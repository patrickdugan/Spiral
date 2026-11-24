#!/usr/bin/env python3
"""Stage a pinned third-party Cairo CUDA source tree with the saved-input adapter."""

import argparse
import hashlib
import json
from pathlib import Path

from stage import archive_tree


CAIRO_REV = '4c54e2e52fc447b7c97ca3d5ffecb759230a676f'
STWO_REV = '483f8c94c02bc7c4eaf128f2cd2269dd6f1a5f6c'
VORTEX_REV = '1e88c31974bcb9906274d7a129bd9f2902d7ae2e'
STWO_URL = 'https://github.com/garrick247/stwo-fork.git'
VORTEX_URL = 'https://github.com/garrick247/VortexSTARK.git'
VORTEX_BUILD_RS_BLOB = 'ba2e6b225bf42a54e4a106ea042fa89f2dec107c'
VORTEX_GIT = f'git = "{VORTEX_URL}", rev = "{VORTEX_REV}"'
VORTEX_LOCK_SOURCE = f'source = "git+{VORTEX_URL}?rev={VORTEX_REV}#{VORTEX_REV}"\n'.encode()
VORTEX_PACKAGES = {'vortexstark': '', 'vortex-cuda-backend': '/crates/cuda-backend'}
NATIVE_FAMILIES = {'sm_80': 'Ampere', 'sm_86': 'Ampere', 'sm_120': 'Blackwell'}


def install_adapter(cairo):
    workspace = cairo / 'Cargo.toml'
    package = cairo / 'crates/prover/Cargo.toml'
    lock = cairo / 'Cargo.lock'
    manifest = package.read_text(encoding='utf-8')
    workspace_text = workspace.read_text(encoding='utf-8')
    locked = lock.read_bytes()
    git_pins = ((STWO_URL, STWO_REV, workspace_text), (VORTEX_URL, VORTEX_REV, manifest))
    if any(f'git = "{url}", rev = "{revision}"' not in source
           or f'source = "git+{url}?rev={revision}#{revision}"'.encode() not in locked
           for url, revision, source in git_pins):
        raise ValueError('pinned CUDA candidate dependencies disagree')
    features, dependencies = '[features]\n', '[dependencies]\n'
    if (manifest.count(features) != 1 or manifest.count(dependencies) != 1
            or 'cuda-prove-json' in manifest or 'cuda-backend = ' not in manifest):
        raise ValueError('unexpected CUDA candidate prover manifest')
    manifest = manifest.replace(features, features + 'cuda-prove-json = ["cuda-backend", "dep:tracing-subscriber"]\n')
    manifest = manifest.replace(dependencies, dependencies + 'tracing-subscriber = { workspace = true, optional = true }\n')
    manifest += ('\n[[bin]]\nname = "prove-json-cuda"\npath = "src/bin/prove-json-cuda.rs"\n'
                 'required-features = ["cuda-prove-json"]\n')
    source = Path(__file__).with_name('prove-json-cuda.rs').read_bytes().replace(b'\r\n', b'\n')
    binary = package.parent / 'src/bin/prove-json-cuda.rs'
    binary.parent.mkdir(exist_ok=True)
    with binary.open('xb') as stream:
        stream.write(source)
    package.write_text(manifest, encoding='utf-8', newline='\n')
    return {'schema': 'proof-grove/shinigami-cuda-adapter-source/v1',
            'cairo_commit': CAIRO_REV, 'stwo_commit': STWO_REV, 'vortex_commit': VORTEX_REV,
            'vortex_license': 'BUSL-1.1', 'cairo_lock_sha256': hashlib.sha256(locked).hexdigest(),
            'cli_source_sha256': hashlib.sha256(source).hexdigest(),
            'prover_manifest_sha256': hashlib.sha256(package.read_bytes()).hexdigest()}


def stage_native(cairo, vortex, architecture):
    build_path = vortex / 'build.rs'
    original = build_path.read_bytes()
    git_blob = hashlib.sha1(f'blob {len(original)}\0'.encode() + original).hexdigest()
    if git_blob != VORTEX_BUILD_RS_BLOB:
        raise ValueError('unexpected pinned Vortex build.rs')
    # The pinned build script uses CRLF. Preserve the original bytes outside this block.
    start = original.index(b'        // GPU architectures\r\n')
    last_arch = b'        cmd.args(["-gencode", "arch=compute_89,code=compute_89"]);\r\n'
    end = original.index(last_arch, start) + len(last_arch)
    family = NATIVE_FAMILIES[architecture]
    compute = architecture.replace('sm_', 'compute_', 1)
    target = (f'        // {family} native cubin\r\n'
              f'        cmd.args(["-gencode", "arch={compute},code={architecture}"]);\r\n').encode()
    patched = original[:start] + target + original[end:]

    prover = cairo / 'crates/prover/Cargo.toml'
    dev_utils = cairo / 'crates/dev_utils/Cargo.toml'
    manifests = {prover: tuple(VORTEX_PACKAGES), dev_utils: ('vortexstark',)}
    staged_manifests = {}
    for path, packages in manifests.items():
        manifest = path.read_bytes()
        for package in packages:
            dependency = f'{package} = {{ {VORTEX_GIT}, optional = true }}\n'.encode()
            local_path = '../../../vortex' + VORTEX_PACKAGES[package]
            if manifest.count(dependency) != 1:
                raise ValueError(f'unexpected {package} dependency in {path}')
            local_dependency = f'{package} = {{ path = "{local_path}", optional = true }}\n'.encode()
            manifest = manifest.replace(dependency, local_dependency)
        if VORTEX_URL.encode() in manifest:
            raise ValueError(f'unexpected remaining Vortex dependency in {path}')
        staged_manifests[path] = manifest

    lock_path = cairo / 'Cargo.lock'
    lock = lock_path.read_bytes()
    for package in VORTEX_PACKAGES:
        record = f'[[package]]\nname = "{package}"\nversion = "0.1.0"\n'.encode()
        if lock.count(record + VORTEX_LOCK_SOURCE) != 1:
            raise ValueError(f'unexpected {package} lock record')
        lock = lock.replace(record + VORTEX_LOCK_SOURCE, record)
    if VORTEX_URL.encode() in lock:
        raise ValueError('unexpected remaining Vortex Git lock record')

    build_path.write_bytes(patched)
    for path, manifest in staged_manifests.items():
        path.write_bytes(manifest)
    lock_path.write_bytes(lock)
    return {'cuda_architecture': architecture, 'vortex_build_rs_original_git_blob': git_blob,
            'vortex_build_rs_original_sha256': hashlib.sha256(original).hexdigest(),
            'vortex_build_rs_staged_sha256': hashlib.sha256(patched).hexdigest(),
            'staged_cairo_lock_sha256': hashlib.sha256(lock).hexdigest(),
            'prover_manifest_sha256': hashlib.sha256(staged_manifests[prover]).hexdigest(),
            'dev_utils_manifest_sha256': hashlib.sha256(staged_manifests[dev_utils]).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cuda-cairo-git', type=Path, required=True)
    parser.add_argument('--vortex-git', '--vortex-sm86-git', type=Path,
                        help='archive the pinned Vortex checkout for a native CUDA target')
    parser.add_argument('--cuda-arch', choices=NATIVE_FAMILIES, help='native CUDA target, defaults to sm_86')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.cuda_arch and not args.vortex_git:
        parser.error('--cuda-arch requires --vortex-git')
    target = args.out.resolve()
    archive_tree(args.cuda_cairo_git.resolve(), CAIRO_REV, target)
    cairo = target / 'stwo_cairo_prover'
    report = install_adapter(cairo)
    if args.vortex_git:
        vortex = target / 'vortex'
        archive_tree(args.vortex_git.resolve(), VORTEX_REV, vortex)
        report.update(stage_native(cairo, vortex, args.cuda_arch or 'sm_86'))
    (target / 'cuda-source-pins.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cuda-cairo-git', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    target = args.out.resolve()
    archive_tree(args.cuda_cairo_git.resolve(), CAIRO_REV, target)
    report = install_adapter(target / 'stwo_cairo_prover')
    (target / 'cuda-source-pins.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Stage the pinned Cairo prover and opt-in disk Merkle overlay in a new directory."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


STWO_REV = 'aeceb74c58184d7886ebd7f34a7453fee714ca40'
CAIRO_REV = '467d5c6d4d6d526c1db8ff69c14f2de6d57f4d73'
STWO_URL = 'https://github.com/starkware-libs/stwo'
CRATES = {
    'stwo': 'stwo',
    'stwo-air-utils': 'air-utils',
    'stwo-air-utils-derive': 'air-utils-derive',
    'stwo-constraint-framework': 'constraint-framework',
}


def archive_tree(repository, revision, target):
    verified = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', f'{revision}^{{commit}}'],
                                       text=True).strip()
    if verified != revision:
        raise ValueError('Unexpected source commit')
    target.mkdir(exist_ok=False)
    with subprocess.Popen(['git', '-C', str(repository), 'archive', '--format=tar', revision],
                          stdout=subprocess.PIPE) as archive:
        subprocess.run(['tar', '-xf', '-', '-C', str(target)], stdin=archive.stdout, check=True)
        if archive.wait():
            raise RuntimeError(f'Git could not archive {revision}')


def point_cairo_to_overlay(cairo):
    manifest = cairo / 'Cargo.toml'
    lockfile = cairo / 'Cargo.lock'
    workspace = manifest.read_text(encoding='utf-8')
    lock = lockfile.read_text(encoding='utf-8')
    suffix = f'git+{STWO_URL}?rev={STWO_REV[:8]}#{STWO_REV}'
    for package, directory in CRATES.items():
        direct_dependency = f'{package} = {{ git = "{STWO_URL}", rev = "{STWO_REV[:8]}" }}'
        if workspace.count(direct_dependency + '\n') != 1:
            raise ValueError(f'Unexpected pinned dependency {package}')
        workspace = workspace.replace(direct_dependency + '\n', f'{package} = {{ path = "../../stwo/crates/{directory}" }}\n')
        pattern = rf'(\[\[package\]\]\nname = "{re.escape(package)}"\nversion = "[^"\n]+"\n)source = "{re.escape(suffix)}"\n'
        lock, count = re.subn(pattern, r'\1', lock)
        if count != 1:
            raise ValueError(f'Unexpected lockfile record for {package}')
    if f'source = "git+{STWO_URL}' in lock:
        raise ValueError('Lockfile still lists a Stwo Git dependency')
    manifest.write_text(workspace, encoding='utf-8', newline='\n')
    lockfile.write_text(lock, encoding='utf-8', newline='\n')
    return hashlib.sha256(lockfile.read_bytes()).hexdigest()


def install_cli(target):
    cairo = target / 'cairo/stwo_cairo_prover'
    pins = json.loads((target / 'source-pins.json').read_bytes())
    lock_sha256 = hashlib.sha256((cairo / 'Cargo.lock').read_bytes()).hexdigest()
    if (pins['cairo_commit'], pins['stwo_commit'], pins['cairo_cargo_lock_sha256']) != (
            CAIRO_REV, STWO_REV, lock_sha256):
        raise ValueError('staged Cairo source pins disagree')
    package = cairo / 'crates/prover/Cargo.toml'
    manifest = package.read_text(encoding='utf-8')
    features, dependencies = '[features]\n', '[dependencies]\n'
    if manifest.count(features) != 1 or manifest.count(dependencies) != 1 or 'disk-prove-cli' in manifest:
        raise ValueError('unexpected or already extended Cairo prover manifest')
    manifest = manifest.replace(features, features + 'disk-prove-cli = ["dep:tracing-subscriber"]\n')
    manifest = manifest.replace(dependencies, dependencies
                                + 'tracing-subscriber = { workspace = true, optional = true }\n')
    manifest += ('\n[[bin]]\nname = "prove-json"\npath = "src/bin/prove-json.rs"\n'
                 'required-features = ["disk-prove-cli"]\n')
    source = Path(__file__).with_name('prove-json.rs').read_bytes().replace(b'\r\n', b'\n')
    binary = cairo / 'crates/prover/src/bin/prove-json.rs'
    binary.parent.mkdir(exist_ok=True)
    with binary.open('xb') as stream:
        stream.write(source)
    package.write_text(manifest, encoding='utf-8', newline='\n')
    report = dict(pins, cli_source_sha256=hashlib.sha256(source).hexdigest(),
                  prover_manifest_sha256=hashlib.sha256(package.read_bytes()).hexdigest())
    (target / 'cli-pins.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def install_cuda_merkle(target):
    """Add the opt-in CUDA batch driver to the exact staged disk Merkle overlay."""
    integration = Path(__file__).parent
    pins = json.loads((target / 'source-pins.json').read_bytes())
    overlay = integration.joinpath('stwo-aeceb74c-disk-merkle.patch').read_bytes().replace(b'\r\n', b'\n')
    if (pins['stwo_commit'], pins['cairo_commit'], pins['overlay_sha256']) != (
            STWO_REV, CAIRO_REV, hashlib.sha256(overlay).hexdigest()):
        raise ValueError('unexpected source pins for the CUDA disk Merkle overlay')
    stwo = target / 'stwo/crates/stwo'
    merkle = stwo / 'src/prover/vcs_lifted'
    cairo = target / 'cairo/stwo_cairo_prover'
    archived = {
        stwo / 'Cargo.toml': 'e54976d349444cfc975bd86df7bcb4ebdd802c27fa66b67e50fcfff3ef4f1b9a',
        merkle / 'mod.rs': '6cf8c79d305e3231d60498d9a78e156e79852bedd3401c6981be17e48990549a',
        merkle / 'disk.rs': '86f95cd84c04a36c5e1cf103e76f757a69ed7504a33dc2206c3a3ac0df6e7d92',
        cairo / 'Cargo.lock': pins['cairo_cargo_lock_sha256'],
        cairo / 'crates/cairo-air/src/claims.rs': '92b78ff266f82d172c93053fd6f75424a0baafd351c3ae862c9186901aa35fc0',
        cairo / 'crates/cairo-air/src/verifier.rs': 'cc40b2e34ef53133a5c35f62aa6ec389f3c86c5820568d3c41acb7b1be4efe12',
    }
    for path, expected in archived.items():
        if hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise ValueError(f'unexpected archived source: {path}')
    module = merkle / 'disk_cuda.rs'
    if module.exists():
        raise ValueError('CUDA disk Merkle overlay already installed')
    source = integration.joinpath('disk-merkle-cuda.rs').read_bytes().replace(b'\r\n', b'\n')
    feature = 'disk-merkle = ["prover"]\n'
    cuda_cfg = '#[cfg(all(target_os = "linux", feature = "cuda-disk-merkle"))]'
    edits = {
        stwo / 'Cargo.toml': [(feature, feature + 'cuda-disk-merkle = ["disk-merkle"]\n')],
        merkle / 'mod.rs': [('mod disk;\n', f'mod disk;\n{cuda_cfg}\nmod disk_cuda;\n')],
        merkle / 'disk.rs': [
            ('        let mut dirty_bytes = 0;\n',
             f'        let mut dirty_bytes = 0;\n        {cuda_cfg}\n'
             '        let mut cuda = super::disk_cuda::CudaDiskMerkle::from_environment()?;\n'
             f'        {cuda_cfg}\n'
             '        let started = std::time::Instant::now();\n'),
            ('        for first in (0..leaves).step_by(NODES_PER_BATCH) {\n'
             '            let count = (leaves - first).min(NODES_PER_BATCH);\n',
             '        let batch_size = NODES_PER_BATCH.min(leaves);\n'
             f'        {cuda_cfg}\n'
             '        let batch_size = if cuda.is_some() {\n'
             '            super::disk_cuda::CudaDiskMerkle::leaf_batch_size(batch_size, &shifts)?\n'
             '        } else {\n'
             '            batch_size\n'
             '        };\n'
             '        for first in (0..leaves).step_by(batch_size) {\n'
             '            let count = (leaves - first).min(batch_size);\n'),
            ('            #[cfg(feature = "parallel")]\n',
             f'            {cuda_cfg}\n'
             '            if let Some(cuda) = &mut cuda {\n'
             '                cuda.hash_leaves(first, &shifts, bytes, |col, row| {\n'
             '                    <B as MerkleOpsLifted<H>>::disk_leaf_value(columns[col], row).0\n'
             '                })?;\n'
             '                append(&mut file, bytes, &mut dirty_bytes)?;\n'
             '                continue;\n'
             '            }\n'
             '            #[cfg(feature = "parallel")]\n'),
            ('                for (record, pair) in bytes\n',
             f'                {cuda_cfg}\n'
             '                if let Some(cuda) = &cuda {\n'
             '                    cuda.hash_parents(inputs, bytes)?;\n'
             '                    append(&mut file, bytes, &mut dirty_bytes)?;\n'
             '                    continue;\n'
             '                }\n'
             '                for (record, pair) in bytes\n'),
            ('        offsets.reverse();\n',
             f'        {cuda_cfg}\n'
             '        if cuda.is_some() {\n'
             '            tracing::info!(leaves, seconds = started.elapsed().as_secs_f64(),\n'
             '                "Committed disk Merkle tree with CUDA batches");\n'
             '        }\n'
             '        offsets.reverse();\n'),
        ],
    }
    rendered = {}
    for path, replacements in edits.items():
        original = path.read_text(encoding='utf-8')
        updated = original
        for before, after in replacements:
            if updated.count(before) != 1:
                raise ValueError(f'unexpected exact disk Merkle source fragment in {path}')
            updated = updated.replace(before, after)
        rendered[path] = updated.encode()
    rendered[module] = source
    for path, updated in rendered.items():
        path.write_bytes(updated)
    native = integration.joinpath('disk-merkle-cuda.cu').read_bytes().replace(b'\r\n', b'\n')
    report = dict(pins, cuda_disk_merkle_abi=1, native_source_sha256=hashlib.sha256(native).hexdigest(),
                  archived_files={str(path.relative_to(target)): digest for path, digest in archived.items()},
                  overlay_files={
        str(path.relative_to(target)): hashlib.sha256(updated).hexdigest()
        for path, updated in rendered.items()
    })
    (target / 'cuda-disk-merkle-pins.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stwo-git', type=Path)
    parser.add_argument('--cairo-git', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--install-cli', type=Path, help='add the JSON-only CLI to an existing staged tree')
    parser.add_argument('--install-cuda-merkle', type=Path, help='add opt-in CUDA batches to a staged disk tree')
    args = parser.parse_args()
    if args.install_cuda_merkle:
        if any((args.stwo_git, args.cairo_git, args.out, args.install_cli)):
            parser.error('--install-cuda-merkle takes only an existing staged directory')
        print(json.dumps(install_cuda_merkle(args.install_cuda_merkle.resolve())))
        return
    if args.install_cli:
        if any((args.stwo_git, args.cairo_git, args.out)):
            parser.error('--install-cli takes only an existing staged directory')
        print(json.dumps(install_cli(args.install_cli.resolve())))
        return
    if not all((args.stwo_git, args.cairo_git, args.out)):
        parser.error('--stwo-git, --cairo-git and --out are required for source staging')
    target = args.out.resolve()
    target.mkdir(parents=True, exist_ok=False)
    archive_tree(args.stwo_git.resolve(), STWO_REV, target / 'stwo')
    archive_tree(args.cairo_git.resolve(), CAIRO_REV, target / 'cairo')
    patch = Path(__file__).with_name('stwo-aeceb74c-disk-merkle.patch').read_bytes().replace(b'\r\n', b'\n')
    # Unlike Git's repository discovery, patch always operates on the staged tree.
    for flags in (['--dry-run'], []):
        subprocess.run(['patch', '-p1', '--batch', '--forward', *flags], cwd=target / 'stwo', input=patch, check=True)
    lock_hash = point_cairo_to_overlay(target / 'cairo/stwo_cairo_prover')
    report = {'schema': 'proof-grove/shinigami-stwo-build-input/v1', 'stwo_commit': STWO_REV,
              'cairo_commit': CAIRO_REV, 'overlay_sha256': hashlib.sha256(patch).hexdigest(),
              'cairo_cargo_lock_sha256': lock_hash}
    (target / 'source-pins.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

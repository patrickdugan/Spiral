"""Inspect the named post-compression pins without releasing M14 state."""

from pathlib import Path
import hashlib
import json
import shutil
import stat
import sys
import tempfile
import subprocess
import time


campaign = Path('/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat')
ark = campaign / 'outputs/zk-rusto-no-bitcoino-ark/Ark'
runtime = Path('/var/tmp/ark-asp-full-20261117')
public = runtime / 'm14-public-file-backed-20261123'
private = Path('/var/tmp/ark-m14-private-file-backed-20261123')
checked = campaign / 'work/ark-modern-verifiers-target-20261122/release'
manager = Path('/var/tmp/ark-asp-pinned-tools-20261123/ark-asp-management')
public_pin = 'dd352842409878b3da279ce254d39ff95e4425ef5c256fdbbf6426acffa88f41'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    return json.loads(path.read_bytes())


pins = record(ark / 'fixtures/bitvm3-pins.proof-grove.json')
tool_pins = {
    'sdk_host': (Path('/root/nb3/m13/wrap/target/release/ark-asp-sp1-host'), '28c3bb3082bd4d4d20f27647bd3c08046eb9822b295138bfccd03c8eac2ca88c'),
    'm13_wrapper': (Path('/root/nb3/m13/wrap/target/release/m13'), 'f3e0608f83f55db8327d371fd90753c9fb450e49682c5ae8f41ce249c784eb2f'),
    'guest_elf': (campaign/'work/ark-asp-guest/ark-asp-nova-guest', '7ce5812fd76c3b31a5c3c24d117120b02839175636a68586e0fe97d370dcba5d'),
    'management': (manager, pins['management_cli_sha256']),
    'm13_verifier': (checked/'m13-verify', pins['m13_verifier_sha256']),
}
for tool, (path, pin) in tool_pins.items():
    if digest(path) != pin:
        raise ValueError(f'{tool}: pinned executable digest differs')
if digest(runtime/'expected-public.bin') != public_pin:
    raise ValueError('stored Ark public values differ from the pinned statement')
with tempfile.TemporaryDirectory(prefix='ark-readiness-') as scratch:
    rebuilt = Path(scratch)/'public.bin'
    subprocess.run([str(manager), 'expect', '--snapshot', str(ark/'fixtures/proof-grove-regtest.json'),
                    '--policy', str(ark/'fixtures/policy-proof-grove.json'),
                    '--proof-dir', str(ark/'.runtime/proof-grove-verified'),
                    '--vk-sha256', pins['nova_vk_sha256'], '--out', str(rebuilt)],
                   check=True, capture_output=True, timeout=45)
    if digest(rebuilt) != public_pin or rebuilt.stat().st_size != 1616:
        raise ValueError('the local policy and Nova inputs rebuild a different public statement')

selection = record(campaign/'work/ark-m14-file-backed-setup-20261123/toolchain-selection.json')
receipt = record(ark/'results/m14-bounded-setup-20261123.json')
state = record(public/'run-state.json')
manifest_path = public/'claim-public/manifest.json'
manifest = record(manifest_path)
build_path = Path(selection['build_pins']).resolve(strict=True)
if not build_path.is_relative_to(ark.resolve()/'results') or digest(build_path) != receipt['build_report_sha256']:
    raise ValueError('the M14 build report differs from the verified setup receipt')
build = record(build_path)
statement = {key: pins[key] for key in ('wrap_vk_sha256', 'program_vk_digest', 'recursion_vk_root')}
statement.update(committed_values_sha256=public_pin, exit_code=0, is_complete=1)
if not (manifest['statement'] == receipt['statement'] == state['statement'] == selection['statement'] == statement
        and state['manifest_sha256'] == receipt['manifest_sha256']
        and digest(manifest_path) == receipt['manifest_file_sha256']
        and receipt['status'] == 'statement_bound_setup_artifacts_verified'):
    raise ValueError('the public M14 setup is bound to a different statement')
for role, binary, state_key in (('m14-claim','native_cli','native_cli_sha256'),
                                 ('ark-m14-negative-input','negative_cli','negative_cli_sha256')):
    if digest(Path(selection[binary])) != build['binaries'][role]['sha256'] or state[state_key] != build['binaries'][role]['sha256']:
        raise ValueError(f'{role}: prepared verifier executable differs from its build pin')
for script in ('ark-overnight-verify.sh', 'ark-overnight-m14.sh'):
    subprocess.run(['/bin/bash', '-n', str(Path(__file__).with_name(script))], check=True, timeout=5)

with tempfile.TemporaryDirectory(prefix='ark-verifier-startup-') as scratch:
    invalid = Path(scratch)/'invalid.bin'
    invalid.write_bytes(b'\0')
    statement_file = Path(scratch)/'statement.json'
    statement_file.write_text(json.dumps(statement), encoding='ascii')
    requests = {
        'sdk': [str(tool_pins['sdk_host'][0]), 'verify-sp1', str(tool_pins['guest_elf'][0]), str(invalid), str(runtime/'expected-public.bin')],
        'm13': [str(tool_pins['m13_verifier'][0]), 'verify-v2', str(invalid), str(statement_file)],
    }
    startup = {}
    for name, args in requests.items():
        start = time.monotonic()
        result = subprocess.run(args, capture_output=True, text=True, timeout=150 if name == 'sdk' else 30)
        if result.returncode != 1 or 'panicked' in result.stderr.lower() or not result.stderr.strip():
            raise ValueError(f'{name}: malformed-input smoke check did not refuse normally')
        startup[name] = {'return_code': result.returncode, 'error': result.stderr.splitlines()[0],
                         'elapsed_seconds': round(time.monotonic()-start, 3)}

if set(state) & {'proof_sha256', 'release_dir', 'release_sha256'}:
    raise ValueError('the preserved M14 setup already has a bound proof or release')
private_info = private.lstat()
if not stat.S_ISDIR(private_info.st_mode) or stat.S_IMODE(private_info.st_mode) != 0o700 or private_info.st_uid != 0:
    raise ValueError('the preserved M14 setup directory is not private root-owned storage')
space = {kind: shutil.disk_usage(path).free for kind,path in (
    ('wsl_native', private), ('windows_d', '/mnt/d'), ('windows_c', '/mnt/c'))}
if not all(space[name] >= 8 * 1024**3 for name in ('wsl_native','windows_d')):
    raise ValueError('an M14 working volume lacks the queued disk reserve')
print(json.dumps({'schema':'ark-post-compression-preflight/v1','status':'post_compression_preflight_passed',
                  'pinned_tool_sha256':{key: pin for key, (_,pin) in tool_pins.items()} | {
                      key: build['binaries'][key]['sha256'] for key in ('m14-claim','ark-m14-negative-input')},
                  'rebuilt_expected_public_sha256':public_pin, 'public_bytes':1616,
                  'manifest_file_sha256':receipt['manifest_file_sha256'], 'm14_build_report_sha256':receipt['build_report_sha256'],
                  'queued_scripts_bash_syntax_passed':True, 'startup_malformed_input_refusals':startup,
                  'private_release_bound':False,
                  'working_volumes_free_bytes':space,'proof_verified':False}))

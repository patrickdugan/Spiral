"""Install an approved, staged Proof Grove API release on its dedicated VPS.

Run as ubuntu after installing Caddy. The public verifier/proof QA directory and
the committed release archive must already be present. Credentials are generated
on the server and never printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import secrets
import shutil
import subprocess
import tarfile
import time
import urllib.request

BASE=Path('/opt/proof-grove')
DOMAIN='proof-grove.170-75-168-145.sslip.io'
VERIFIER_SHA='4ffe8241b0dddfde808366f865a551d75e726489c300cb4d720027820159897c'


def run(*command):
    return subprocess.check_output(command,text=True,stderr=subprocess.STDOUT).strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',required=True)
    parser.add_argument('--qa-directory',type=Path,required=True)
    args=parser.parse_args()
    if not args.release.isalnum():raise SystemExit('An exact Git release identifier is required')
    qa=args.qa_directory.resolve()
    if qa.parent!=Path('/tmp') or not qa.name.startswith('proof-grove-qa-'):raise SystemExit('An owned temporary QA directory is required')
    before=run('systemctl','show','rehearsal-bitcoind.service','--property=MainPID','--value')
    os.umask(0o077)
    for name in ('releases','bin','records/testnet4','config','state','staging'):
        (BASE/name).mkdir(parents=True,exist_ok=True)
    release=BASE/'releases'/args.release;release.mkdir(exist_ok=True)
    with tarfile.open(BASE/'release.tar.gz') as tar:tar.extractall(release,filter='data')
    # The Cashu bridge verifies wallet signatures with the pinned SDK, even when
    # its HTTP service is launched by systemd rather than an interactive shell.
    node_bin=Path('/home/ubuntu/node24/node-v24.22.1-linux-x64/bin')
    if not (node_bin/'node').is_file():raise SystemExit('The approved Node 24 runtime is missing')
    env=os.environ|{'PATH':str(node_bin)+':/usr/local/bin:/usr/bin:/bin'}
    with (BASE/'staging/sdk-install.log').open('ab') as log:
        subprocess.run([str(node_bin/'npm'),'exec','--yes','--package=pnpm@11.25.0','--','pnpm',
            '--dir',str(release/'app/wallet'),'install','--frozen-lockfile','--ignore-scripts','--prod'],
            env=env,stdout=log,stderr=log,check=True)
    binary=(qa/'m13-verify').read_bytes()
    if hashlib.sha256(binary).hexdigest()!=VERIFIER_SHA:raise SystemExit('Verifier hash differs from the reviewed QA binary')
    executable=BASE/'bin/m13-verify';executable.write_bytes(binary);executable.chmod(0o750)
    for name in ('public.bin','wrap-v2.bin','statement-check.json','native-verify.json'):
        shutil.copyfile(qa/'records'/name,BASE/'records/testnet4'/name)
    environment=BASE/'config/operator.env'
    if not environment.exists():
        environment.write_text('PROOF_GROVE_API_TOKEN='+secrets.token_urlsafe(32)+'\n',encoding='utf-8')
    environment.chmod(0o600)
    token=environment.read_text().strip().split('=',1)[1]
    render=runpy.run_path(str(release/'app/deploy/render_config.py'))['render']
    configuration=render(BASE/'records/testnet4',str(executable),VERIFIER_SHA,DOMAIN)
    (BASE/'config/testnet4.local.json').write_text(json.dumps(configuration,indent=2)+'\n',encoding='utf-8')
    next_link=BASE/'current.next'
    if next_link.is_symlink():next_link.unlink()
    next_link.symlink_to(release/'app',target_is_directory=True);os.replace(next_link,BASE/'current')
    run('sudo','-n','install','-m','0644',str(release/'app/deploy/proof-grove.service'),'/etc/systemd/system/proof-grove.service')
    caddy_env=BASE/'staging/caddy-environment.conf'
    caddy_env.write_text('[Service]\nEnvironment=PROOF_GROVE_API_DOMAIN='+DOMAIN+'\n',encoding='utf-8')
    run('sudo','-n','install','-d','/etc/systemd/system/caddy.service.d')
    run('sudo','-n','install','-m','0644',str(caddy_env),'/etc/systemd/system/caddy.service.d/proof-grove.conf')
    run('sudo','-n','env','PROOF_GROVE_API_DOMAIN='+DOMAIN,'caddy','validate','--config',str(release/'app/deploy/Caddyfile'),'--adapter','caddyfile')
    backup=BASE/'staging/Caddyfile.before-proof-grove'
    if not backup.exists():shutil.copyfile('/etc/caddy/Caddyfile',backup)
    run('sudo','-n','install','-m','0644',str(release/'app/deploy/Caddyfile'),'/etc/caddy/Caddyfile')
    run('sudo','-n','systemctl','daemon-reload')
    run('sudo','-n','systemctl','enable','--now','proof-grove.service')
    run('sudo','-n','systemctl','restart','proof-grove.service')
    run('sudo','-n','systemctl','restart','caddy.service')
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','X-Proof-Grove':'1'}
    def request(path,body=None):
        req=urllib.request.Request('http://127.0.0.1:8767'+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    for attempt in range(20):
        try:status=request('/api/status');break
        except OSError:time.sleep(1)
    else:raise SystemExit('API did not start; inspect its systemd journal')
    chain=request('/api/chainstate');proof=request('/api/proofs/recorded/check',{})
    after=run('systemctl','show','rehearsal-bitcoind.service','--property=MainPID','--value')
    assert before==after and before!='0','Existing Core process changed unexpectedly'
    assert proof['proof_verified'] and proof['chain_observation'] and not proof['payment_admitted']
    print(json.dumps({'api_active':status['mode']=='live','core_height':chain['blocks'],'native_proof_verified':True,
                     'existing_core_pid_unchanged':True,'https_origin':'https://'+DOMAIN,'token_printed':False}))


if __name__=='__main__':main()

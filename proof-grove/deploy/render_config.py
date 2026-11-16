"""Render the server-owned testnet4 profile from the committed public record.

No passwords, seeds or bearer values are accepted or written by this command.
"""
import argparse
import hashlib
import json
from pathlib import Path


def render(record:Path,verifier:str,binary_hash:str,domain:str):
    statement=(record/'public.bin').read_bytes()
    reference=json.loads((record/'statement-check.json').read_text(encoding='utf-8'))
    pins=json.loads((record/'native-verify.json').read_text(encoding='utf-8'))['statement']
    proof_hash=hashlib.sha256((record/'wrap-v2.bin').read_bytes()).hexdigest()
    if hashlib.sha256(statement).hexdigest()!=pins['committed_values_sha256']:
        raise ValueError('Public record statement hash does not match its verifier receipt')
    if len(binary_hash)!=64 or any(c not in '0123456789abcdef' for c in binary_hash):raise ValueError('Verifier SHA-256 required')
    return {'mode':'live','database':'/opt/proof-grove/state/testnet4.sqlite',
      'gate':{'format':'m13-final','argv':[verifier],'binary_sha256':binary_hash},
      'core':{'url':'http://127.0.0.1:48332','cookie_file':'/home/ubuntu/rehearsal/btc-data/testnet4/.cookie'},
      'policy':{'network':'testnet4','min_confirmations':6,'min_tip_chainwork':reference['tip']['chainwork'],
       'anchor':reference['anchor'],
       'pins':{**{key:pins[key] for key in ('wrap_vk_sha256','program_vk_digest','recursion_vk_root')},
        'nova_vk_sha256':statement[1100:1132].hex(),'genesis_z0_sha256':hashlib.sha256(statement[12:556]).hexdigest()},
       'scripts':[{'id':'historical-burger-testnet4','script_sha256':statement[1260:1292].hex(),'min_value_sats':11600}]},
      'max_tip_lag':144,'intents':[],
      'recorded_proof':{'name':'Burger testnet4: checkpoint 160000 to tip 161016; historical payment, verification only',
       'statement_file':'/opt/proof-grove/records/testnet4/public.bin','proof_file':'/opt/proof-grove/records/testnet4/wrap-v2.bin',
       'statement_sha256':pins['committed_values_sha256'],'proof_sha256':proof_hash},
      'hosted_api':{'token_env':'PROOF_GROVE_API_TOKEN','allowed_origins':['https://patrickdugan.github.io'],
       'public_hosts':[domain],'allow_mutations':False,'allow_private_bundles':False}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',type=Path,required=True)
    parser.add_argument('--verifier',required=True)
    parser.add_argument('--verifier-sha256',required=True)
    parser.add_argument('--domain',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    config=render(args.record,args.verifier,args.verifier_sha256,args.domain)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'configuration_written':True,'network':'testnet4','secrets_written':False}))

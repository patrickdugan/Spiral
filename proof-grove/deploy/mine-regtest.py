"""Mine one block on the explicitly isolated, valueless Proof Grove sandbox."""
import base64
import json
from pathlib import Path
import urllib.request

root=Path('/opt/proof-grove/regtest')
settings=json.loads((root/'private.json').read_text())
headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(('proofgrove:'+settings['rpc_password']).encode()).decode()}

def rpc(method,params,wallet=False):
    req=urllib.request.Request('http://127.0.0.1:28743'+('/wallet/proof-grove-sandbox-miner' if wallet else ''),
        data=json.dumps({'jsonrpc':'2.0','id':'pg-regtest-miner','method':method,'params':params}).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=30) as response:result=json.load(response)
    if result.get('error'):raise RuntimeError('Isolated miner RPC refused')
    return result['result']

if rpc('getblockchaininfo',[])['chain']!='regtest':raise SystemExit('Refusing to mine outside regtest')
rpc('generatetoaddress',[1,settings['mining_address']],True)

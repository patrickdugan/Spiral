"""Export an allowlisted static fixture demo; never export local wallet state."""
import argparse
import json
import re
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from proofdesk import demo
from proofdesk.archive import bundle
from proofdesk.server import Desk


def export_pages(output:Path):
    output=output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Static export requires a new or empty output directory')
    output.mkdir(parents=True,exist_ok=True)
    runs={case['id']:demo.run_case(case['id']) for case in demo.CASES}
    archives={}
    for key,run in runs.items():
        raw,manifest=bundle(run['receipts'])
        archives[key]={'text':raw.decode('utf-8'),'manifest':manifest}
    payload={'status':{**Desk().status(),'hosting':'static-fixtures'},'cases':demo.CASES,
             'runs':runs,'archives':archives,'sources':json.loads((ROOT/'docs/sources.json').read_text(encoding='utf-8')),
             'vtxos':{'evidence_level':'fixture','tip_height':1005,'vtxos':demo.vtxos(),'plans':demo.plans()},
             'plans':{str(height):demo.plans(height) for height in range(1005,1381)}}
    (output/'demo-data.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    for name in ('styles.css','app.js','icon.svg','hosted.js'):
        shutil.copyfile(ROOT/'web'/name,output/name)
    html=(ROOT/'web/index.html').read_text(encoding='utf-8')
    for name in ('styles.css','app.js','icon.svg'):
        html=html.replace('"/'+name+'"','"./'+name+'"')
    html=html.replace('href="/"','href="./"').replace('<script src="./app.js" defer>',
        '<script src="./hosted.js" defer></script><script src="./app.js" defer>')
    html=html.replace('<section class="panel" id="ark-connection">','<section class="panel" id="ark-connection" hidden>')
    html=html.replace('<section class="panel" id="exit-recovery">','<section class="panel" id="exit-recovery" hidden>')
    html=html.replace('v0.4 · local build','v0.4 · hosted fixture demo')
    html=html.replace('Local workspace <small>Python · no dependencies</small>',
        'Public fixture demo <small>Wallet operations run locally</small>')
    notice='<strong>Hosted fixture demo.</strong> Payment cases and slider decisions are precomputed from the Python policy. Native proof verification and wallet signing run locally. No funds are used on this website.'
    html=re.sub(r'(<div class="notice" id="mode-notice">.*?<p>).*?(</p>)',lambda m:m[1]+notice+m[2],html,count=1)
    results=output/'results';results.mkdir()
    for name in ('cashu-ark-integration.json','cashu-ark-exit-integration.json'):
        report=json.loads((ROOT/'docs'/name).read_text(encoding='utf-8'))
        if report.get('status')!='passed':raise ValueError('Only a passed public test report can be published')
        shutil.copyfile(ROOT/'docs'/name,results/name)
    section='''<section class="panel"><div class="panel-head"><h2>Recorded regtest withdrawal and offline exit</h2><span class="pill">TEST COINS ONLY</span></div><p>The local native test deposited 25,000 sats, withdrew 10,000 into Ark and recovered 15,000 sats of Cashu change after a lost reply. The exact recipient VTXO refreshed and exited with the mint and Ark server offline. The owner claimed 9,165 sats; refresh and claim fees account for the rest. Separate fixture coins paid CPFP fees.</p><p><a href="./results/cashu-ark-integration.json">Read the combined test result ↗</a> · <a href="./results/cashu-ark-exit-integration.json">Read the linked exit result ↗</a> · <a href="https://github.com/patrickdugan/Spiral/tree/main/proof-grove">Source and local setup ↗</a></p></section>'''
    html=html.replace('<section class="panel boundary-panel">',section+'<section class="panel boundary-panel">',1)
    (output/'index.html').write_text(html,encoding='utf-8')
    (output/'.nojekyll').touch()
    return {'output':str(output),'cases':len(runs),'heights':len(payload['plans']),'mode':'static-fixtures'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(export_pages(parser.parse_args().output)))

#!/usr/bin/env python3
"""Reproduce two malicious-prover attacks against exact historical sources.
The optional fetch retrieves only public, pinned Git commits from this repo.
"""
import json
from pathlib import Path
import subprocess
import sys
import types
import nova_ipa as current
from test_ipa_claim_binding import fresh_false_claim,fresh_shifted_commitment

V1 = '0e03f8ab4dd53892436c10059c8087364765a463'
V2 = 'ab6124449d863db6140a3ec0304f6218c5f1aaf9'
PATH = 'BIPSpace/Keyless-CHECKSIG/verifiers/nova_ipa.py'

def historical(revision,label):
    exists = subprocess.run(['git','cat-file','-e',revision],capture_output=True).returncode == 0
    if not exists:
        subprocess.check_call(['git','fetch','--depth=1','origin',revision])
    source = subprocess.check_output(['git','show',f'{revision}:{PATH}'],text=True)
    module = types.ModuleType(label)
    sys.modules[label] = module
    exec(compile(source,f'{revision}:{PATH}','exec'),module.__dict__)
    return module

first = fresh_false_claim(historical(V1,'historical_ipa_v1'))
second = fresh_shifted_commitment(historical(V2,'historical_ipa_v2'))
fixed_first = fresh_false_claim(current)
fixed_second = fresh_shifted_commitment(current)
report = {
    'historical_v1_revision':V1,
    'historical_fresh_false_claim_accepted':first,
    'historical_v2_revision':V2,
    'historical_shifted_commitment_accepted':second,
    'v3_fresh_false_claim_accepted':fixed_first,
    'v3_shifted_commitment_accepted':fixed_second,
    'repair':'Commit C=<a,G>+<b,H>; derive U from a challenge after C, claim and context; verify from C+claim*U.',
    'scope':'Standalone illustrative Python IPA. Upstream Nova uses a separate implementation. Tests do not establish general cryptographic soundness.'
}
print(json.dumps(report,indent=2))
Path('ipa-claim-audit.json').write_text(json.dumps(report,indent=2)+'\n')
if not first or not second or fixed_first or fixed_second:
    raise SystemExit('Historical exploit/fix regression did not behave as expected')

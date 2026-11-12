#!/usr/bin/env python3
"""Compare the historical illustrative IPA against the fixed relation.
Run after fetching OLD_REV into the local Git object database.
"""
import json
from pathlib import Path
import subprocess
import sys
import types
import nova_ipa as current
from test_ipa_claim_binding import fresh_false_claim

OLD_REV = '0e03f8ab4dd53892436c10059c8087364765a463'
PATH = 'BIPSpace/Keyless-CHECKSIG/verifiers/nova_ipa.py'
source = subprocess.check_output(['git','show',f'{OLD_REV}:{PATH}'],text=True)
old = types.ModuleType('historical_keyless_ipa')
sys.modules[old.__name__] = old
exec(compile(source,f'{OLD_REV}:{PATH}','exec'),old.__dict__)
old_accepts = fresh_false_claim(old)
fixed_accepts = fresh_false_claim(current)
report = {'historical_revision':OLD_REV,
          'historical_fresh_false_claim_accepted':old_accepts,
          'fixed_fresh_false_claim_accepted':fixed_accepts,
          'attack':'Malicious prover selects claim+1 before Fiat-Shamir and regenerates all IPA rounds.',
          'repair':'Commit vectors in C; verify folding from C + claim*U.',
          'scope':'Standalone illustrative Python IPA only; upstream Nova is separate.'}
print(json.dumps(report,indent=2))
Path('ipa-claim-audit.json').write_text(json.dumps(report,indent=2)+'\n')
if not old_accepts or fixed_accepts:
    raise SystemExit('The historical exploit/fix regression did not behave as expected')

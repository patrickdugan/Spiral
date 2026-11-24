"""Run the pinned Cairo payout statement and its two negative controls."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


repo, bundle, case = map(Path, sys.argv[1:4])
redemption = bundle / 'redemption'
with tempfile.TemporaryDirectory(prefix='cashu-melt-cairo-') as scratch:
    project = Path(scratch)
    target = project / 'target/dev'
    target.mkdir(parents=True)
    shutil.copyfile(redemption / 'Runtime.toml', project / 'Scarb.toml')
    shutil.copyfile(redemption / 'main.executable.json', target / 'main.executable.json')
    env = os.environ | {'SCARB_CACHE': str(project/'cache'), 'SCARB_TARGET_DIR': str(project/'target'),
                        'PATH': str(bundle/'bin') + os.pathsep + os.environ['PATH'], 'RAYON_NUM_THREADS':'1'}
    result = subprocess.run([sys.executable, '-B', str(repo/'benchmarks/shinigami/redemption/check.py'),
                             str(case), '--project', str(project), '--scarb', str(bundle/'bin/scarb')],
                            check=True, text=True, capture_output=True, timeout=110, env=env)
    data = json.loads(result.stdout)
    assert data['early_spend_refused'] and data['changed_prevout_amount_refused']
    assert data['public_words_matched'] == 24 and data['stark_proof_generated'] is False
    print(json.dumps(data))

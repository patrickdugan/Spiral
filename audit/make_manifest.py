"""Bind only the new deliverables; do not overwrite any historical receipts."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=[p for p in (ROOT/"audit").rglob("*") if p.is_file()
       and "__pycache__" not in p.parts and p.name!="bundle_manifest.json"]
for stem in ("liquidity_on_trial","connector_calculus_critique"):
    paths.extend([ROOT/"paper"/f"{stem}.md",ROOT/"output/pdf"/f"{stem}.pdf"])
paths.extend([ROOT/"paper/manuscript.md",ROOT/"src/spiral_ln/paper.py",ROOT/"output/pdf/connector_calculus.pdf"])
records={p.relative_to(ROOT).as_posix():{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(paths)}
payload={"schema":"spiral-adversarial-followup-manifest-v1","generated_utc":datetime.now(timezone.utc).isoformat(),
         "baseline_commit":"a0a3140","originals_modified":True,
         "original_modification_scope":"User-requested paper attribution and PDF author metadata only; patent attribution and scientific content retained.",
         "followup_title":"Liquidity on Trial","paper_pages":13,"critique_pages":6,
         "evidence_scope":"exploratory sub-agent simulations and historical public testnet4 headers, not live Lightning",
         "tests_passed":104,"files":records,
         "notes":["Historical receipts retained including explicitly documented corrections.",
                  "Hash-seed-1 final inference output is authoritative; earlier dialogue values are historical.",
                  "This manifest demonstrates byte integrity, not scientific truth or author approval."]}
(ROOT/"audit/bundle_manifest.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"files":len(records),"bytes":sum(r["bytes"] for r in records.values())}))

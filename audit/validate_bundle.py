"""Run retained tests and post-review evidence checks without changing originals."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,default=Path("C:/projects/Spiral"))
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONHASHSEED="1",
             PYTHONPATH=os.pathsep.join([str(args.source_root/"src"),str(root)]))
    command=[sys.executable,"-m","pytest",str(args.source_root/"tests"),str(root/"test_resource_model.py"),
             str(root/"algebra/test_transactional.py"),str(root/"inference/test_audit.py"),"-q","-p","no:cacheprovider"]
    completed=subprocess.run(command,env=env,text=True,capture_output=True)
    print(completed.stdout)
    if completed.returncode:
        raise RuntimeError(completed.stderr or completed.stdout)
    from resource_model import ResourceChannel,ResourceLedger
    state=ResourceLedger({"c":ResourceChannel(100,100)})
    before=asdict(state)
    try:
        state.prepare("float-direction",[("c",1.0,10)])
        raise AssertionError("float direction was accepted")
    except ValueError:
        assert asdict(state)==before
    inference=json.loads((root/"inference/receipt.json").read_text())
    attribution_corrections=[]
    for path,expected in inference["inputs"].items():
        if digest(path)==expected:
            continue
        # Retain the historical receipt. Accept only the user-requested author
        # correction if reversing that one edit exactly restores its digest.
        candidate=Path(path).read_text(encoding="utf-8")
        if Path(path).name=="manuscript.md" and candidate.count("**Authors:** Dugan")==1:
            restored=candidate.replace("**Authors:** Dugan", "**Authors:** Rubio, Dugan, and Pizarro",1)
            variants=(restored.encode(),restored.replace("\n","\r\n").encode())
            if any(hashlib.sha256(value).hexdigest()==expected for value in variants):
                attribution_corrections.append(path)
                continue
        raise AssertionError(f"Original source/input changed beyond authorized attribution: {path}")
    assert digest(root/"inference/results.json")==inference["results_sha256"]
    for path,expected in json.loads((root/"inference/bundle_receipt.json").read_text())["files"].items():
        assert digest(root/"inference"/path)==expected, path
    testnet=json.loads((root/"testnet4/results/summary.json").read_text())
    csv_path=root/"testnet4/results/headers.csv"
    assert digest(csv_path)==testnet["headers_csv_sha256"]
    with csv_path.open(newline="") as stream:
        rows=list(csv.DictReader(stream))
    for row in rows:
        header=bytes.fromhex(row["header_hex"])
        actual=hashlib.sha256(hashlib.sha256(header).digest()).digest()[::-1].hex()
        assert actual==row["hash"]
    assert all(b["previous"]==a["hash"] for a,b in zip(rows,rows[1:]))
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),"status":"passed",
            "command":command,"test_output":completed.stdout.strip(),
            "original_input_hashes_verified":len(inference["inputs"])-len(attribution_corrections),
            "attribution_only_corrections_verified":attribution_corrections,
            "inference_bundle_hashes_verified":len(json.loads((root/"inference/bundle_receipt.json").read_text())["files"]),
            "post_review_float_direction":"rejected_without_mutation",
            "resource_model_sha256":digest(root/"resource_model.py"),
            "headers_verified":len(rows),"internal_parent_links":len(rows)-1,
            "historical_erratum":"original summary check label says512 links; correct511 internal links for512 headers",
            "historical_cross_review":"pre-guard resource hash retained in algebra/cross_examination.json",
            "validation_script_sha256":digest(__file__)}
    (root/"validation.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","original_input_hashes_verified","post_review_float_direction","headers_verified","internal_parent_links")},indent=2))


if __name__=="__main__":
    main()

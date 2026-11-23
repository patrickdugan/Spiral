#!/usr/bin/env python3
"""Publish run verdicts as GitHub notice annotations (at most 10 per step).

Job logs and artifacts need authentication to read; check-run annotations
of a public repository do not.
"""
import json
import sys
from pathlib import Path


def emit(lines):
    for line in lines[:10]:
        print("::notice title=private-signet::" + line.replace("%", "%25").replace("\n", " "))


def signet(receipts: Path):
    rows = {}
    for f in sorted(receipts.glob("*.json")):
        d = json.loads(f.read_text())
        rows.setdefault(d.get("kind"), []).append(d)
    out = []
    for m in rows.get("mining", []):
        out.append(f"mined {m['blocks_requested']} -> height {m['height']} tip {m['tip']} rc={m['returncode']} {m['elapsed_seconds']}s")
    out = out[:3]
    for a in rows.get("agreement", [])[-1:]:
        out.append(f"agree={a['agree']} height={a['height']} chainwork={a['chainwork']['miner']} genesis={a['genesis']['miner']} versions={a['versions']}")
    for w in rows.get("wallet-transaction", []):
        out.append(f"wallet tx {w['txid']} block {w['block']} confirmed_on_both={w['confirmed_on_both']}")
    for d in rows.get("signet-vanilla-dlc", []):
        out.append(f"vanilla DLC funding {d['funding_txid']} CET {d['cet_txid']} block {d['settlement_block']} "
                   f"confirmed_on_both={d['confirmed_on_both']} weight={d['cet_weight']} mempool={d['testmempoolaccept']['miner'][0].get('allowed')}")
    for t in rows.get("signet-dlc-ownership-rollover", []):
        out.append(
            f"rollover={t['rollover_txid']} height={t['rollover_height']} "
            f"former_owner_rejected={all(not x.get('allowed') for x in t['old_cet_rejected_after_rollover'].values())} "
            f"buyer_cet={t['buyer_cet_txid']} buyer_confirmed={t['confirmed_new_owner_payout']}"
        )
    emit(out or ["no receipts"])


def ab(path: Path):
    r = json.loads(path.read_text())
    t = r["trials"]
    out = [f"{len(t)} trials, {len(r['mismatches'])} mismatches; nodes " +
           ", ".join(f"{k}={v['version']}" for k, v in r["nodes"].items())]
    by = {}
    for row in t:
        key = (row["arm"], tuple(row["accepted"].values()))
        by.setdefault(key, []).append(row["case"])
    for (arm, verdict), cases in sorted(by.items()):
        tag = "/".join("A" if v else "r" for v in verdict)
        out.append(f"{arm} new/old-flag/old-stock={tag}: " + "; ".join(cases)[:900])
    emit(out)


if __name__ == "__main__":
    {"signet": signet, "ab": ab}[sys.argv[1]](Path(sys.argv[2]))

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


def keyless(receipts: Path):
    out = []
    k4_files = sorted(receipts.glob("*signet-keyless-k4.json"))
    for f in sorted(receipts.glob("*.json")):
        d = json.loads(f.read_text())
        if d.get("kind") == "signet-keyless-k4" and f != k4_files[-1]:
            continue   # report the latest K4 run only
        if d.get("kind") == "mining":
            out.append(f"mined {d['blocks_requested']} -> height {d['height']} tip {d['tip']} rc={d['returncode']}")
        elif d.get("kind") == "signet-keyless-k4":
            k4, c1, k3 = d["k4"], d["c1"], d["k3"]
            out.append(f"K4 arm B settlement {k4['txid']} in signed block {k4['block']} accepted_by_all={k4['accepted_by_all']} "
                       f"mempool={ {n: v.get('reject-reason') for n, v in d['k4_mempool'].items()} } versions={d['versions']}")
            out.append(f"C1 forbidden spend {c1['txid']} block {c1['block']}: "
                       + ", ".join(f"{n}={(t or {}).get('status')}" for n, t in c1.get('chaintips', {}).items())
                       + f"; legacy_forked={c1['legacy_forked']} patched_rejected={c1['patched_rejected']}")
            out.append(f"K3 bare TXCOMMIT theft {k3['txid']} in {k3['block']} on all nodes="
                       f"{all(u is not None for u in k3['thief_utxo'].values())}; agreement={d['agreement']}")
    emit(out[:2] + out[-3:] if len(out) > 5 else out or ["no receipts"])


if __name__ == "__main__":
    {"signet": signet, "ab": ab, "keyless": keyless}[sys.argv[1]](Path(sys.argv[2]))

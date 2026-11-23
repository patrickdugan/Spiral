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
    """One line per arm (GitHub keeps 10 notices per step)."""
    r = json.loads(path.read_text())
    t = r["trials"]
    out = [f"{len(t)} trials, {len(r['mismatches'])} mismatches; nodes " +
           ", ".join(f"{k}={v['version']}" for k, v in r["nodes"].items())]
    arms = {}
    for row in t:
        tag = "/".join("A" if v else "r" for v in row["accepted"].values())
        arms.setdefault(row["arm"], {}).setdefault(tag, []).append(row["case"])
    for arm, groups in arms.items():
        out.append(f"{arm} (new/old-flag/old-stock): " + " | ".join(
            f"{tag} x{len(cases)}: " + "; ".join(cases) for tag, cases in sorted(groups.items()))[:1000])
    emit(out)


def keyless(receipts: Path):
    out, mining = [], []
    k4_files = sorted(receipts.glob("*signet-keyless-k4.json"))
    for f in sorted(receipts.glob("*.json")):
        d = json.loads(f.read_text())
        if d.get("kind") == "signet-keyless-k4" and f != k4_files[-1]:
            continue   # report the latest K4 run only
        if d.get("kind") == "mining":
            mining.append(f"mined {d['blocks_requested']} -> height {d['height']} tip {d['tip']} rc={d['returncode']}")
        elif d.get("kind") == "signet-shz-k1":
            t, s, x = d["transfer"], d["split"], d["double_sale"]
            out.append(f"SHZ-K1 transfer to carol {t['txid']} outputs={t['outputs']} vsize={t['vsize']} in {t['block']} "
                       f"accepted_by_all={t['accepted_by_all']}; double sale rejected_everywhere={x['rejected_everywhere']}")
            out.append(f"SHZ-K1 1-sat shave block {s['block']}: "
                       + ", ".join(f"{n}={(c or {}).get('status')}" for n, c in s["chaintips"].items())
                       + f"; legacy_forked={s['legacy_forked']} patched_rejected={s['patched_rejected']}; agreement={d['agreement']}")
        elif d.get("kind") == "signet-keyless-k4":
            k4, c1, k3 = d["k4"], d["c1"], d["k3"]
            out.append(f"K4 arm B settlement {k4['txid']} in signed block {k4['block']} accepted_by_all={k4['accepted_by_all']} "
                       f"mempool={ {n: v.get('reject-reason') for n, v in d['k4_mempool'].items()} } versions={d['versions']}")
            out.append(f"C1 forbidden spend {c1['txid']} block {c1['block']}: "
                       + ", ".join(f"{n}={(t or {}).get('status')}" for n, t in c1.get('chaintips', {}).items())
                       + f"; legacy_forked={c1['legacy_forked']} patched_rejected={c1['patched_rejected']}")
            out.append(f"K3 bare TXCOMMIT theft {k3['txid']} in {k3['block']} on all nodes="
                       f"{all(u is not None for u in k3['thief_utxo'].values())}; agreement={d['agreement']}")
            if d.get("armC"):
                c = d["armC"]
                out.append(f"arm C transfer to carol {c['transfer_txid']} in {c['transfer_block']} accepted_by_all="
                           f"{c['accepted_by_all']}; double sale {c['double_sale_txid']}: "
                           + ", ".join(f"{n}={v['result'][:40]}" for n, v in c["double_sale_verdicts"].items()))
    emit(mining[:2] + out or ["no receipts"])


def shz(receipts: Path):
    out = []
    for f in sorted(receipts.glob("*signet-shz-prototype.json")):
        d = json.loads(f.read_text())
        out.append(f"SHZ prototype on private Signet: funding {d['funding_txid']} clearing {d['clearing_txid']} "
                   f"vsize={d['clearing_vsize']} block {d['settlement_block']} confirmations={d['confirmations']}")
        out.append("clearing outputs " + ", ".join(f"{o['sats']} sats unspent on {len(o['unspent_on'])}" for o in d["clearing_outputs"])
                   + "; probes " + ", ".join(f"{p['probe_id']}={p['core_reject_reason']}" for p in d["probes"])
                   + f"; agreement={d['agreement']}")
    emit(out or ["no receipts"])


if __name__ == "__main__":
    {"signet": signet, "ab": ab, "keyless": keyless, "shz": shz}[sys.argv[1]](Path(sys.argv[2]))

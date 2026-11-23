#!/usr/bin/env python3
"""SHZ-K1 trials: SatsHedgeZero trade 1 as a keyless numeric DLC on regtest.

Same three validators and block-per-trial method as run_ab_regtest.py:
  new        patched Core (Keyless + Signet + CSFS patches), -keylessresearch=1
  old-flag   same binary, stock rules
  old-stock  unmodified Bitcoin Core

Contract: the SHZ prototype's live trade 1 (Alice long $1 at 2x, Bob short
$1 at 1.25x, entry $80,000; margins 625 + 1,000 sats), 20-bit oracle price,
compress_cet_ranges(spec, 20, 1) -> 949 CET leaves + 1 keyless refund leaf.
Settlement price $125,000 (the prototype's clearing mark): long 1,075 /
short 550 sats.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import secp  # noqa: E402
from arms import Parties  # noqa: E402
from nodes import Faucet, Node, coinbase_coin  # noqa: E402
from run_ab_regtest import ALL, FORK, Lab  # noqa: E402
from shz_k1 import DigitOracle, K1Contract  # noqa: E402
from shz_margin import InverseContractSpec  # noqa: E402
from txlib import TxOut  # noqa: E402

EVENT_ID = "SHZ/BTCUSD/2026-11-24T00:00Z"
NUM_BITS, MAX_ERR, FEE = 20, 1, 1_000
SETTLE_PRICE = 125_000


def fixture():
    p = Parties.fixture("shz-k1-v1")
    oracle = DigitOracle("shz-k1-v1", EVENT_ID, NUM_BITS)
    spec = InverseContractSpec(usd_notional=1, entry_price_usd=80_000, long_margin_sats=625, short_margin_sats=1_000)
    k1 = K1Contract(spec, oracle, p.x("alice"), p.x("bob"), label="shz-k1-v1/trade1",
                    max_error_sats=MAX_ERR, fee_sats=FEE)
    return p, oracle, spec, k1


def run(args) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="shz-k1-regtest-"))
    nodes = [Node("new", args.patched, tmp / "new", ["-keylessresearch=1"]),
             Node("old-flag", args.patched, tmp / "oldflag"),
             Node("old-stock", args.stock, tmp / "oldstock")]
    try:
        for n in nodes:
            n.start()
        lab = Lab(nodes)
        faucet = Faucet("shz-k1-faucet")

        def advance(count: int) -> None:
            for b in lab.new.rpc("generatetoaddress", count, faucet.address):
                raw = lab.new.rpc("getblock", b, 0)
                for n in nodes[1:]:
                    if n.rpc("submitblock", raw) is not None:
                        raise RuntimeError(f"{n.name} refused block {b}")

        advance(110)
        p, oracle, spec, k1 = fixture()
        coin = coinbase_coin(lab.new, lab.new.rpc("getblockhash", 1))
        funding = faucet.spend(coin, [TxOut(k1.funding_sats, k1.spk),
                                      TxOut(coin["value"] - k1.funding_sats - 5_000, faucet.spk)])
        funding_block = lab.extend([funding], "funding")
        F, V = funding.txid, 0

        att = oracle.attest(SETTLE_PRICE)
        i125 = k1.leaf_for_price(SETTLE_PRICE)
        x = p.x
        self_long, self_short = k1.assign(p.alice, x("alice")), k1.assign(p.bob, x("bob"))
        to_carol = k1.assign(p.alice, x("carol"))
        to_second = k1.assign(p.alice, x("mallory"))
        short_to_mallory = k1.assign(p.bob, x("mallory"))
        own = {"long": (x("alice"), self_long), "short": (x("bob"), self_short)}

        honest = k1.spend(F, V, i125, own, att)
        lab.trial("K1", "settle $125k: alice 1075 / bob 550", honest, ALL(True))
        lab.trial("K1", "transfer long to carol (no Bob)",
                  k1.spend(F, V, i125, {**own, "long": (x("carol"), to_carol)}, att), ALL(True),
                  "one owner signature, valid for every price range")
        lab.trial("K1", "transfer short to mallory (no Alice)",
                  k1.spend(F, V, i125, {**own, "short": (x("mallory"), short_to_mallory)}, att), ALL(True))
        lab.trial("K1", "double sale: long also assigned to 2nd buyer",
                  k1.spend(F, V, i125, {**own, "long": (x("mallory"), to_second)}, att), ALL(True),
                  "both assignments are valid until one settles")
        for price, label in ((50_000, "$50k: long liquidated, short-only output"),
                             (500_000, "$500k: short liquidated, long-only output")):
            lab.trial("K1", label, k1.spend(F, V, k1.leaf_for_price(price), own, oracle.attest(price)), ALL(True))

        # Negative controls (soft-fork restrictions: new rejects, old rules accept).
        shaved = {"long": 1_075 - 1, "short": 550 + 1}
        lab.trial("K1", "1-sat shave of long payout, stale witness",
                  k1.spend(F, V, i125, own, att, amounts=shaved, witness_for=honest), FORK)
        lab.trial("K1", "1-sat shave of long payout, fresh witness",
                  k1.spend(F, V, i125, own, att, amounts=shaved), FORK, "TXCOMMIT matches, leaf amounts do not")
        lab.trial("K1", "$100k attestation on the $125k leaf",
                  k1.spend(F, V, i125, own, oracle.attest(100_000)), FORK)
        forged = list(att)
        forged[5] = bytes([forged[5][0] ^ 1]) + forged[5][1:]
        lab.trial("K1", "forged digit 5 scalar", k1.spend(F, V, i125, own, forged), FORK)
        j = 3
        bit = (SETTLE_PRICE >> (NUM_BITS - 1 - j)) & 1
        other_nonce = secp.sign(oracle.d, oracle.msg(j, bit))   # valid BIP340, unannounced nonce
        swapped = list(att)
        swapped[j] = other_nonce[32:]
        lab.trial("K1", "digit 3 signed under an unannounced nonce", k1.spend(F, V, i125, own, swapped), FORK,
                  "the leaf pins R_j, as SHZ's announcement does")
        lab.trial("K1", "mallory paid, carol's assignment presented",
                  k1.spend(F, V, i125, {**own, "long": (x("mallory"), to_carol)}, att,
                           proof_recipients={"long": (x("carol"), to_carol)}), FORK)
        lab.trial("K1", "mallory paid with carol's assignment",
                  k1.spend(F, V, i125, {**own, "long": (x("mallory"), to_carol)}, att), FORK)
        lab.trial("K1", "long assignment signed by Bob",
                  k1.spend(F, V, i125, {**own, "long": (x("carol"), k1.assign(p.bob, x("carol")))}, att), FORK)
        other_cid = hashlib.sha256(b"another SHZ contract").digest()
        lab.trial("K1", "assignment replayed from another contract",
                  k1.spend(F, V, i125, {**own, "long": (x("carol"), k1.assign(p.alice, x("carol"), other_cid))}, att), FORK)
        refund = len(k1.leaves) - 1
        lab.trial("K1", "refund before CSV 144", k1.spend(F, V, refund, own, []), ALL(False),
                  "nSequence 144 is a BIP68 relative lock: consensus on every node, script aside")

        advance(k1.refund_csv)
        lab.trial("K1", "keyless refund after CSV 144: 625 / 1000", k1.spend(F, V, refund, own, []), ALL(True),
                  "no oracle attestation, no party key; margins return to assigned recipients")
        lab.trial("K1", "refund pays carol (long transferred)",
                  k1.spend(F, V, refund, {**own, "long": (x("carol"), to_carol)}, []), ALL(True))
        lab.trial("K1", "refund with 1-sat shave", k1.spend(F, V, refund, own, [],
                                                         amounts={"long": 626, "short": 999}), FORK)

        info = {n.name: {"version": n.version(), "cmdline": n.cmdline[:1] + n.cmdline[2:]} for n in nodes}
        leaf = k1.leaves[i125]
        return {
            "experiment": "SHZ-K1: SatsHedgeZero trade 1 as a keyless numeric DLC (TXCOMMIT + CAT + P2MR + CSFS)",
            "nodes": info, "funding_txid": F, "funding_block": funding_block,
            "contract": {"usd_notional": spec.usd_notional, "entry_price_usd": spec.entry_price_usd,
                         "long_margin_sats": spec.long_margin_sats, "short_margin_sats": spec.short_margin_sats,
                         "long_liquidation_usd": spec.long_liquidation_price_usd(),
                         "short_liquidation_usd": spec.short_liquidation_price_usd(),
                         "num_bits": NUM_BITS, "max_error_sats": MAX_ERR, "fee_sats": FEE} | k1.summary(),
            "oracle": oracle.announcement(),
            "settle_price_usd": SETTLE_PRICE,
            "settle_leaf": {"index": i125, "prefix_bits": list(leaf.cet.prefix_bits),
                            "range_usd": [leaf.cet.min_price_usd, leaf.cet.max_price_usd],
                            "payout": {"long": leaf.cet.payout.long_sats, "short": leaf.cet.payout.short_sats},
                            "script_bytes": len(leaf.script), "control_bytes": len(k1.control(i125))},
            "trials": lab.trials,
            "mismatches": [t for t in lab.trials if not t["matches_expectation"]],
        }
    finally:
        for n in nodes:
            n.stop()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--patched", type=Path, required=True)
    ap.add_argument("--stock", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    t0 = time.time()
    report = run(args)
    report["seconds"] = round(time.time() - t0, 1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"trials": len(report["trials"]), "mismatches": len(report["mismatches"]),
                      "seconds": report["seconds"], "output": str(args.output)}))
    sys.exit(1 if report["mismatches"] else 0)


if __name__ == "__main__":
    main()

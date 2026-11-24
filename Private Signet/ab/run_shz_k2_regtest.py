#!/usr/bin/env python3
"""SHZ-K2 trials: exclusive keyless transfer, netted book settlement, FROST oracle.

Validators and method as run_ab_regtest.py (new / old-flag / old-stock; one
block per trial, rolled back). Setup steps that later trials build on (a
confirmed transfer, the CSV delay) are mined on every node.

Oracle: SatsHedgeZero's t-of-n FROST construction (shz_frost.py), 3-of-5.
Contracts:
  K2   SHZ trade 1 (Alice long $1 2x vs Bob short $1 1.25x @ $80,000)
  BOOK SHZ's 3-trade triangle ($80k / $100k / $125k entries) as ONE output
       paying netted per-party totals; at $125,000 that is the prototype's
       clearing: Alice 1,475, Bob 1,250, Carol 825.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from arms import Parties  # noqa: E402
from nodes import Faucet, Node, coinbase_coin  # noqa: E402
from run_ab_regtest import ALL, FORK, Lab  # noqa: E402
from shz_frost import FrostOracle  # noqa: E402
from shz_k2 import Coin, book, single_trade  # noqa: E402
from shz_margin import BookTrade, InverseContractSpec  # noqa: E402
from txlib import TxOut  # noqa: E402

EVENT_ID = "SHZ/BTCUSD/2026-11-24T00:00Z"
NUM_BITS, MAX_ERR, SETTLE_FEE, TRANSFER_FEE = 20, 1, 1_000, 500
PRICE = 125_000
TRADE1 = InverseContractSpec(1, 80_000, 625, 1_000)
TRIANGLE = [BookTrade(TRADE1, "alice", "bob"),
            BookTrade(InverseContractSpec(1, 100_000, 500, 625), "bob", "carol"),
            BookTrade(InverseContractSpec(1, 125_000, 400, 400), "carol", "alice")]


def fixture():
    p = Parties.fixture("shz-k2-v1")
    oracle = FrostOracle("shz-k2-v1", EVENT_ID, NUM_BITS, t=3, n=5)
    k2 = single_trade(oracle, TRADE1, max_error_sats=MAX_ERR, settle_fee=SETTLE_FEE, transfer_fee=TRANSFER_FEE)
    bk = book(oracle, TRIANGLE, ["alice", "bob", "carol"], max_error_sats=MAX_ERR, settle_fee=SETTLE_FEE,
              transfer_fee=TRANSFER_FEE)
    return p, oracle, k2, bk


def run(args) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="shz-k2-regtest-"))
    nodes = [Node("new", args.patched, tmp / "new", ["-keylessresearch=1"]),
             Node("old-flag", args.patched, tmp / "oldflag"),
             Node("old-stock", args.stock, tmp / "oldstock")]
    try:
        for n in nodes:
            n.start()
        lab = Lab(nodes)
        faucet = Faucet("shz-k2-faucet")

        def advance(count: int) -> None:
            for b in lab.new.rpc("generatetoaddress", count, faucet.address):
                raw = lab.new.rpc("getblock", b, 0)
                for n in nodes[1:]:
                    if n.rpc("submitblock", raw) is not None:
                        raise RuntimeError(f"{n.name} refused block {b}")

        advance(110)
        p, oracle, k2, bk = fixture()
        x = p.x
        A, B, C, M = x("alice"), x("bob"), x("carol"), x("mallory")
        v_single = TRADE1.total_collateral_sats + SETTLE_FEE + 2 * TRANSFER_FEE      # two transfers budgeted
        v_book = sum(t.spec.total_collateral_sats for t in TRIANGLE) + SETTLE_FEE + 2 * TRANSFER_FEE
        coin_cb = coinbase_coin(lab.new, lab.new.rpc("getblockhash", 1))
        funding = faucet.spend(coin_cb, [TxOut(v_single, k2.spk([A, B])), TxOut(v_book, bk.spk([A, B, C])),
                                         TxOut(coin_cb["value"] - v_single - v_book - 5_000, faucet.spk)])
        funding_block = lab.extend([funding], "funding")
        c0 = Coin(funding.txid, 0, v_single, [A, B])
        cb = Coin(funding.txid, 1, v_book, [A, B, C])

        att = oracle.attest(PRICE, [1, 2, 3])
        i125 = k2.index("cet", price=PRICE)
        honest = k2.payout(c0, i125, att)

        # --- single trade: settlement, oracle quorum, owner binding ---------
        lab.trial("K2", "settle $125k to state owners alice/bob", honest, ALL(True))
        lab.trial("K2", "FROST quorum 2,4,5 attests", k2.payout(c0, i125, oracle.attest(PRICE, [2, 4, 5])), ALL(True))
        lab.trial("K2", "FROST: only 2 of 5 signers", k2.payout(c0, i125, oracle.attest(PRICE, [1, 2])), FORK)
        lab.trial("K2", "$100k attestation on the $125k leaf", k2.payout(c0, i125, oracle.attest(100_000)), FORK)
        lab.trial("K2", "1-sat shave of long payout", k2.payout(c0, i125, att, amounts=[1_074, 551]), FORK)
        lab.trial("K2", "pays mallory instead of the long owner", k2.payout(c0, i125, att, pay_keys=[M, B]), FORK)
        lab.trial("K2", "witness claims carol owns long (state says alice)",
                  k2.payout(c0, i125, att, claimed_keys=[C, B]), FORK, "the recomputed spk differs from the coin's")

        # --- transfer rules ---------------------------------------------------
        to_carol, c1 = k2.transfer(c0, "long", C, p.alice)
        lab.trial("K2", "transfer long alice -> carol (no Bob)", to_carol, ALL(True))
        lab.trial("K2", "transfer of alice's position signed by bob", k2.transfer(c0, "long", C, p.bob)[0], FORK)
        lab.trial("K2", "transfer also swaps bob's key for mallory",
                  k2.transfer(c0, "long", C, p.alice, out_keys=[C, M])[0], FORK)
        lab.trial("K2", "transfer takes 1000 sats extra fee",
                  k2.transfer(c0, "long", C, p.alice, out_value=c0.value - TRANSFER_FEE - 1_000)[0], FORK)
        lab.trial("K2", "refund before CSV 144", k2.payout(c0, k2.index("refund"), []), ALL(False),
                  "BIP68 relative lock: consensus on every node")

        lab.extend([to_carol], "transfer to carol")
        lab.trial("K2", "second sale: alice transfers the spent coin to mallory",
                  k2.transfer(c0, "long", M, p.alice)[0], ALL(False), "the coin no longer exists")
        lab.trial("K2", "old owner alice transfers the new coin",
                  k2.transfer(c1, "long", M, p.alice, claimed_keys=[A, B])[0], FORK)
        lab.trial("K2", "old owner alice signs as if she were carol",
                  k2.transfer(c1, "long", M, p.alice)[0], FORK, "CHECKSIG against the state key")
        lab.trial("K2", "settle new coin: carol 1075 / bob 550", k2.payout(c1, i125, att), ALL(True))
        lab.trial("K2", "settle new coin to old owner alice",
                  k2.payout(c1, i125, att, claimed_keys=[A, B]), FORK)
        to_dave, c2 = k2.transfer(c1, "long", M, p.carol)
        lab.extend([to_dave], "transfer carol -> mallory")
        lab.trial("K2", "third transfer would drop below settlement floor",
                  k2.transfer(c2, "long", A, p.mallory)[0], FORK, f"floor {k2.settle_floor} sats")
        lab.trial("K2", "short side: bob transfers to carol", k2.transfer(c2, "short", C, p.bob)[0], FORK,
                  "also below the floor after two transfers")

        # --- book: netted settlement and transfer of a party's book -----------
        ib = bk.index("cet", price=PRICE)
        book_tx = bk.payout(cb, ib, att)
        lab.trial("BOOK", "netted $125k: " + " / ".join(f"{p_} {a}" for p_, a in zip(bk.parties, bk.leaves[ib].amounts)),
                  book_tx, ALL(True), "one input, three outputs, no signatures")
        lab.trial("BOOK", "carol shaves alice by 1 sat",
                  bk.payout(cb, ib, att, amounts=[bk.leaves[ib].amounts[0] - 1, bk.leaves[ib].amounts[1],
                                                  bk.leaves[ib].amounts[2] + 1]), FORK)
        bob_out, cb1 = bk.transfer(cb, "bob", M, p.bob)
        lab.extend([bob_out], "bob's book -> mallory")
        lab.trial("BOOK", "settle after bob's book moved to mallory", bk.payout(cb1, ib, att), ALL(True))
        lab.trial("BOOK", "bob settles after selling his book", bk.payout(cb1, ib, att, claimed_keys=[A, B, C]), FORK)

        advance(k2.refund_csv)
        lab.trial("K2", "keyless refund after CSV to current owners", k2.payout(c2, k2.index("refund"), []), ALL(True))
        lab.trial("K2", "refund to former owner alice",
                  k2.payout(c2, k2.index("refund"), [], claimed_keys=[A, B]), FORK)
        lab.trial("BOOK", "book refund after CSV: margins per party", bk.payout(cb1, bk.index("refund"), []), ALL(True))

        info = {n.name: {"version": n.version(), "cmdline": n.cmdline[:1] + n.cmdline[2:]} for n in nodes}
        lk, lb = k2.leaves[i125], bk.leaves[ib]
        return {
            "experiment": "SHZ-K2: exclusive keyless transfer, netted book settlement, FROST 3-of-5 oracle",
            "nodes": info, "funding_txid": funding.txid, "funding_block": funding_block,
            "oracle": oracle.announcement(),
            "single": k2.summary() | {"funding_sats": v_single, "settle_leaf": {"prefix_bits": list(lk.rng.prefix_bits),
                                       "amounts": lk.amounts, "script_bytes": len(lk.script)},
                                       "settle_vsize": honest.vsize, "transfer_vsize": to_carol.vsize},
            "book": bk.summary() | {"funding_sats": v_book, "settle_leaf": {"prefix_bits": list(lb.rng.prefix_bits),
                                     "amounts": lb.amounts, "script_bytes": len(lb.script)},
                                     "settle_vsize": book_tx.vsize, "transfer_vsize": bob_out.vsize},
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

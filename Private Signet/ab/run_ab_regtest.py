#!/usr/bin/env python3
"""Matched A/B settlement trials on three isolated regtest validators.

  new        patched Core (Keyless-CHECKSIG patch) with -keylessresearch=1:
             TXCOMMIT + OP_CAT + restricted P2MR enforced in block validation
  old-flag   the same patched binary without -keylessresearch (stock rules)
  old-stock  unmodified Bitcoin Core (stock rules, independent build)

Every trial is ONE hand-built block (same bytes) submitted to every node with
submitblock. Accepted trial blocks are invalidated afterwards so the next
trial starts from the same tip. Nodes have no P2P links.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import secp  # noqa: E402
from arms import (FUNDING_SATS, OUTCOMES, PAYOUT_SATS, SETTLE_FEE_SATS, ArmA, ArmB, ArmC, CsfsProbe,  # noqa: E402
                  Parties, UnsafeUnconstrained, p2tr_key_spk, keyless_leaf)
from nodes import Faucet, Node, build_block, coinbase_coin, submit_all  # noqa: E402
from txlib import Tx, TxIn, TxOut, ref  # noqa: E402


class Lab:
    def __init__(self, nodes: list[Node]):
        self.nodes = nodes
        self.new = nodes[0]
        self.trials: list[dict] = []
        self.n = 0

    def tips(self) -> dict:
        return {n.name: n.rpc("getbestblockhash") for n in self.nodes}

    def extend(self, txs: list[Tx], label: str) -> str:
        """Append a block every node must accept (setup steps)."""
        self.n += 1
        block, bhash = build_block(self.new, txs, b"ab-setup-%d" % self.n)
        res = submit_all(self.nodes, block)
        if any(v["result"] != "accepted" for v in res.values()):
            raise RuntimeError(f"setup block {label} refused: {res}")
        return bhash

    def trial(self, arm: str, case: str, tx: Tx, expect: dict, note: str = "") -> dict:
        """Submit one candidate in its own block to all nodes, then roll back."""
        self.n += 1
        before = self.tips()
        block, bhash = build_block(self.new, [tx], b"ab-trial-%d" % self.n)
        res = submit_all(self.nodes, block)
        for n in self.nodes:
            if res[n.name]["result"] == "accepted":
                n.rpc("invalidateblock", bhash)
        if self.tips() != before:
            raise RuntimeError(f"trial {case} did not roll back cleanly")
        verdict = {k: v["result"] == "accepted" for k, v in res.items()}
        row = {"arm": arm, "case": case, "txid": tx.txid, "weight": tx.weight, "vsize": tx.vsize,
               "witness_bytes": sum(len(w) for w in tx.vin[0].witness),
               "accepted": verdict, "reasons": {k: v["result"] for k, v in res.items()},
               "submit_ms": {k: v["ms"] for k, v in res.items()}, "expected": expect,
               "matches_expectation": all(verdict[k] == v for k, v in expect.items()), "note": note,
               "raw_tx": tx.hex()}
        self.trials.append(row)
        flag = "ok " if row["matches_expectation"] else "BAD"
        print(f"[{flag}] {arm:<3} {case:<44} " + " ".join(f"{k}={'A' if v else 'r'}" for k, v in verdict.items()), flush=True)
        return row


ALL = lambda v: {"new": v, "old-flag": v, "old-stock": v}  # noqa: E731
FORK = {"new": False, "old-flag": True, "old-stock": True}   # soft-fork restriction


def run(args) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="ab-regtest-"))
    research = [] if args.mechanics_only else ["-keylessresearch=1"]
    nodes = [Node("new", args.patched, tmp / "new", research),
             Node("old-flag", args.patched, tmp / "oldflag"),
             Node("old-stock", args.stock, tmp / "oldstock")]
    try:
        for n in nodes:
            n.start()
        lab = Lab(nodes)
        faucet = Faucet()
        blocks = lab.new.rpc("generatetoaddress", 110, faucet.address)
        for b in blocks:
            raw = lab.new.rpc("getblock", b, 0)
            for n in nodes[1:]:
                if n.rpc("submitblock", raw) is not None:
                    raise RuntimeError(f"{n.name} refused prefix block")
        p = Parties.fixture()
        arm_a, arm_b = ArmA(p), ArmB(p)
        unsafe_k3 = UnsafeUnconstrained()
        no_oracle = ArmB(p, oracle_gate=False)
        bad_builder = ArmB(p, allow={"ALICE_WINS": ("alice", "mallory"), "BOB_WINS": ("bob", "mallory")})
        fund_outputs = [TxOut(FUNDING_SATS, arm_a.funding_spk), TxOut(FUNDING_SATS, arm_a.funding_spk),
                        TxOut(FUNDING_SATS, arm_b.funding_spk), TxOut(FUNDING_SATS, arm_b.funding_spk),
                        TxOut(FUNDING_SATS, unsafe_k3.funding_spk), TxOut(FUNDING_SATS, no_oracle.funding_spk),
                        TxOut(FUNDING_SATS, bad_builder.funding_spk)]
        arm_c = ArmC(p) if args.csfs else None
        probe_msg = hashlib.sha256(b"csfs probe").digest()
        probes = {}
        if arm_c:
            probes = {"bip340": CsfsProbe(probe_msg, p.x("alice")),
                      "msg31": CsfsProbe(probe_msg[:31], p.x("alice")),
                      "unknown_key": CsfsProbe(probe_msg, b"\x02" + p.x("alice"))}
            fund_outputs += [TxOut(FUNDING_SATS, arm_c.funding_spk)] + \
                            [TxOut(FUNDING_SATS, pr.funding_spk) for pr in probes.values()]
        coin = coinbase_coin(lab.new, blocks[0])
        change = coin["value"] - FUNDING_SATS * len(fund_outputs) - 5_000
        funding = faucet.spend(coin, fund_outputs + [TxOut(change, faucet.spk)])
        funding_block = lab.extend([funding], "funding")
        F = funding.txid
        A1, A2, B1, B2, K3, NO, BB, C1, PR_SIG, PR_31, PR_UNK = range(11)
        s_alice, s_bob = p.oracle.attest("ALICE_WINS"), p.oracle.attest("BOB_WINS")

        # --- Arm A ----------------------------------------------------------
        pre = arm_a.presign_all(F, A1)
        honest_a = arm_a.settle(pre, "ALICE_WINS", s_alice)
        sigs = list(honest_a.vin[0].witness)
        lab.trial("A", "settle ALICE_WINS -> alice", honest_a, ALL(True))
        lab.trial("A", "settle BOB_WINS -> bob (counterfactual outcome)", arm_a.settle(pre, "BOB_WINS", s_bob), ALL(True))

        def stale_a(**changes):
            base = honest_a
            if "vout" in changes:
                base = replace(base, vout=changes.pop("vout"))
            if "vin" in changes:
                base = replace(base, vin=changes.pop("vin"))
            return replace(base, **changes)

        lab.trial("A", "altered recipient (mallory), honest sigs", stale_a(vout=(TxOut(PAYOUT_SATS, p2tr_key_spk(p.x("mallory"))),)), ALL(False))
        lab.trial("A", "altered amount (-1000 sats)", stale_a(vout=(TxOut(PAYOUT_SATS - 1000, p2tr_key_spk(p.x("alice"))),)), ALL(False))
        lab.trial("A", "altered input outpoint (twin funding)", stale_a(vin=(replace(honest_a.vin[0], vout=A2),)), ALL(False))
        lab.trial("A", "altered version 2 -> 3", stale_a(version=3), ALL(False))
        lab.trial("A", "altered sequence", stale_a(vin=(replace(honest_a.vin[0], sequence=0xFFFFFFFE),)), ALL(False))
        lab.trial("A", "altered locktime", stale_a(locktime=1), ALL(False))
        bad_leaf = honest_a.with_witness(0, sigs[:2] + [sigs[2] + b"\x51", sigs[3]])
        lab.trial("A", "altered tapleaf script", bad_leaf, ALL(False))
        wrong = pre["ALICE_WINS"]
        bad_sigs = [secp.adaptor_complete(wrong["presig"][w], s_bob) for w in ("bob", "alice")]
        lab.trial("A", "invalid proof: decrypted with BOB_WINS attestation", wrong["tx"].with_witness(0, bad_sigs + sigs[2:]), ALL(False))
        lab.trial("A", "compromised: both funding keys sign to mallory", arm_a.forge_with_keys(F, A1, p.x("mallory")), ALL(True),
                  "setup-key compromise redirects funds under every rule set")

        # --- Arm B ----------------------------------------------------------
        honest_b = arm_b.settlement(F, B1, "ALICE_WINS", "alice", s_alice)
        lab.trial("B", "settle ALICE_WINS -> alice", honest_b, ALL(True))
        lab.trial("B", "settle ALICE_WINS -> carol (selected at settlement)", arm_b.settlement(F, B1, "ALICE_WINS", "carol", s_alice), ALL(True))
        lab.trial("B", "settle BOB_WINS -> bob (counterfactual outcome)", arm_b.settlement(F, B1, "BOB_WINS", "bob", s_bob), ALL(True))
        st = dict(witness_for=honest_b)
        lab.trial("B", "altered recipient (mallory), stale witness", arm_b.settlement(F, B1, "ALICE_WINS", "mallory", s_alice, **st), FORK)
        lab.trial("B", "altered recipient (mallory), fresh witness", arm_b.settlement(F, B1, "ALICE_WINS", "mallory", s_alice), FORK)
        lab.trial("B", "altered amount (-1000), stale witness", arm_b.settlement(F, B1, "ALICE_WINS", "alice", s_alice, amount=PAYOUT_SATS - 1000, **st), FORK)
        lab.trial("B", "altered amount (-1000), fresh witness", arm_b.settlement(F, B1, "ALICE_WINS", "alice", s_alice, amount=PAYOUT_SATS - 1000), FORK,
                  "amount is a constant in the leaf; a re-derived witness cannot change it")
        lab.trial("B", "altered input outpoint, stale witness", arm_b.settlement(F, B2, "ALICE_WINS", "alice", s_alice, **st), FORK)
        lab.trial("B", "altered input outpoint, fresh witness", arm_b.settlement(F, B2, "ALICE_WINS", "alice", s_alice), ALL(True),
                  "policy does not name the outpoint: any coin with this script settles the same way")
        for field_name, kw in (("version 2 -> 3", {"version": 3}), ("sequence", {"sequence": 0xFFFFFFFE}),
                               ("locktime", {"locktime": 1})):
            lab.trial("B", f"altered {field_name}, stale witness", arm_b.settlement(F, B1, "ALICE_WINS", "alice", s_alice, **kw, **st), FORK)
            lab.trial("B", f"altered {field_name}, fresh witness", arm_b.settlement(F, B1, "ALICE_WINS", "alice", s_alice, **kw), ALL(True),
                      "field is bound to the actual tx but not constrained by policy")
        w = list(honest_b.vin[0].witness)
        lab.trial("B", "tapleaf: ALICE_WINS witness under BOB_WINS leaf", honest_b.with_witness(0, w[:-2] + [arm_b.leaves["BOB_WINS"], arm_b.controls["BOB_WINS"]]), FORK)
        lab.trial("B", "tapleaf: leaf not in the committed tree", honest_b.with_witness(0, w[:-2] + [w[-2] + b"\x51", w[-1]]), FORK)
        lab.trial("B", "invalid proof: BOB_WINS attestation on ALICE leaf", arm_b.settlement(F, B1, "ALICE_WINS", "alice", s_bob), FORK)
        lab.trial("B", "invalid proof: no attestation", arm_b.settlement(F, B1, "ALICE_WINS", "alice", None), FORK)
        digest31 = honest_b.with_witness(0, w[:-3] + [w[-3]] + w[-2:])  # unchanged control (sanity)
        lab.trial("B", "old/new: honest witness, unchanged", digest31, ALL(True))

        # --- Phase 5 fixtures -------------------------------------------------
        lab.trial("K3", "unconstrained TXCOMMIT: thief pays itself", unsafe_k3.steal(F, K3, p.x("mallory")), ALL(True),
                  "a bare TXCOMMIT check is anyone-can-spend under the new rules too")
        lab.trial("K3", "unconstrained TXCOMMIT: 31-byte digest", Tx(
            (TxIn(F, K3),), (TxOut(PAYOUT_SATS, p2tr_key_spk(p.x("mallory"))),)).with_witness(
            0, [bytes(31), unsafe_k3.leaf, unsafe_k3.control]), FORK)
        lab.trial("NO", "no oracle gate: settle before attestation", no_oracle.settlement(F, NO, "BOB_WINS", "bob", None), ALL(True),
                  "omitting the oracle check lets anyone pick the outcome")
        lab.trial("BB", "compromised builder: allowlist holds mallory", bad_builder.settlement(F, BB, "ALICE_WINS", "mallory", s_alice), ALL(True),
                  "the trust moves to whoever compiles the leaf and its allowlist")

        # --- Arm C: CSFS oracle + owner assignment + TXCOMMIT ------------------
        if arm_c:
            osig = arm_c.oracle_sig("ALICE_WINS", s_alice)
            self_assign = arm_c.assign("ALICE_WINS", "alice")
            to_carol = arm_c.assign("ALICE_WINS", "carol")
            to_dave = arm_c.assign("ALICE_WINS", "mallory")   # a second buyer
            good_c = arm_c.settlement(F, C1, "ALICE_WINS", "alice", osig, self_assign)
            lab.trial("C", "settle ALICE_WINS -> alice (owner self-assigns)", good_c, ALL(True))
            lab.trial("C", "transfer: Alice assigns to carol, no Bob", arm_c.settlement(F, C1, "ALICE_WINS", "carol", osig, to_carol), ALL(True),
                      "transfer without the counterparty; one signature from the position owner")
            lab.trial("C", "double sale: Alice also assigns to a second buyer", arm_c.settlement(F, C1, "ALICE_WINS", "mallory", osig, to_dave), ALL(True),
                      "both assignments are valid; the first settlement mined wins")
            lab.trial("C", "unassigned recipient (carol's assignment, mallory paid)",
                      arm_c.settlement(F, C1, "ALICE_WINS", "mallory", osig, to_carol, proof_payee="carol"), FORK)
            lab.trial("C", "recipient key without assignment", arm_c.settlement(F, C1, "ALICE_WINS", "mallory", osig, to_carol), FORK)
            lab.trial("C", "assignment signed by Bob (not the owner)",
                      arm_c.settlement(F, C1, "ALICE_WINS", "carol", osig, arm_c.assign("ALICE_WINS", "carol", signer="bob")), FORK)
            other_cid = hashlib.sha256(b"another contract").digest()
            lab.trial("C", "assignment replayed from another contract",
                      arm_c.settlement(F, C1, "ALICE_WINS", "carol", osig, arm_c.assign("ALICE_WINS", "carol", cid=other_cid)), FORK)
            lab.trial("C", "BOB_WINS attestation on ALICE leaf",
                      arm_c.settlement(F, C1, "ALICE_WINS", "alice", arm_c.oracle_sig("ALICE_WINS", s_bob), self_assign), FORK)
            lab.trial("C", "forged oracle signature", arm_c.settlement(F, C1, "ALICE_WINS", "alice", bytes(range(64)), self_assign), FORK)
            lab.trial("C", "63-byte oracle signature", arm_c.settlement(F, C1, "ALICE_WINS", "alice", osig[:63], self_assign), FORK)
            lab.trial("C", "empty oracle signature (CSFS pushes false)", arm_c.settlement(F, C1, "ALICE_WINS", "alice", b"", self_assign), FORK)
            lab.trial("C", "amount -1000, stale witness",
                      arm_c.settlement(F, C1, "ALICE_WINS", "alice", osig, self_assign, amount=PAYOUT_SATS - 1000, witness_for=good_c), FORK)
            # Plain Taproot CSFS probes: OP_SUCCESS204 on old rules.
            probe_sig = secp.sign(p.alice, probe_msg)
            lab.trial("CS", "CSFS valid BIP340 signature", probes["bip340"].spend(F, PR_SIG, probe_sig, p.x("carol")), ALL(True))
            lab.trial("CS", "CSFS wrong signature", probes["bip340"].spend(F, PR_SIG, secp.sign(p.bob, probe_msg), p.x("carol")), FORK)
            lab.trial("CS", "CSFS 63-byte signature", probes["bip340"].spend(F, PR_SIG, probe_sig[:63], p.x("carol")), FORK)
            lab.trial("CS", "CSFS empty signature (false result)", probes["bip340"].spend(F, PR_SIG, b"", p.x("carol")), FORK)
            lab.trial("CS", "CSFS 31-byte message (lab restriction)", probes["msg31"].spend(F, PR_31, probe_sig, p.x("carol")), FORK)
            lab.trial("CS", "CSFS 33-byte key type, any non-empty sig", probes["unknown_key"].spend(F, PR_UNK, b"\x01", p.x("carol")), ALL(True),
                      "unknown key types stay upgradable, as in BIP342/BIP348")

        # --- Phase 4: transfer --------------------------------------------------
        # Vanilla: Alice sells her ALICE_WINS position to Carol. Bob and Alice
        # re-sign a CET paying Carol (novation). The old CET still exists.
        novated = arm_a.presign_all(F, A1, payees={"ALICE_WINS": "carol", "BOB_WINS": "bob"})
        lab.trial("A", "transfer: novated CET pays carol", arm_a.settle(novated, "ALICE_WINS", s_alice), ALL(True),
                  "requires Bob online to re-sign")
        lab.trial("A", "transfer: superseded CET still pays alice", arm_a.settle(pre, "ALICE_WINS", s_alice), ALL(True),
                  "off-chain novation cannot revoke the old CET; Carol must trust Alice")

        info = {n.name: {"version": n.version(), "cmdline": n.cmdline[:1] + n.cmdline[2:]} for n in nodes}
        report = {
            "experiment": "Private Signet A/B: vanilla adaptor DLC vs Keyless-CHECKSIG",
            "nodes": info, "funding_txid": F, "funding_block": funding_block,
            "funding_sats_per_arm": FUNDING_SATS, "payout_sats": PAYOUT_SATS, "fee_sats": SETTLE_FEE_SATS,
            "oracle": {"P": p.oracle.P.hex(), "R": p.oracle.R.hex(),
                       "commitments": {m: p.oracle.hash_commitment(m).hex() for m in OUTCOMES}},
            "arm_a_leaf": arm_a.leaf.hex(), "arm_b_leaves": {m: l.hex() for m, l in arm_b.leaves.items()},
            "arm_b_spk": arm_b.funding_spk.hex(),
            "arm_c_leaves": {m: l.hex() for m, l in arm_c.leaves.items()} if arm_c else None,
            "trials": lab.trials,
            "mismatches": [t for t in lab.trials if not t["matches_expectation"]],
        }
        return report
    finally:
        for n in nodes:
            n.stop()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--patched", type=Path, required=True, help="bitcoind built with the Keyless patch")
    ap.add_argument("--stock", type=Path, required=True, help="unmodified bitcoind")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--csfs", action="store_true",
                    help="patched build includes core/patch_core_csfs.py: run arm C and CSFS probes")
    ap.add_argument("--mechanics-only", action="store_true",
                    help="omit -keylessresearch (harness check against stock binaries; fork rows will mismatch)")
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

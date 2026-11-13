#!/usr/bin/env python3
"""Bounded graph comparison and exact serialization accounting, Python 3.11+.

The paired validator is loaded unchanged from the pinned Spiral model. This
file implements a merged-output comparator and a separate wire decoder.
Authorization predicates and script commitments remain symbolic. Witness
envelopes measure stated byte layouts; they are not executable proof circuits.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import struct
import sys


SPIRAL_COMMIT = "76071a0195f48961386e46d56df7b5e0276637fc"
UPSTREAM_BLOB = "17c405958854f5e5e86914997ed7da7acf024c22"
BIPS_COMMIT = "b34d9f751791d4feb22feff4f2ed00bcac83961b"
VECTOR_BLOB = "4ed4ac04fd40051ba630ab17dfa736e4e5a5ee69"
SEED = 20261113
HERE = Path(__file__).resolve().parent


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_upstream(path: Path):
    raw = path.read_bytes()
    if git_blob_sha(raw) != UPSTREAM_BLOB:
        raise ValueError(f"Upstream model differs from pinned blob: {path}")
    spec = importlib.util.spec_from_file_location("sieve_paired_upstream", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_compact(raw: bytes, pos: int) -> tuple[int, int]:
    first = raw[pos]
    pos += 1
    if first < 253:
        return first, pos
    size = {253: 2, 254: 4, 255: 8}[first]
    return int.from_bytes(raw[pos:pos + size], "little"), pos + size


def decode_wire(raw: bytes) -> dict:
    """Independent decoder retains scriptSigs and witnesses from known vectors."""
    version = int.from_bytes(raw[:4], "little", signed=True)
    pos = 4
    witness = raw[pos:pos + 2] == b"\x00\x01"
    if witness:
        pos += 2
    count, pos = read_compact(raw, pos)
    inputs = []
    for _ in range(count):
        txid, n = raw[pos:pos + 32], int.from_bytes(raw[pos + 32:pos + 36], "little")
        pos += 36
        size, pos = read_compact(raw, pos)
        script_sig = raw[pos:pos + size]
        pos += size
        sequence = int.from_bytes(raw[pos:pos + 4], "little")
        pos += 4
        inputs.append({"txid": txid, "n": n, "script_sig": script_sig, "sequence": sequence})
    count, pos = read_compact(raw, pos)
    outputs = []
    for _ in range(count):
        start = pos
        value = int.from_bytes(raw[pos:pos + 8], "little")
        pos += 8
        size, pos = read_compact(raw, pos)
        script = raw[pos:pos + size]
        pos += size
        outputs.append({"value": value, "script": script, "wire": raw[start:pos]})
    stacks = [[] for _ in inputs]
    if witness:
        for index in range(len(inputs)):
            count, pos = read_compact(raw, pos)
            for _ in range(count):
                size, pos = read_compact(raw, pos)
                stacks[index].append(raw[pos:pos + size])
                pos += size
    locktime = int.from_bytes(raw[pos:pos + 4], "little")
    pos += 4
    assert pos == len(raw), "Trailing or truncated transaction bytes"
    return {"version": version, "locktime": locktime, "inputs": inputs,
            "outputs": outputs, "witnesses": stacks}


def independent_template(parsed: dict, index: int, annex: bytes | None) -> bytes:
    h = lambda data: hashlib.sha256(data).digest()
    payload = struct.pack("<iI", parsed["version"], parsed["locktime"])
    payload += h(b"".join(struct.pack("<I", item["sequence"]) for item in parsed["inputs"]))
    payload += h(b"".join(item["wire"] for item in parsed["outputs"]))
    payload += bytes([annex is not None]) + struct.pack("<I", index)
    if annex is not None:
        payload += h(compact(len(annex)) + annex)
    tag = h(b"TemplateHash")
    return h(tag + tag + payload)


def compact(n: int) -> bytes:
    if n < 253:
        return bytes([n])
    if n < 2**16:
        return b"\xfd" + n.to_bytes(2, "little")
    if n < 2**32:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def check_official_vectors(U, path: Path) -> dict:
    raw = path.read_bytes()
    assert git_blob_sha(raw) == VECTOR_BLOB, "Official vector fixture differs from pinned blob"
    rows = json.loads(raw)
    checked, upstream_checked = [], 0
    for number, row in enumerate(rows):
        parsed = decode_wire(bytes.fromhex(row["spending_tx"]))
        i = row["input_index"]
        stack = list(parsed["witnesses"][i])
        annex = stack.pop() if len(stack) >= 2 and stack[-1][:1] == b"\x50" else None
        script = stack[-2]
        assert len(script) == 35 and script[0] == 32 and script[-2:] == b"\xce\x87"
        expected = script[1:33]
        digest = independent_template(parsed, i, annex)
        assert (digest == expected) == row["valid"], (number, row["comment"])
        if annex is None:
            tx = U.Transaction(
                tuple(U.TxInput(U.OutPoint(x["txid"], x["n"]), x["sequence"]) for x in parsed["inputs"]),
                tuple(U.TxOutput(x["value"], x["script"]) for x in parsed["outputs"]),
                parsed["version"], parsed["locktime"])
            assert U.template_hash(tx, i) == digest
            upstream_checked += 1
        checked.append({"vector": number, "expected_template_result": row["valid"],
                        "matched": True, "current_input_annex": annex is not None})
    return {"known_template_conditions_matched": len(checked),
            "upstream_annex_absent_hashes_matched": upstream_checked,
            "scope": "Template-equality condition in the 19 simple official scripts; full Script and Taproot validation remain outside this run.",
            "cases": checked}


def run_graphs(U) -> tuple[dict, dict]:
    @dataclass(frozen=True)
    class CommonManifest(U.Manifest):
        def terminal_outputs(self, branch):
            original = super().terminal_outputs(branch)
            # A one-byte OP_TRUE anchor is a serialization fixture. Relay is unmodeled.
            return original[:2] + (U.TxOutput(0, b"\x51"),)

    def make_manifest(number=0, principal=1_000_000, bond=10_000, delay=20, false=True):
        key = lambda name: b"\x51\x20" + U.h(name)
        return CommonManifest(
            U.h(f"graph-{number}".encode()), U.h(f"payment-{number}".encode()),
            U.h(f"setup-{number}".encode()), principal_value=principal,
            control_value=bond, delay=delay, claim_is_false=false,
            payout_script=key(b"operator"), recovery_script=key(b"liability-safe-recovery"),
            bond_return_script=key(b"bond-return"), bond_recovery_script=key(b"bond-recovery"))

    def paired_instance(number, m, height=100, ledger=None):
        ledger = U.Ledger({}) if ledger is None else ledger
        working = ledger.copy()
        working, old = U.make_instance(number, manifest=m, height=height, ledger=working)
        # The draft includes an assertion anchor that the upstream constructor omits.
        # Add it equally to both routes, remapping the upstream instance's outpoints.
        assertion = replace(old.assertion, outputs=old.assertion.outputs + (U.TxOutput(0, b"\x51"),))
        root = assertion.txid()
        principal, control = U.OutPoint(root, 0), U.OutPoint(root, 1)
        anchor = U.OutPoint(root, 2)
        destinations = (principal, control, anchor, old.sponsor)
        U.require(len(set(destinations)) == len(destinations), "duplicate construction destinations")
        U.require(all(point not in ledger.coins for point in destinations), "instance destination already exists")
        working.coins[principal] = working.coins.pop(old.principal)
        working.coins[control] = working.coins.pop(old.control)
        working.coins[anchor] = U.Coin(assertion.outputs[2], height, "anchor")
        ledger.coins = working.coins
        return ledger, replace(old, assertion=assertion, principal=principal, control=control)

    @dataclass(frozen=True)
    class MergedWitness:
        branch: str
        evidence: object = None
        signature: bool = False
        keypath: bool = False
        annex: bytes | None = None

    def merged_template(m, branch):
        dummy = U.OutPoint(bytes(32), 0)
        sequence = m.delay if branch == "payout" else 0
        skeleton = U.Transaction((U.TxInput(dummy, sequence),), m.terminal_outputs(branch))
        return U.template_hash(skeleton, 0)

    def merged_script(m):
        return b"\x51\x20" + U.h(b"symbolic-merged-profile-v1\0" + m.graph_id
                                + m.statement_hash + m.setup_id
                                + merged_template(m, "payout") + merged_template(m, "recovery"))

    class MergedLedger(U.Ledger):
        def copy(self):
            return MergedLedger(dict(self.coins))

        def validate(self, tx, witness, height):
            coins = self.values_and_uniqueness(tx)
            U.require(len(coins) == 1, "merged profile requires one protected input")
            coin = coins[0]
            U.require(coin.role == "merged", "merged input role")
            m = coin.manifest
            U.require(m is not None, "manifest")
            m.check_admission()
            U.require(coin.output.script == merged_script(m), "merged script commitment")
            U.require(coin.output.value == m.principal_value + m.control_value, "denomination")
            U.require(not witness.keypath and witness.annex is None, "profile authority")
            U.require(U.template_hash(tx, 0) == merged_template(m, witness.branch), "template")
            U.require(height >= coin.height, "before assertion")
            if witness.branch == "payout":
                U.require(tx.version >= 2 and tx.inputs[0].sequence == m.delay, "CSV fields")
                U.require(height >= coin.height + m.delay, "CSV age")
                U.require(witness.signature, "operator authorization")
            else:
                U.require(witness.evidence is not None and witness.evidence.verifies(m), "fraud evidence")
            U.require(sum(x.value for x in tx.outputs) == coin.output.value, "protected value")
            return 0

        def apply(self, tx, witness, height):
            self.validate(tx, witness, height)
            txid = tx.txid()
            U.require(all(U.OutPoint(txid, i) not in self.coins for i in range(len(tx.outputs))), "duplicate outputs")
            del self.coins[tx.inputs[0].prevout]
            for i, output in enumerate(tx.outputs):
                self.coins[U.OutPoint(txid, i)] = U.Coin(output, height, "anchor" if i == 2 else "terminal")
            return txid

    @dataclass(frozen=True)
    class MergedInstance:
        manifest: object
        assertion: object
        merged: object
        sponsor: object

        def evidence(self):
            m = self.manifest
            return U.FraudEvidence(m.graph_id, m.statement_hash, m.setup_id)

        def spending(self, branch):
            m = self.manifest
            tx = U.Transaction((U.TxInput(self.merged, m.delay if branch == "payout" else 0),),
                               m.terminal_outputs(branch))
            return tx, MergedWitness(branch, self.evidence() if branch == "recovery" else None, branch == "payout")

    def merged_instance(number, m, height=100, ledger=None):
        ledger = MergedLedger({}) if ledger is None else ledger
        m.check_admission()
        assertion = U.Transaction((U.TxInput(U.OutPoint(U.h(f"assert-funding{number}".encode()), 0)),),
                                  (U.TxOutput(m.principal_value + m.control_value, merged_script(m)),
                                   U.TxOutput(0, b"\x51")))
        coin = U.OutPoint(assertion.txid(), 0)
        anchor = U.OutPoint(assertion.txid(), 1)
        sponsor = U.OutPoint(U.h(f"fee-funding{number}".encode()), 0)
        destinations = (coin, anchor, sponsor)
        U.require(len(set(destinations)) == len(destinations), "duplicate construction destinations")
        U.require(all(point not in ledger.coins for point in destinations), "instance destination already exists")
        working = ledger.copy()
        working.coins[coin] = U.Coin(assertion.outputs[0], height, "merged", m)
        working.coins[anchor] = U.Coin(assertion.outputs[1], height, "anchor")
        working.coins[sponsor] = U.Coin(U.TxOutput(3000, b"fee-sponsor"), height - 1, "sponsor")
        ledger.coins = working.coins
        return ledger, MergedInstance(m, assertion, coin, sponsor)

    def accepted(call):
        try:
            call()
            return True
        except U.Rejected:
            return False

    # Exhaustive bounded decision grid shares the economic claim and authorization.
    decision_pairs = accepted_pairs = 0
    for principal in (1000, 1_000_000, U.MAX_MONEY - 1_000_000):
        for bond in (1, 10_000):
            for delay in (1, 6, 20, 144, 65535):
                for false in (False, True):
                    m = make_manifest(0, principal, bond, delay, false)
                    pl, pi = paired_instance(0, m)
                    ml, mi = merged_instance(0, m)
                    for height in (99, 100, 100 + delay - 1, 100 + delay, 101 + delay):
                        for branch in ("payout", "recovery"):
                            for signature in (False, True):
                                for evidence_case in ("valid", "invalid", "other_statement", "missing"):
                                    evidence = pi.evidence()
                                    if evidence_case == "invalid":
                                        evidence = replace(evidence, valid_under_ideal_verifier=False)
                                    elif evidence_case == "other_statement":
                                        evidence = replace(evidence, statement_hash=bytes(32))
                                    elif evidence_case == "missing":
                                        evidence = None
                                    pt, pw = pi.spending(branch)
                                    mt, mw = mi.spending(branch)
                                    pw = (pw[0], replace(pw[1], operator_signature_valid=signature, evidence=evidence))
                                    mw = replace(mw, signature=signature, evidence=evidence)
                                    a = accepted(lambda: pl.validate_pair(pt, pw, height))
                                    b = accepted(lambda: ml.validate(mt, mw, height))
                                    # Independent abstract contract predicate.
                                    expected = height >= 100 and (
                                        (branch == "payout" and height >= 100 + delay and signature)
                                        or (branch == "recovery" and false and evidence_case == "valid"))
                                    assert a == b == expected
                                    assert pt.outputs == mt.outputs
                                    decision_pairs += 1
                                    accepted_pairs += a

    m = make_manifest()
    pl, pi = paired_instance(17, m)
    ml, mi = merged_instance(17, m)
    attacks = []
    for branch in ("payout", "recovery"):
        pt, pw = pi.spending(branch)
        mt, mw = mi.spending(branch)
        def mutate(tx, case, sponsor):
            if case == "redirect_principal":
                return replace(tx, outputs=(replace(tx.outputs[0], script=b"\x51\x20" + bytes(32)), *tx.outputs[1:]))
            if case == "principal_to_fee":
                return replace(tx, outputs=(replace(tx.outputs[0], value=tx.outputs[0].value - 1), *tx.outputs[1:]))
            if case == "inflate_payout":
                return replace(tx, outputs=(replace(tx.outputs[0], value=tx.outputs[0].value + 1), *tx.outputs[1:]))
            if case == "append_sponsor":
                return replace(tx, inputs=tx.inputs + (U.TxInput(sponsor),))
            if case == "change_sequence":
                return replace(tx, inputs=(replace(tx.inputs[0], sequence=tx.inputs[0].sequence + 1), *tx.inputs[1:]))
            if case == "change_version":
                return replace(tx, version=3)
            if case == "change_locktime":
                return replace(tx, locktime=1)
            if case == "burn_all":
                return replace(tx, outputs=(U.TxOutput(0, b"\x6a"),))
            raise AssertionError(case)
        for case in ("redirect_principal", "principal_to_fee", "inflate_payout", "append_sponsor",
                     "change_sequence", "change_version", "change_locktime", "burn_all"):
            pa, ma = mutate(pt, case, pi.sponsor), mutate(mt, case, mi.sponsor)
            assert not accepted(lambda: pl.validate_pair(pa, pw, 120))
            assert not accepted(lambda: ml.validate(ma, mw, 120))
            attacks.append({"branch": branch, "case": case, "paired_rejected": True, "merged_rejected": True})

    # Equivalent terminal consumption and fee-child independence.
    trace_results = []
    for first in ("payout", "recovery"):
        second = "recovery" if first == "payout" else "payout"
        pstate, mstate = pl.copy(), ml.copy()
        pt, pw = pi.spending(first)
        mt, mw = mi.spending(first)
        pid = pstate.apply_pair(pt, pw, 120)
        mid = mstate.apply(mt, mw, 120)
        assert [pstate.coins[U.OutPoint(pid, i)].output for i in range(3)] == [
            mstate.coins[U.OutPoint(mid, i)].output for i in range(3)]
        pt2, pw2 = pi.spending(second)
        mt2, mw2 = mi.spending(second)
        assert not accepted(lambda: pstate.apply_pair(pt2, pw2, 121))
        assert not accepted(lambda: mstate.apply(mt2, mw2, 121))
        trace_results.append({"first": first, "conflicting_second_rejected": True,
                              "same_terminal_output_vector": True})

    fee_cases = []
    for branch in ("payout", "recovery"):
        for fee in (1000, 3000, 9000):
            pstate, mstate = pl.copy(), ml.copy()
            pt, pw = pi.spending(branch)
            mt, mw = mi.spending(branch)
            pid = pstate.apply_pair(pt, pw, 120)
            mid = mstate.apply(mt, mw, 120)
            child_ids, child_sizes = [], []
            for state, parent in ((pstate, pid), (mstate, mid)):
                sponsor = U.OutPoint(U.h(f"independent-fee-{fee}".encode()), 0)
                state.coins[sponsor] = U.Coin(U.TxOutput(10_000, b"fee-sponsor"), 99, "sponsor")
                child = U.Transaction((U.TxInput(U.OutPoint(parent, 2)), U.TxInput(sponsor)),
                                      (U.TxOutput(10_000 - fee, b"fee-change"),))
                assert not accepted(lambda: state.apply_anchor_child(child, 120, sponsor_signature_valid=False))
                child_ids.append(state.apply_anchor_child(child, 120))
                child_sizes.append(len(child.serialize()))
                assert state.coins[U.OutPoint(parent, 0)].output.value == m.principal_value
                assert state.coins[U.OutPoint(parent, 1)].output.value == m.control_value
            assert child_sizes[0] == child_sizes[1]
            fee_cases.append({"branch": branch, "fee_sats": fee, "protected_outputs_unchanged": True,
                              "same_child_base_size": True})

    # Snapshot rollback and re-confirmation height reassignment, without a chain engine.
    age_cases = []
    for displacement in (1, 6, 20):
        pstate, mstate = pl.copy(), ml.copy()
        for point in (pi.principal, pi.control):
            pstate.coins[point] = replace(pstate.coins[point], height=100 + displacement)
        mstate.coins[mi.merged] = replace(mstate.coins[mi.merged], height=100 + displacement)
        for height in (119 + displacement, 120 + displacement):
            pt, pw = pi.spending("payout")
            mt, mw = mi.spending("payout")
            a = accepted(lambda: pstate.validate_pair(pt, pw, height))
            b = accepted(lambda: mstate.validate(mt, mw, height))
            assert a == b == (height == 120 + displacement)
            age_cases.append({"reconfirmation_displacement": displacement, "height": height, "both_accept": a})

    randomizer = random.Random(SEED)
    identifiers = randomizer.sample(range(1, 1_000_000_000), 64)
    substitutions = U.Ledger({})
    instances = [paired_instance(n, m, ledger=substitutions)[1] for n in identifiers]
    correct = rejected = 0
    for left, own in enumerate(instances):
        tx, witnesses = own.spending("payout")
        for right, other in enumerate(instances):
            attempt = U.replace_input(tx, 1, other.control)
            ok = accepted(lambda: substitutions.validate_pair(attempt, witnesses, 120))
            assert ok == (left == right)
            correct += ok
            rejected += not ok
    # Complete independent clones still carry separate claims to the same payout.
    duplicate_totals = {}
    for route in ("paired", "merged"):
        state = U.Ledger({}) if route == "paired" else MergedLedger({})
        total = 0
        for number in (51, 52):
            factory = paired_instance if route == "paired" else merged_instance
            state, inst = factory(number, m, ledger=state)
            tx, witness = inst.spending("payout")
            if route == "paired":
                state.apply_pair(tx, witness, 120)
            else:
                state.apply(tx, witness, 120)
            total += tx.outputs[0].value
        duplicate_totals[route] = total
    assert duplicate_totals == {"paired": 2_000_000, "merged": 2_000_000}

    # Fresh UTXO-root admission is atomic. Separate funded roots for the same
    # economic liability remain the distinct duplicate-admission control above.
    admission_cases = []
    for route, factory, ledger_class in (("paired", paired_instance, U.Ledger),
                                        ("merged", merged_instance, MergedLedger)):
        state, inst = factory(777, m)
        before = dict(state.coins)
        assert not accepted(lambda: factory(777, m, height=101, ledger=state))
        assert state.coins == before, "Failed repeated admission changed existing coins"
        protected = (inst.principal, inst.control) if route == "paired" else (inst.merged,)
        assert all(state.coins[point].height == 100 for point in protected)
        admission_cases.append({"route": route, "case": "readmit_same_unspent_root",
                                "rejected": True, "original_state_and_heights_preserved": True})
        anchor_index = 2 if route == "paired" else 1
        destinations = list(protected) + [U.OutPoint(inst.assertion.txid(), anchor_index), inst.sponsor]
        for destination_index, point in enumerate(destinations):
            occupied = U.Coin(U.TxOutput(42, b"existing-coin"), 3, "terminal")
            state = ledger_class({point: occupied})
            before = dict(state.coins)
            assert not accepted(lambda: factory(777, m, height=101, ledger=state))
            assert state.coins == before, "Failed destination check changed ledger"
            admission_cases.append({"route": route, "case": "occupied_construction_destination",
                                    "destination_index": destination_index, "rejected": True,
                                    "original_state_and_heights_preserved": True})

    graph_result = {
        "bounded_decision_pairs": decision_pairs, "accepted_pairs": accepted_pairs,
        "differential_mismatches": 0,
        "independent_contract_predicate_mismatches": 0,
        "input_parameters": {"principal_sats": [1000, 1_000_000, U.MAX_MONEY - 1_000_000],
                             "bond_sats": [1, 10_000], "delay_blocks": [1, 6, 20, 144, 65535],
                             "assertion_height": 100, "claim_false": [False, True]},
        "matched_mutation_cases": attacks, "terminal_traces": trace_results,
        "fee_child_cases": fee_cases,
        "synthetic_reconfirmation_age_cases": age_cases,
        "same_script_substitution": {"instances": 64, "combinations": 4096,
                                     "intended_pairs_accepted": correct, "cross_pairs_rejected": rejected},
        "duplicated_admission_principal_paid_sats": duplicate_totals,
        "atomic_admission_cases": admission_cases,
        "maturity_boundary": "Both routes admit valid recovery and signed settlement at maturity; confirmed consumption excludes the other branch.",
    }
    sizing = {"paired_assertion": pi.assertion, "merged_assertion": mi.assertion,
              "paired_payout": pi.spending("payout")[0], "merged_payout": mi.spending("payout")[0],
              "paired_recovery": pi.spending("recovery")[0], "merged_recovery": mi.spending("recovery")[0],
              "principal": m.principal_value, "bond": m.control_value, "delay": m.delay}
    return graph_result, sizing


def witness_wire(items: list[bytes]) -> bytes:
    return compact(len(items)) + b"".join(compact(len(item)) + item for item in items)


def size_run(U, sizing) -> dict:
    def sizes(tx, witnesses):
        base = tx.serialize()
        assert len(witnesses) == len(tx.inputs)
        raw = base[:4] + b"\x00\x01" + base[4:-4] + b"".join(witness_wire(w) for w in witnesses) + base[-4:]
        # A distinct decoder checks count framing and parsed output conservation.
        parsed = decode_wire(raw)
        assert len(parsed["inputs"]) == len(tx.inputs)
        assert sum(x["value"] for x in parsed["outputs"]) == sum(x.value for x in tx.outputs)
        weight = 3 * len(base) + len(raw)
        assert weight == 4 * len(base) + 2 + sum(len(witness_wire(w)) for w in witnesses)
        return {"base_bytes": len(base), "total_bytes": len(raw), "weight_WU": weight,
                "vbytes": (weight + 3) // 4, "witness_bytes_including_marker_flag": len(raw) - len(base)}

    def push(data):
        assert len(data) <= 75
        return bytes([len(data)]) + data

    # Byte templates only: the sibling opcode has no assigned byte, and control
    # blocks/output commitments here are opaque size fixtures.
    def th(tx, index):
        return b"\xce" + push(U.template_hash(tx, index)) + b"\x87"
    sibling_principal = push(struct.pack("<III", 0, 1, 1)) + b"\xbb"
    sibling_control = push(struct.pack("<III", 1, 0, 0)) + b"\xbb"
    principal_leaf = sibling_principal + th(sizing["paired_payout"], 0)
    assert len(sibling_principal) == 14 and len(principal_leaf) == 49
    control = b"\xc0" + bytes(64)  # two-leaf Taproot tree: 33+32 bytes
    csv_sig = b"\x01\x14\xb2\x75" + push(bytes(32)) + b"\xad"
    assert len(csv_sig) == 38  # delay=20, CSV/DROP, 32-byte key, CHECKSIGVERIFY
    payout_merged_script = csv_sig + th(sizing["merged_payout"], 0)
    payout_paired_control_script = sibling_control + csv_sig + th(sizing["paired_payout"], 1)
    signature = bytes(64)
    payout = {
        "paired": sizes(sizing["paired_payout"],
                        [[principal_leaf, control], [signature, payout_paired_control_script, control]]),
        "merged": sizes(sizing["merged_payout"], [[signature, payout_merged_script, control]]),
    }
    payout["paired_extra_WU"] = payout["paired"]["weight_WU"] - payout["merged"]["weight_WU"]
    payout["paired_extra_vbytes"] = payout["paired"]["vbytes"] - payout["merged"]["vbytes"]
    # Assertion proof/encoding and funding authorization must have the same size
    # in this structural comparison. The concrete shared fixture is 64+35+65 bytes.
    assertion = {
        route: sizes(sizing[f"{route}_assertion"],
                     [[bytes(64), th(sizing[f"{route}_assertion"], 0), control]])
        for route in ("paired", "merged")
    }
    assertion["paired_extra_WU"] = assertion["paired"]["weight_WU"] - assertion["merged"]["weight_WU"]
    recovery_rows = []
    for verifier_body in (0, 64, 203, 204, 217, 218, 1024, 4096):
        for proof_bytes in (0, 32, 520, 4096):
            proof_items = [bytes(min(520, proof_bytes - offset)) for offset in range(0, proof_bytes, 520)]
            # Opaque verifier bytes have the declared length. They are never executed.
            merged_script = bytes(verifier_body) + th(sizing["merged_recovery"], 0)
            paired_script = sibling_control + bytes(verifier_body) + th(sizing["paired_recovery"], 1)
            recovery_principal_leaf = sibling_principal + th(sizing["paired_recovery"], 0)
            p = sizes(sizing["paired_recovery"],
                      [[recovery_principal_leaf, control], proof_items + [paired_script, control]])
            m = sizes(sizing["merged_recovery"], [proof_items + [merged_script, control]])
            recovery_rows.append({"shared_verifier_body_bytes": verifier_body, "shared_proof_bytes": proof_bytes,
                                  "paired": p, "merged": m, "paired_extra_WU": p["weight_WU"] - m["weight_WU"]})
    delta_base_a = len(sizing["paired_assertion"].serialize()) - len(sizing["merged_assertion"].serialize())
    delta_base_t = len(sizing["paired_payout"].serialize()) - len(sizing["merged_payout"].serialize())
    assert delta_base_a == 43 and delta_base_t == 41
    assert assertion["paired_extra_WU"] == 172 and payout["paired_extra_WU"] == 295
    assert {x["paired_extra_WU"] for x in recovery_rows} == {295, 297}
    return {
        "scope": "Exact byte accounting of a specified symbolic envelope; full Taproot validity and proof execution remain unmeasured.",
        "layout": {"terminal_outputs": "two 34-byte commitment-shaped scripts plus a one-byte OP_TRUE anchor",
                   "assertion_outputs": "two protected commitments in paired route, one in merged route; same anchor",
                   "tree_leaves_per_protected_coin": 2, "control_block_bytes": 65,
                   "principal_leaf_bytes": 49, "template_leaf_bytes": 35, "sibling_chunk_bytes": 14,
                   "payout_operator_signature_bytes": 64, "delay_blocks": 20,
                   "shared_assertion_witness": "64-byte opaque data,35-byte template leaf,65-byte control envelope",
                   "sibling_opcode_size_fixture": "0xbb used only to occupy one byte; no allocation or executable policy asserted"},
        "assertion": assertion, "payout": payout, "recovery_parameter_sweep": recovery_rows,
        "exact_base_byte_delta": {"assertion": delta_base_a, "terminal": delta_base_t, "complete_path": 84},
        "two_stage_payout_path_extra_WU": 467,
        "two_stage_recovery_path_extra_WU_values": [467, 469],
        "marginal_fee_scenario_sats": {"1_sat_vB": 117, "5_sat_vB": 585, "10_sat_vB": 1170},
        "fee_scenario_note": "Ceiling-rounded sum of the two payout transactions' vbytes; fee-child layouts are identical. Market fees and relay acceptance are unmeasured.",
        "resource_work_counts": {"paired_terminal_template_checks": 2, "merged_terminal_template_checks": 1,
                                 "paired_sibling_checks": 2, "merged_sibling_checks": 0,
                                 "shared_crypto_or_authority_payload_executions_per_route": 1},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-model", type=Path)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    candidates = [args.upstream_model] if args.upstream_model else [
        HERE / "source_snapshot/upstream_sibling_model.py",
        HERE.parents[2] / "in-and-out-burger/research/checksiblingverify/sibling_model.py",
    ]
    model = next((x for x in candidates if x is not None and x.is_file()), None)
    if model is None:
        raise FileNotFoundError("Supply the pinned model with --upstream-model")
    U = load_upstream(model)
    vectors = check_official_vectors(U, HERE / "bip446_basics.json")
    graph, sizing = run_graphs(U)
    result = {
        "schema_version": "0.1", "experiment": "BIP-SIEVE-MATCH-01",
        "observation_date": "2026-11-13", "seed": SEED,
        "source_pins": {"spiral_commit": SPIRAL_COMMIT, "paired_model_git_blob": UPSTREAM_BLOB,
                        "bips_commit": BIPS_COMMIT, "bip446_basics_git_blob": VECTOR_BLOB},
        "match_contract": {
            "claim": "One admitted finite economic liability with predetermined settlement and liability-preserving recovery outputs.",
            "principal": "Same P", "bond": "Same B, combined with P in the merged coin",
            "authority": "Same ideal operator signature and graph/statement/setup-bound ideal fraud predicate.",
            "timing": "Same assertion confirmation height and block-based relative delay.",
            "fees": "Zero-fee protected parents; separately authorized child spends a zero-value anchor and confirmed fee coin.",
            "recovery": "Same full terminal output vector; consumes every protected claim output.",
            "admission": "Full policy and denomination assumed checked; fresh UTXO-root construction is atomic and rejects occupied destinations. Distinct roots can still duplicate an economic claim.",
        },
        "official_vectors": vectors, "graph_results": graph, "serialization": size_run(U, sizing),
        "unmeasured": [
            "Bitcoin Script execution, actual Taproot output/control-block commitments and native validation time.",
            "Real BitVM garbling, proof soundness, assertion publication and cryptographic witness size.",
            "Live node relay, fee replacement, adversarial inclusion, actual chain reorganizations and funded recovery.",
            "Global economic claim uniqueness, reusable vaults and liabilities outside the one-shot terminal policy.",
        ],
        "passed": True,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": True, "decision_pairs": graph["bounded_decision_pairs"],
                      "cross_pairs_rejected": graph["same_script_substitution"]["cross_pairs_rejected"],
                      "base_path_extra_bytes": 84, "payout_path_extra_WU": 467,
                      "results": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()

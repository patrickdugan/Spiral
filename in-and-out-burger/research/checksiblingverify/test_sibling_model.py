"""Adversarial model tests. Run with Python 3.11+ and no dependencies.

`python test_sibling_model.py` writes model_report.json after running tests.
Security conclusions are limited to this symbolic transaction/UTXO model.
"""

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import struct
import unittest

from sibling_model import (
    Coin, FraudEvidence, Ledger, Manifest, OutPoint, Rejected, Transaction,
    TxInput, TxOutput, Witness, check_sibling_verify, compact_size, descriptor,
    h, make_instance, replace_input, template_hash,
)


EXHAUSTIVE_GRAPHS = 24
EXHAUSTIVE_COUNTS: dict[str, int] = {}


class OpcodeTests(unittest.TestCase):
    def setUp(self):
        self.ledger, self.instance = make_instance()
        self.tx, self.witnesses = self.instance.spending("payout")

    def test_valid_descriptor_consumes_one_item_and_pushes_nothing(self):
        stack = [b"preserved", descriptor(0, 1, 1)]
        check_sibling_verify(stack, self.tx, 0)
        self.assertEqual(stack, [b"preserved"])
        stack = [descriptor(1, 0, 0)]
        check_sibling_verify(stack, self.tx, 1)
        self.assertEqual(stack, [])

    def test_empty_stack_rejected(self):
        with self.assertRaisesRegex(Rejected, "empty stack"):
            check_sibling_verify([], self.tx, 0)

    def test_descriptor_lengths_rejected(self):
        for length in (0, 1, 4, 8, 11, 13, 16, 520):
            with self.subTest(length=length), self.assertRaisesRegex(Rejected, "12 bytes"):
                check_sibling_verify([bytes(length)], self.tx, 0)

    def test_current_input_bounds_rejected(self):
        for index in (-1, 2, 2**32 - 1):
            with self.subTest(index=index), self.assertRaisesRegex(Rejected, "current input out"):
                check_sibling_verify([descriptor(0, 1, 1)], self.tx, index)

    def test_peer_input_bounds_rejected(self):
        for index in (2, 2**32 - 1):
            with self.subTest(index=index), self.assertRaisesRegex(Rejected, "peer input out"):
                check_sibling_verify([descriptor(0, index, 1)], self.tx, 0)

    def test_self_peer_rejected(self):
        with self.assertRaisesRegex(Rejected, "peer equals"):
            check_sibling_verify([descriptor(0, 0, 1)], self.tx, 0)

    def test_equal_output_roles_rejected(self):
        with self.assertRaisesRegex(Rejected, "equal output roles"):
            check_sibling_verify([descriptor(0, 1, 0)], self.tx, 0)

    def test_wrong_own_vout_rejected(self):
        with self.assertRaisesRegex(Rejected, "current output role"):
            check_sibling_verify([descriptor(2, 1, 1)], self.tx, 0)

    def test_wrong_peer_vout_rejected(self):
        with self.assertRaisesRegex(Rejected, "peer output role"):
            check_sibling_verify([descriptor(0, 1, 2)], self.tx, 0)

    def test_same_parent_opposite_roles_accept(self):
        reverse = replace(self.tx, inputs=(self.tx.inputs[1], self.tx.inputs[0]))
        stack = [descriptor(1, 1, 0)]
        check_sibling_verify(stack, reverse, 0)
        self.assertEqual(stack, [])
        # The opcode supports arbitrary indices; the application fixes its own layout.

    def test_cross_parent_same_script_rejected(self):
        # Both instances intentionally carry byte-identical symbolic scripts.
        _, other = make_instance(1, ledger=self.ledger, manifest=self.instance.manifest)
        self.assertEqual(self.instance.assertion.outputs, other.assertion.outputs)
        tx = replace_input(self.tx, 1, other.control)
        with self.assertRaisesRegex(Rejected, "different funding"):
            check_sibling_verify([descriptor(0, 1, 1)], tx, 0)

    def test_uint32_descriptor_wire_encoding(self):
        self.assertEqual(descriptor(0x01020304, 0x05060708, 0x090A0B0C).hex(),
                         "04030201080706050c0b0a09")
        for args in ((-1, 1, 2), (0, 2**32, 1), (0, 1, 2**32)):
            with self.subTest(args=args), self.assertRaises(Rejected):
                descriptor(*args)


class SerializationTests(unittest.TestCase):
    def test_compact_size_boundaries(self):
        vectors = ((0, "00"), (252, "fc"), (253, "fdfd00"), (65535, "fdffff"),
                   (65536, "fe00000100"), (2**32, "ff0000000001000000"))
        for number, expected in vectors:
            with self.subTest(number=number):
                self.assertEqual(compact_size(number).hex(), expected)

    def test_template_hash_matches_independent_wire_payload(self):
        tx = Transaction(
            (TxInput(OutPoint(bytes(32), 0), 1), TxInput(OutPoint(b"\x01" * 32, 9), 2)),
            (TxOutput(3, b"\x51"), TxOutput(5, b"\x6a")), locktime=17,
        )
        # Literal serialized sequences and CTxOut bytes from BIP 446's field rules.
        seq_hash = sha256(bytes.fromhex("0100000002000000")).digest()
        output_hash = sha256(bytes.fromhex("030000000000000001510500000000000000016a")).digest()
        payload = bytes.fromhex("0200000011000000") + seq_hash + output_hash + bytes.fromhex("0001000000")
        tag = sha256(b"TemplateHash").digest()
        expected = sha256(tag + tag + payload).digest()
        self.assertEqual(template_hash(tx, 1), expected)

    def test_template_hash_omits_outpoints_which_sibling_rule_checks(self):
        _, instance = make_instance()
        tx, _ = instance.spending("payout")
        changed = replace_input(tx, 1, OutPoint(h(b"counterfeit parent"), 1))
        self.assertEqual(template_hash(tx, 0), template_hash(changed, 0))
        self.assertNotEqual(tx.txid(), changed.txid())
        with self.assertRaisesRegex(Rejected, "different funding"):
            check_sibling_verify([descriptor(0, 1, 1)], changed, 0)

    def test_template_commits_sequences_outputs_version_locktime_and_index(self):
        _, instance = make_instance()
        tx, _ = instance.spending("payout")
        edits = (
            replace(tx, version=3),
            replace(tx, locktime=1),
            replace(tx, inputs=(replace(tx.inputs[0], sequence=0), tx.inputs[1])),
            replace(tx, outputs=(replace(tx.outputs[0], script=b"attacker"), *tx.outputs[1:])),
        )
        for edited in edits:
            with self.subTest(edited=edited):
                self.assertNotEqual(template_hash(tx, 0), template_hash(edited, 0))
        self.assertNotEqual(template_hash(tx, 0), template_hash(tx, 1))

    def test_annex_rejected_by_declared_profile(self):
        _, instance = make_instance()
        tx, _ = instance.spending("payout")
        with self.assertRaisesRegex(Rejected, "no annex"):
            template_hash(tx, 0, b"\x50anything")


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.ledger, self.instance = make_instance()

    def test_delayed_payout_preserves_principal_and_control(self):
        tx, witnesses = self.instance.spending("payout")
        self.assertEqual(self.ledger.validate_pair(tx, witnesses, 120), 0)
        txid = self.ledger.apply_pair(tx, witnesses, 120)
        self.assertNotIn(self.instance.principal, self.ledger.coins)
        self.assertNotIn(self.instance.control, self.ledger.coins)
        self.assertEqual(self.ledger.coins[OutPoint(txid, 0)].output.value, 1_000_000)
        self.assertEqual(sum(x.value for x in tx.outputs), 1_010_000)
        self.assertEqual(tx.outputs[2].value, 0)

    def test_valid_fraud_recovers_both_atomically(self):
        tx, witnesses = self.instance.spending("recovery")
        txid = self.ledger.apply_pair(tx, witnesses, 101)
        self.assertNotIn(self.instance.principal, self.ledger.coins)
        self.assertNotIn(self.instance.control, self.ledger.coins)
        self.assertEqual(self.ledger.coins[OutPoint(txid, 0)].output.script,
                         self.instance.manifest.recovery_script)
        self.assertTrue(all(self.ledger.coins[OutPoint(txid, i)].manifest is None for i in range(3)))

    def test_recovery_can_follow_assertion_within_same_block(self):
        tx, witnesses = self.instance.spending("recovery")
        # Consensus order may place Assert before its disproof in one block.
        # Relay acceptance and package limits are deliberately outside this model.
        self.ledger.apply_pair(tx, witnesses, 100)

    def test_omitted_connector_rejected(self):
        tx, witnesses = self.instance.spending("payout")
        tx = replace(tx, inputs=(tx.inputs[0],))
        with self.assertRaises(Rejected):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_connector_only_burn_rejected(self):
        tx, witnesses = self.instance.spending("recovery")
        tx = replace(tx, inputs=(tx.inputs[1],), outputs=(TxOutput(0, b"\x6a"),))
        with self.assertRaisesRegex(Rejected, "exactly two protected"):
            self.ledger.validate_pair(tx, witnesses, 101)
        self.assertIn(self.instance.principal, self.ledger.coins)
        self.assertIn(self.instance.control, self.ledger.coins)

    def test_wrong_input_order_rejected(self):
        tx, witnesses = self.instance.spending("payout")
        tx = replace(tx, inputs=tuple(reversed(tx.inputs)))
        with self.assertRaisesRegex(Rejected, "role layout"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_wrong_connector_output_index_rejected(self):
        tx, witnesses = self.instance.spending("payout")
        fake = OutPoint(self.instance.control.txid, 2)
        self.ledger.coins[fake] = self.ledger.coins[self.instance.control]
        tx = replace_input(tx, 1, fake)
        with self.assertRaisesRegex(Rejected, "peer output role"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_duplicate_inputs_rejected(self):
        tx, witnesses = self.instance.spending("payout")
        tx = replace_input(tx, 1, self.instance.principal)
        with self.assertRaisesRegex(Rejected, "duplicate transaction input"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_branch_splice_rejected_in_both_directions(self):
        payout, pw = self.instance.spending("payout")
        recovery, rw = self.instance.spending("recovery")
        for tx, witnesses in ((payout, (pw[0], rw[1])), (recovery, (rw[0], pw[1]))):
            with self.subTest(branch=witnesses[0].branch), self.assertRaisesRegex(Rejected, "template"):
                self.ledger.validate_pair(tx, witnesses, 120)

    def test_output_redirection_and_principal_to_fees_rejected(self):
        tx, witnesses = self.instance.spending("payout")
        changed = (
            replace(tx.outputs[0], script=b"attacker"),
            replace(tx.outputs[0], value=tx.outputs[0].value - 1),
        )
        for first in changed:
            edited = replace(tx, outputs=(first, *tx.outputs[1:]))
            with self.subTest(first=first), self.assertRaisesRegex(Rejected, "template"):
                self.ledger.validate_pair(edited, witnesses, 120)

    def test_extra_input_cannot_join_fixed_parent(self):
        tx, witnesses = self.instance.spending("payout")
        tx = replace(tx, inputs=tx.inputs + (TxInput(self.instance.sponsor),))
        with self.assertRaisesRegex(Rejected, "exactly two protected"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_premature_payout_rejected_at_boundary(self):
        tx, witnesses = self.instance.spending("payout")
        with self.assertRaisesRegex(Rejected, "timelock"):
            self.ledger.validate_pair(tx, witnesses, 119)
        self.assertEqual(self.ledger.validate_pair(tx, witnesses, 120), 0)

    def test_missing_operator_signature_rejected(self):
        tx, witnesses = self.instance.spending("payout")
        witnesses = (witnesses[0], replace(witnesses[1], operator_signature_valid=False))
        with self.assertRaisesRegex(Rejected, "operator signature"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_invalid_and_missing_fraud_evidence_rejected(self):
        tx, witnesses = self.instance.spending("recovery")
        for evidence in (None, replace(self.instance.evidence(), valid_under_ideal_verifier=False)):
            edited = (witnesses[0], replace(witnesses[1], evidence=evidence))
            with self.subTest(evidence=evidence), self.assertRaisesRegex(Rejected, "fraud evidence"):
                self.ledger.validate_pair(tx, edited, 101)

    def test_ideal_fraud_proof_cannot_refute_valid_claim(self):
        ledger, instance = make_instance(99, claim_is_false=False)
        tx, witnesses = instance.spending("recovery")
        with self.assertRaisesRegex(Rejected, "fraud evidence"):
            ledger.validate_pair(tx, witnesses, 101)

    def test_copied_public_evidence_fails_for_other_graph_or_statement(self):
        for field in ("graph_id", "statement_hash", "setup_id"):
            altered = replace(self.instance.manifest, **{field: h(field.encode())})
            ledger, other = make_instance(7, manifest=altered)
            tx, witnesses = other.spending("recovery", evidence=self.instance.evidence())
            with self.subTest(field=field), self.assertRaisesRegex(Rejected, "fraud evidence"):
                ledger.validate_pair(tx, witnesses, 101)

    def test_confirmed_disproof_makes_later_payout_a_double_spend(self):
        recovery, rw = self.instance.spending("recovery")
        payout, pw = self.instance.spending("payout")
        self.ledger.apply_pair(recovery, rw, 101)
        with self.assertRaisesRegex(Rejected, "missing or spent"):
            self.ledger.apply_pair(payout, pw, 120)

    def test_confirmed_payout_makes_later_disproof_a_double_spend(self):
        payout, pw = self.instance.spending("payout")
        recovery, rw = self.instance.spending("recovery")
        self.ledger.apply_pair(payout, pw, 120)
        with self.assertRaisesRegex(Rejected, "missing or spent"):
            self.ledger.apply_pair(recovery, rw, 121)

    def test_maturity_block_allows_either_valid_conflicting_spend(self):
        # Boundary counterexample: consensus grants no fraud transaction priority.
        payout, pw = self.instance.spending("payout")
        recovery, rw = self.instance.spending("recovery")
        self.ledger.validate_pair(payout, pw, 120)
        self.ledger.validate_pair(recovery, rw, 120)
        for first, fw, second, sw in ((payout, pw, recovery, rw), (recovery, rw, payout, pw)):
            branch = self.ledger.copy()
            branch.apply_pair(first, fw, 120)
            with self.assertRaisesRegex(Rejected, "missing or spent"):
                branch.apply_pair(second, sw, 120)

    def test_keypath_and_unchecked_setup_rejected_at_admission(self):
        for field in ("keypath_disabled", "complete_tree_checked", "setup_verified",
                      "assert_encoding_valid", "one_shot"):
            with self.subTest(field=field), self.assertRaises(Rejected):
                make_instance(8, manifest=replace(self.instance.manifest, **{field: False}))

    def test_admitted_profile_excludes_keypath_spend(self):
        tx, witnesses = self.instance.spending("payout")
        witnesses = (replace(witnesses[0], keypath=True), witnesses[1])
        with self.assertRaisesRegex(Rejected, "key path disabled"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_literal_descriptor_cannot_be_replaced_by_spender(self):
        tx, witnesses = self.instance.spending("payout")
        witnesses = (replace(witnesses[0], operand=descriptor(0, 0, 1)), witnesses[1])
        with self.assertRaisesRegex(Rejected, "script literal"):
            self.ledger.validate_pair(tx, witnesses, 120)

    def test_fee_children_leave_protected_parent_and_payout_fixed(self):
        parent, witnesses = self.instance.spending("payout")
        parent_id = parent.txid()
        left, right = self.ledger.copy(), self.ledger.copy()
        for ledger, fee in ((left, 3_000), (right, 9_000)):
            ledger.apply_pair(parent, witnesses, 120)
            sponsor = OutPoint(h(f"sponsor-{fee}".encode()), 0)
            ledger.coins[sponsor] = Coin(TxOutput(fee, b"fee-sponsor"), 99, "sponsor")
            child = Transaction(
                (TxInput(OutPoint(parent_id, 2)), TxInput(sponsor)),
                (TxOutput(0, b"\x6a"),),
            )
            self.assertEqual(sum(ledger.coins[i.prevout].output.value for i in child.inputs), fee)
            ledger.apply_anchor_child(child, 120)
            self.assertEqual(ledger.coins[OutPoint(parent_id, 0)].output, parent.outputs[0])
            self.assertEqual(ledger.coins[OutPoint(parent_id, 1)].output, parent.outputs[1])
        self.assertEqual(parent.txid(), parent_id)

    def test_fee_sponsor_authorization_remains_required(self):
        parent, witnesses = self.instance.spending("payout")
        parent_id = self.ledger.apply_pair(parent, witnesses, 120)
        child = Transaction((TxInput(OutPoint(parent_id, 2)), TxInput(self.instance.sponsor)),
                            (TxOutput(0, b"\x6a"),))
        with self.assertRaisesRegex(Rejected, "sponsor signature"):
            self.ledger.apply_anchor_child(child, 120, sponsor_signature_valid=False)

    def test_same_script_cross_graph_substitution_exhaustive(self):
        ledger = Ledger({})
        instances = []
        # Identical scripts remove script differences as an accidental defense.
        for index in range(EXHAUSTIVE_GRAPHS):
            _, instance = make_instance(index, ledger=ledger, manifest=self.instance.manifest)
            instances.append(instance)
        accepted, rejected = 0, 0
        for left, own in enumerate(instances):
            tx, witnesses = own.spending("payout")
            for right, peer in enumerate(instances):
                changed = replace_input(tx, 1, peer.control)
                with self.subTest(principal_graph=left, connector_graph=right):
                    if left == right:
                        ledger.validate_pair(changed, witnesses, 120)
                        accepted += 1
                    else:
                        with self.assertRaisesRegex(Rejected, "different funding"):
                            ledger.validate_pair(changed, witnesses, 120)
                        rejected += 1
        EXHAUSTIVE_COUNTS.update(graphs=EXHAUSTIVE_GRAPHS, combinations=accepted + rejected,
                                 valid_same_graph=accepted, rejected_cross_graph=rejected)
        self.assertEqual(accepted, 24)
        self.assertEqual(rejected, 552)

    def test_two_valid_roots_can_reimburse_one_economic_payment_if_admission_duplicates_it(self):
        # Boundary counterexample: new graph IDs do not constitute a global nullifier.
        same_payment = h(b"one external payment")
        ledger = Ledger({})
        paid = []
        for number in (51, 52):
            manifest = replace(self.instance.manifest,
                               graph_id=h(f"graph-{number}".encode()),
                               setup_id=h(f"setup-{number}".encode()),
                               statement_hash=same_payment, claim_is_false=False)
            _, instance = make_instance(number, ledger=ledger, manifest=manifest)
            tx, witnesses = instance.spending("payout")
            txid = ledger.apply_pair(tx, witnesses, 120)
            paid.append(ledger.coins[OutPoint(txid, 0)].output.value)
        self.assertEqual(sum(paid), 2_000_000)


def run_and_report() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "scope": "Symbolic UTXO and transaction model of a proposed sibling-check opcode and one-shot profile",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "passed": result.wasSuccessful(),
        "exhaustive_substitution": EXHAUSTIVE_COUNTS,
        "implemented": [
            "Exactly 12-byte uint32 little-endian descriptor semantics",
            "Bitcoin non-witness transaction serialization and txids",
            "BIP 446 annex-absent tagged TemplateHash",
            "Fixed two-input terminal payout and atomic recovery transactions",
            "UTXO existence, amounts, duplicate-input rejection and consumption",
            "Block-height relative-lock boundary for the declared profile",
            "Zero-valued fixed parent anchor with external fee child",
        ],
        "observed_boundaries": [
            "At payout maturity, a valid fraud spend and delayed payout may both be valid; first confirmed wins",
            "Distinct admitted graph roots can reimburse the same economic payment if admission permits duplicated claims",
        ],
        "ideal_predicates": [
            "Correct and publicly evaluable setup with correct claim encoding before admission",
            "Graph/statement/setup-bound fraud verification",
            "Operator and fee-sponsor signature validity",
            "NUMS/key-path exclusion and complete-tree audit recorded in manifest",
        ],
        "limitations": [
            "No Bitcoin Core patch, Bitcoin Script execution, Taproot arithmetic or real proof verification",
            "Symbolic script identifiers are not valid instantiated Taproot programs",
            "Synthetic Assert admission; a real Reserve-to-Assert path must enforce the complete claim witness",
            "No garbling soundness, proof-system soundness, data-availability or secret-erasure implementation",
            "No relay, RBF, package acceptance, fee estimation, miner-inclusion or censorship analysis",
            "No chain reorganizations, mempool model, global payment-nullifier set or complete bridge accounting",
            "One-shot terminal recovery only; recurrent or reusable garbling remains outside scope",
            "Only annex-absent, fixed two-input templates are modeled",
            "Terminal recovery destination must preserve application liabilities; this model assumes its correctness",
        ],
    }
    Path(__file__).with_name("model_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_and_report())

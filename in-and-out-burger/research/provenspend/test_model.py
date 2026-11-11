"""Adversarial semantic tests. IdealReceipts is a test oracle, never a ZK prover."""
import json
import unittest
from dataclasses import replace
from hashlib import sha256, new as new_hash
from pathlib import Path

from model import *

CHAIN = h("fixture", b"regtest")
PROGRAM = h("fixture", b"reviewed-iob-program")
ANCHOR = h("fixture", b"canonical-ancestor")
OTHER_ANCHOR = h("fixture", b"older-canonical-ancestor")
ANCESTORS = {100: ANCHOR, 99: OTHER_ANCHOR}


class IdealReceipts:
    def __init__(self):
        self.accepted = set()
        self.calls = 0

    def issue(self, tx, env, menu, claims=frozenset(), payment=None, chain=CHAIN):
        env = replace(env, proof=b"shape-check")
        digest = precheck(chain, tx, env, ANCESTORS)
        d = env.old if env.old else env.new
        need(d.program == PROGRAM, "unknown_program_in_test_oracle")
        iob_relation(tx, env, menu, claims, payment)
        token = b"IDEAL-ORACLE-ONLY:" + len(self.accepted).to_bytes(8, "little")
        self.accepted.add((d.program, env.phase, digest, token))
        return replace(env, proof=token)

    def verify(self, program, phase, digest, token):
        self.calls += 1
        return (program, phase, digest, token) in self.accepted


class TestProvenSpend(unittest.TestCase):
    def setUp(self):
        self.menu = Menu()
        self.oracle = IdealReceipts()
        self.seed = Outpoint(h("fixture", b"funding"), 0)
        self.nonce = h("fixture", b"fresh-nonce")
        ident = origin_id(CHAIN, self.seed, 0, PROGRAM, self.menu.digest(), self.nonce)
        self.d = Descriptor(PROGRAM, self.menu.digest(), ident, state_root(frozenset()))
        self.init_tx = Tx((Input(self.seed, 2_001_000, b"\x51\x20" + compressed(G)[1:]),),
                          (Output(2_000_000, self.d.script()),))
        self.init_env = Envelope("INIT", None, self.d, 0, 100, ANCHOR, nonce=self.nonce)
        self.init_env = self.oracle.issue(self.init_tx, self.init_env, self.menu)
        self.payment = AuthenticatedPayment(Outpoint(h("fixture", b"payment"), 2),
                                            940_000, compressed(mul(7)), ident, ANCHOR)
        n = self.payment.nullifier()
        self.next_d = replace(self.d, state=state_root(frozenset({n})))
        self.tx = Tx((Input(Outpoint(h("fixture", b"origin-tx"), 0), 2_000_000, self.d.script()),),
                     (Output(948_400, dynamic_target(self.payment.pubkey, self.payment.prevout)),
                      Output(1_050_600, self.next_d.script())))
        self.env = Envelope("STEP", self.d, self.next_d, 1, 100, ANCHOR, journal=n)
        self.env = self.oracle.issue(self.tx, self.env, self.menu, payment=self.payment)

    def valid(self, tx=None, env=None, chain=CHAIN, ancestors=ANCESTORS):
        return validate(chain, tx or self.tx, env or self.env, ancestors, self.oracle.verify)

    def test_init_receipt_is_required_and_accepted(self):
        self.valid(self.init_tx, self.init_env)
        with self.assertRaises(Reject):
            self.valid(self.init_tx, replace(self.init_env, proof=b""))

    def test_step_pays_derived_destination(self):
        self.valid()
        self.assertEqual(self.tx.outputs[0].amount, 948_400)
        self.assertEqual(self.tx.outputs[0].script, dynamic_target(self.payment.pubkey, self.payment.prevout))

    def test_default_backend_rejects(self):
        with self.assertRaisesRegex(Reject, "no_cryptographic_backend"):
            validate(CHAIN, self.tx, self.env, ANCESTORS)

    def test_false_backend_rejects(self):
        with self.assertRaises(Reject):
            validate(CHAIN, self.tx, self.env, ANCESTORS, lambda *args: False)

    def test_proof_copy_preserves_payout(self):
        self.assertEqual(self.valid(), self.valid(replace(self.tx), replace(self.env)))

    def test_unknown_profile_rejected_before_backend(self):
        before = self.oracle.calls
        with self.assertRaises(Reject):
            self.valid(env=replace(self.env, old=replace(self.d, profile=1)))
        self.assertEqual(before, self.oracle.calls)

    def test_noncanonical_anchor_rejected_before_backend(self):
        before = self.oracle.calls
        with self.assertRaises(Reject):
            self.valid(env=replace(self.env, anchor_hash=ZERO))
        self.assertEqual(before, self.oracle.calls)

    def test_reorg_removes_anchor(self):
        with self.assertRaisesRegex(Reject, "noncanonical_anchor"):
            self.valid(ancestors={99: OTHER_ANCHOR})

    def test_anchor_receipt_cannot_move_to_another_ancestor(self):
        with self.assertRaises(Reject):
            self.valid(env=replace(self.env, anchor_height=99, anchor_hash=OTHER_ANCHOR))

    def test_duplicate_inputs(self):
        with self.assertRaisesRegex(Reject, "duplicate_input"):
            self.valid(tx=replace(self.tx, inputs=self.tx.inputs * 2))

    def test_two_proof_inputs(self):
        second = replace(self.tx.inputs[0], prevout=Outpoint(h("fixture", b"other"), 0))
        with self.assertRaisesRegex(Reject, "step_shape"):
            self.valid(tx=replace(self.tx, inputs=self.tx.inputs + (second,)))

    def test_missing_successor_commitment(self):
        with self.assertRaises(Reject):
            self.valid(tx=replace(self.tx, outputs=(self.tx.outputs[0],)))

    def test_forked_successor(self):
        outs = (self.tx.outputs[0], replace(self.tx.outputs[1], amount=500_000),
                replace(self.tx.outputs[1], amount=500_000))
        with self.assertRaisesRegex(Reject, "successor_count"):
            self.valid(tx=replace(self.tx, outputs=outs))

    def test_descriptor_swap(self):
        forged = replace(self.d, policy=h("fixture", b"evil"))
        with self.assertRaises(Reject):
            self.valid(env=replace(self.env, old=forged))

    def test_program_rotation_is_disallowed_even_with_matching_script(self):
        d = replace(self.next_d, program=h("fixture", b"evil"))
        tx = replace(self.tx, outputs=(self.tx.outputs[0], replace(self.tx.outputs[1], script=d.script())))
        with self.assertRaisesRegex(Reject, "program_or_origin_changed"):
            self.valid(tx, replace(self.env, new=d))

    def test_origin_reinitialization_changes_id(self):
        seed = Outpoint(h("fixture", b"another-funding"), 0)
        tx = replace(self.init_tx, inputs=(replace(self.init_tx.inputs[0], prevout=seed),))
        with self.assertRaisesRegex(Reject, "origin_binding"):
            self.valid(tx, self.init_env)

    def test_origin_nonce_change_rejected(self):
        with self.assertRaisesRegex(Reject, "origin_binding"):
            self.valid(self.init_tx, replace(self.init_env, nonce=ZERO))

    def test_init_must_have_taproot_carrier(self):
        tx = replace(self.init_tx, inputs=(replace(self.init_tx.inputs[0], script=b"\x00\x14" + bytes(20)),))
        with self.assertRaisesRegex(Reject, "init_carrier"):
            self.valid(tx, self.init_env)

    def test_init_nonempty_history_cannot_be_proven_by_example_program(self):
        d = replace(self.d, state=state_root(frozenset({h("fixture", b"used")})))
        tx = replace(self.init_tx, outputs=(Output(2_000_000, d.script()),))
        with self.assertRaisesRegex(Reject, "initial_state"):
            self.oracle.issue(tx, replace(self.init_env, new=d), self.menu)

    def test_dynamic_second_payment_has_different_target(self):
        p = replace(self.payment, prevout=Outpoint(h("fixture", b"second-payment"), 3),
                    pubkey=compressed(mul(11)), amount=500_000)
        n = p.nullifier()
        d = replace(self.d, state=state_root(frozenset({n})))
        tx = replace(self.tx, outputs=(Output(504_000, dynamic_target(p.pubkey, p.prevout)),
                                      Output(1_495_000, d.script())))
        env = self.oracle.issue(tx, replace(self.env, new=d, journal=n), self.menu, payment=p)
        self.valid(tx, env)
        self.assertNotEqual(tx.outputs[0].script, self.tx.outputs[0].script)

    def test_private_tweak_matches_public_target(self):
        p = 7
        pub = compressed(mul(p))
        t = int.from_bytes(h("IOB/payout-key", self.payment.prevout.encode() + pub), "big")
        q = compressed(mul((p + t) % ORDER))
        expected = b"\x00\x14" + new_hash("ripemd160", sha256(q).digest()).digest()
        self.assertEqual(expected, dynamic_target(pub, self.payment.prevout))

    def test_invalid_public_key_rejected(self):
        with self.assertRaises(Reject):
            dynamic_target(b"\x02" + bytes.fromhex("ff" * 32), self.payment.prevout)

    def test_fee_theft_cannot_receive_fresh_receipt(self):
        tx = replace(self.tx, outputs=(self.tx.outputs[0], replace(self.tx.outputs[1], amount=1)))
        with self.assertRaisesRegex(Reject, "fee_cap"):
            self.oracle.issue(tx, self.env, self.menu, payment=self.payment)

    def test_wrong_target_cannot_receive_fresh_receipt(self):
        tx = replace(self.tx, outputs=(replace(self.tx.outputs[0], script=b"\x00\x14" + bytes(20)), self.tx.outputs[1]))
        with self.assertRaisesRegex(Reject, "dynamic_payout"):
            self.oracle.issue(tx, self.env, self.menu, payment=self.payment)

    def test_same_payment_new_proof_rejected_by_state(self):
        used = frozenset({self.payment.nullifier()})
        tx = replace(self.tx, inputs=(replace(self.tx.inputs[0], script=self.next_d.script(), amount=1_050_600),),
                     outputs=(self.tx.outputs[0], replace(self.tx.outputs[1], amount=101_200)))
        env = replace(self.env, old=self.next_d)
        with self.assertRaisesRegex(Reject, "already_paid"):
            self.oracle.issue(tx, env, self.menu, used, self.payment)

    def test_second_leg_receipt_rejected_in_another_vault(self):
        d = replace(self.d, origin=h("fixture", b"other-origin"))
        nd = replace(self.next_d, origin=d.origin)
        tx = replace(self.tx, inputs=(replace(self.tx.inputs[0], script=d.script()),),
                     outputs=(self.tx.outputs[0], replace(self.tx.outputs[1], script=nd.script())))
        with self.assertRaisesRegex(Reject, "payment_domain"):
            self.oracle.issue(tx, replace(self.env, old=d, new=nd), self.menu, payment=self.payment)

    def test_authenticated_payment_must_use_selected_anchor(self):
        with self.assertRaisesRegex(Reject, "payment_anchor"):
            self.oracle.issue(self.tx, self.env, self.menu, payment=replace(self.payment, anchor=OTHER_ANCHOR))

    def test_history_reset_cannot_receive_fresh_receipt(self):
        nd = replace(self.next_d, state=state_root(frozenset()))
        tx = replace(self.tx, outputs=(self.tx.outputs[0], replace(self.tx.outputs[1], script=nd.script())))
        with self.assertRaisesRegex(Reject, "history_update"):
            self.oracle.issue(tx, replace(self.env, new=nd), self.menu, payment=self.payment)

    def test_fake_history_cannot_receive_fresh_receipt(self):
        with self.assertRaisesRegex(Reject, "history_root"):
            self.oracle.issue(self.tx, self.env, self.menu, frozenset({h("fixture", b"fake")}), self.payment)

    def test_menu_swap_cannot_receive_fresh_receipt(self):
        with self.assertRaisesRegex(Reject, "menu_binding"):
            self.oracle.issue(self.tx, self.env, replace(self.menu, rate_ppm=2_000_000), payment=self.payment)

    def test_block_budget_charged_before_verification(self):
        before = self.oracle.calls
        with self.assertRaisesRegex(Reject, "block_proof_budget"):
            validate_block([(CHAIN, self.tx, self.env)] * 3, ANCESTORS, self.oracle.verify, 2)
        self.assertEqual(before, self.oracle.calls)

    def test_block_budget_includes_origination(self):
        with self.assertRaises(Reject):
            validate_block([(CHAIN, self.init_tx, self.init_env)], ANCESTORS, self.oracle.verify, 0)

    def test_block_budget_accepts_one(self):
        validate_block([(CHAIN, self.tx, self.env)], ANCESTORS, self.oracle.verify, 1)

    def test_deposit_origin_domains_have_distinct_nullifiers(self):
        p = replace(self.payment, origin=h("fixture", b"other-vault"))
        self.assertNotEqual(p.nullifier(), self.payment.nullifier())


# Each changed public field must invalidate the already issued receipt.
MUTATIONS = {
    "tx_version": lambda s: (replace(s.tx, version=3), s.env),
    "locktime": lambda s: (replace(s.tx, locktime=1), s.env),
    "input_txid": lambda s: (replace(s.tx, inputs=(replace(s.tx.inputs[0], prevout=Outpoint(ZERO, 0)),)), s.env),
    "input_index": lambda s: (replace(s.tx, inputs=(replace(s.tx.inputs[0], prevout=replace(s.tx.inputs[0].prevout, index=1)),)), s.env),
    "input_value": lambda s: (replace(s.tx, inputs=(replace(s.tx.inputs[0], amount=2_000_001),)), s.env),
    "sequence": lambda s: (replace(s.tx, inputs=(replace(s.tx.inputs[0], sequence=0),)), s.env),
    "recipient": lambda s: (replace(s.tx, outputs=(replace(s.tx.outputs[0], script=b"\x00\x14" + bytes(20)), s.tx.outputs[1])), s.env),
    "payout_value": lambda s: (replace(s.tx, outputs=(replace(s.tx.outputs[0], amount=948_401), s.tx.outputs[1])), s.env),
    "reserve_value": lambda s: (replace(s.tx, outputs=(s.tx.outputs[0], replace(s.tx.outputs[1], amount=1_050_599))), s.env),
    "output_order": lambda s: (replace(s.tx, outputs=tuple(reversed(s.tx.outputs))), s.env),
    "journal": lambda s: (s.tx, replace(s.env, journal=ZERO)),
    "proof": lambda s: (s.tx, replace(s.env, proof=b"forged")),
    "empty_proof": lambda s: (s.tx, replace(s.env, proof=b"")),
    "large_proof": lambda s: (s.tx, replace(s.env, proof=b"x" * (MAX_PROOF_BYTES + 1))),
    "large_journal": lambda s: (s.tx, replace(s.env, journal=b"x" * (MAX_JOURNAL_BYTES + 1))),
    "negative_amount": lambda s: (replace(s.tx, outputs=(replace(s.tx.outputs[0], amount=-1), s.tx.outputs[1])), s.env),
    "create_value": lambda s: (replace(s.tx, outputs=(replace(s.tx.outputs[0], amount=MAX_MONEY), s.tx.outputs[1])), s.env),
    "step_nonce": lambda s: (s.tx, replace(s.env, nonce=h("fixture", b"wrong"))),
    "phase": lambda s: (s.tx, replace(s.env, phase="INIT")),
    "output_index": lambda s: (s.tx, replace(s.env, output_index=0)),
}


def mutation_test(mutate):
    def run(self):
        tx, env = mutate(self)
        with self.assertRaises(Reject):
            self.valid(tx, env)
    return run


for name, mutate in MUTATIONS.items():
    setattr(TestProvenSpend, "test_binding_" + name, mutation_test(mutate))


def chain_domain_test(self):
    with self.assertRaises(Reject):
        self.valid(chain=h("fixture", b"other-chain"))


TestProvenSpend.test_chain_domain = chain_domain_test

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestProvenSpend)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "success": result.wasSuccessful(),
        "scope": "semantic binding, origin rules, dynamic P2WPKH payout, replay state, test cost caps",
        "proof_backend": "ideal receipt oracle; no cryptographic proofs",
        "core_integration": False,
        "wire_decoder_implemented": False,
        "model_profile_and_limits": "test-only, unallocated, unbenchmarked",
        "source_sha256": {p: sha256(Path(p).read_bytes()).hexdigest() for p in ("model.py", "test_model.py")},
    }
    Path("results.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)

"""Keyless CHECKSIG prototype tests: cryptographic transcript binding and Script.

The Merkle path is a transparent hash proof of membership in a 2-key allowlist.
No Bitcoin Core integration, no STARK, no ZK, and no activated consensus rules.
"""
import json
from pathlib import Path
from dataclasses import replace
from struct import unpack_from
import unittest

from reference import (
    Input, Output, Tx, Reject, H, PUBKEYS, DUMMY, TXCOMMIT_KEY,
    compiled_script, execute, fixture, sighash, sigmsg, tapleaf,
    p2mr, tapbranch, compact_size, ops, CAT, CHECKSIGVERIFY
)


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        self.tx, self.script, self.control, self.witness = fixture(0)

    def run_modified(self, *, tx=None, script=None, control=None,
                     witness=None, upgraded=True, cat_active=True):
        return execute(self.tx if tx is None else tx,
                       self.script if script is None else script,
                       self.control if control is None else control,
                       self.witness if witness is None else witness,
                       upgraded=upgraded, cat_active=cat_active)

    def assert_rejects(self, *args, **kw):
        with self.assertRaises(Reject):
            self.run_modified(*args, **kw)

    def test_accept_recipient_zero(self):
        self.assertTrue(self.run_modified())

    def test_accept_recipient_one_from_same_funding_outpoint(self):
        tx2, script2, control2, witness2 = fixture(1)
        self.assertEqual(tx2.inputs, self.tx.inputs)
        self.assertEqual(script2, self.script)
        self.assertEqual(control2, self.control)
        self.assertNotEqual(tx2.outputs, self.tx.outputs)
        self.assertTrue(execute(tx2, script2, control2, witness2))

    def test_pubkey_selector_is_unknown_by_current_bip342(self):
        self.assertEqual(len(TXCOMMIT_KEY), 33)
        self.assertEqual(TXCOMMIT_KEY[0], 2)
        self.assertIn(CHECKSIGVERIFY, list(code for code, _ in ops(self.script)))

    def test_carries_real_cat_ops(self):
        self.assertIn(CAT, list(code for code, _ in ops(self.script)))

    def test_a_different_origin_can_generate_a_new_digest_after_funding(self):
        new_outpoint = H(b"new funding outpoint")
        tx, script, control, witness = fixture(1, prevout=new_outpoint)
        self.assertTrue(execute(tx, script, control, witness))
        self.assertNotEqual(sighash(tx, 0, leaf=tapleaf(script)),
                            sighash(self.tx, 0, leaf=tapleaf(self.script)))

    def test_unauthorized_recipient_with_original_witness(self):
        tx = replace(self.tx, outputs=(Output(948400, b"\x51\x20" + bytes(32)),))
        self.assert_rejects(tx=tx)

    def test_wrong_value(self):
        tx = replace(self.tx, outputs=(replace(self.tx.outputs[0], value=948401),))
        self.assert_rejects(tx=tx)

    def test_change_output_injected(self):
        tx = replace(self.tx, outputs=self.tx.outputs + (Output(1, b"\x6a"),))
        self.assert_rejects(tx=tx)

    def test_fee_or_funding_value_changed(self):
        inp = replace(self.tx.inputs[0], value=self.tx.inputs[0].value + 1)
        self.assert_rejects(tx=replace(self.tx, inputs=(inp,)))

    def test_outpoint_changed_with_original_proof(self):
        inp = replace(self.tx.inputs[0], txid=H(b"alternate original coin"))
        self.assert_rejects(tx=replace(self.tx, inputs=(inp,)))

    def test_sequence_changed(self):
        inp = replace(self.tx.inputs[0], sequence=0xfffffffe)
        self.assert_rejects(tx=replace(self.tx, inputs=(inp,)))

    def test_version_changed(self):
        self.assert_rejects(tx=replace(self.tx, version=3))

    def test_locktime_changed(self):
        self.assert_rejects(tx=replace(self.tx, locktime=5))

    def test_wrong_witness_prefix(self):
        witness = self.witness.copy()
        witness[0] = b"\xff" + witness[0][1:]
        self.assert_rejects(witness=witness)

    def test_wrong_witness_suffix(self):
        witness = self.witness.copy()
        witness[1] = witness[1][:-1] + b"\x00"
        self.assert_rejects(witness=witness)

    def test_membership_wrong_sibling(self):
        witness = self.witness.copy()
        witness[3] = bytes(32)
        self.assert_rejects(witness=witness)

    def test_membership_wrong_direction(self):
        witness = self.witness.copy()
        witness[4] = b"\x01"
        self.assert_rejects(witness=witness)

    def test_membership_unknown_recipient(self):
        witness = self.witness.copy()
        witness[2] = bytes([7]) * 32
        self.assert_rejects(witness=witness)

    def test_minimalif_rejects_nonminimal_true(self):
        witness = self.witness.copy()
        witness[4] = b"\x02"
        self.assert_rejects(witness=witness)

    def test_oversized_item(self):
        witness = self.witness.copy()
        witness[0] = bytes(521)
        self.assert_rejects(witness=witness)

    def test_p2mr_tree_commitment(self):
        self.assertEqual(self.tx.inputs[0].spent_script,
                         p2mr(self.script, DUMMY))
        self.assertEqual(len(self.control), 33)

    def test_wrong_control_branch(self):
        self.assert_rejects(control=b"\xc0" + bytes(32))

    def test_wrong_control_leaf_version(self):
        self.assert_rejects(control=b"\xc2" + self.control[1:])

    def test_mutate_committed_script(self):
        script = self.script[:-1] + b"\x00"
        self.assert_rejects(script=script)

    def test_old_rules_accept_mutated_output_under_unknown_pubkey(self):
        # This illustrates precisely why activation must precede funding.
        tx = replace(self.tx, outputs=(Output(948400, b"\x51\x20" + bytes(32)),))
        self.assertTrue(self.run_modified(tx=tx, upgraded=False))
        self.assert_rejects(tx=tx, upgraded=True)

    def test_reference_requires_cat_activation(self):
        self.assert_rejects(cat_active=False)

    def test_candidate_bip342_sighash_has_expected_size(self):
        msg = sigmsg(self.tx, 0, leaf=tapleaf(self.script))
        self.assertEqual(len(msg), 212)
        self.assertEqual(msg[0:2], b"\x00\x00")
        self.assertEqual(msg[170], 2)  # spend_type
        self.assertEqual(msg[-5], 2)   # proposed key_version

    def test_extension_domain_separation(self):
        normal = sighash(self.tx, 0, leaf=tapleaf(self.script), key_version=0)
        new = sighash(self.tx, 0, leaf=tapleaf(self.script), key_version=2)
        self.assertNotEqual(normal, new)

    def test_code_separator_changes_commitment(self):
        normal = sighash(self.tx, 0, leaf=tapleaf(self.script), codesep=0xffffffff)
        changed = sighash(self.tx, 0, leaf=tapleaf(self.script), codesep=17)
        self.assertNotEqual(normal, changed)

    def test_annex_changes_commitment(self):
        normal = sighash(self.tx, 0, leaf=tapleaf(self.script))
        annexed = sighash(self.tx, 0, leaf=tapleaf(self.script), annex=b"\x50other")
        self.assertNotEqual(normal, annexed)

    def test_invalid_hash_type(self):
        with self.assertRaises(Reject):
            sighash(self.tx, 0, leaf=tapleaf(self.script), hash_type=0x40)

    def test_single_missing_output(self):
        tx = replace(self.tx, inputs=(self.tx.inputs[0], replace(
            self.tx.inputs[0], txid=H(b"extra input"))))
        with self.assertRaises(Reject):
            sighash(tx, 1, leaf=tapleaf(self.script), hash_type=3)


def read_varint(data, offset):
    prefix = data[offset]
    offset += 1
    if prefix < 253:
        return prefix, offset
    if prefix == 253:
        return unpack_from("<H", data, offset)[0], offset + 2
    if prefix == 254:
        return unpack_from("<I", data, offset)[0], offset + 4
    return unpack_from("<Q", data, offset)[0], offset + 8


def load_unsigned_bip341_tx(hex_tx, utxos):
    raw = bytes.fromhex(hex_tx)
    off = 0
    version = unpack_from("<i", raw, off)[0]
    off += 4
    num_in, off = read_varint(raw, off)
    inputs = []
    for index in range(num_in):
        txid = raw[off:off+32]; off += 32
        vout = unpack_from("<I", raw, off)[0]; off += 4
        length, off = read_varint(raw, off)
        off += length  # scriptSig
        sequence = unpack_from("<I", raw, off)[0]; off += 4
        utxo = utxos[index]
        inputs.append(Input(txid, vout, utxo["amountSats"],
                            bytes.fromhex(utxo["scriptPubKey"]), sequence))
    num_out, off = read_varint(raw, off)
    outputs = []
    for _ in range(num_out):
        amount = unpack_from("<Q", raw, off)[0]; off += 8
        size, off = read_varint(raw, off)
        outputs.append(Output(amount, raw[off:off+size]))
        off += size
    locktime = unpack_from("<I", raw, off)[0]; off += 4
    assert off == len(raw)
    return Tx(tuple(inputs), tuple(outputs), version, locktime)


class OfficialBIP341VectorTests(unittest.TestCase):
    def test_key_path_sighash_matches_canonical_vectors(self):
        doc = json.loads(Path(__file__).with_name("bip341-vectors.json").read_text())
        tx = load_unsigned_bip341_tx(doc["rawUnsignedTx"], doc["utxosSpent"])
        for vector in doc["cases"]:
            with self.subTest(index=vector["index"], hash_type=vector["hash_type"]):
                msg = sigmsg(tx, vector["index"],
                             hash_type=vector["hash_type"], ext_flag=0)
                self.assertEqual(msg.hex(), vector["sigmsg"])
                digest = sighash(tx, vector["index"],
                                 hash_type=vector["hash_type"], ext_flag=0)
                self.assertEqual(digest.hex(), vector["sighash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

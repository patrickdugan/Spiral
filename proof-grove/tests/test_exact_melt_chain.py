import hashlib
import json
from pathlib import Path
import shutil
import unittest

from proofdesk.domain import Refused
from proofdesk.exact_melt_chain import WITNESS_CONTEXT_SCHEMA, audit_holder_transaction, observe, verify_witness_context
from proofdesk.protected_payout_evidence import _transaction
from proofdesk.protected_reserve import GENESIS
from test_protected_payout_evidence import fixture, hash256, little


FIXTURE = Path(__file__).resolve().parents[2] / "codex-campaign-2026-11-23" / "outputs"
OPENSSL = shutil.which("openssl")
RESERVE = "002059e8332f9a24f42a628572cfdfe3fd4822ad1c3f708ec73648de8531d2b10c58"
DESTINATION = "0014f52d0a091f630149ef614456e5bf58d831ad6b67"
PAYOUT = (
    "0200000000010116bd7575e8cd0f51c7863385348db2a8e1aec25ac08ebd23d464a353de73bf5100000000000600000001"
    "c65c000000000000160014f52d0a091f630149ef614456e5bf58d831ad6b67030047304402200861b73e01d3b9b789384c365"
    "32e9a439f433d58f971f817a7be9cafe2a61b8202202f447b6bf82b12c3350daea8d6d48f2b699d2bfc7b86fe649e85deb565"
    "18a7ee014b2103b3a696dd4b5e941ca1819db8a0f5e392505b355cb4f648c3ce2b3c71e94d9682ad63210200ceca8f1812db"
    "d53ac9a49504972171778a25437fd8075a5594130a875e8569ac6756b26800000000"
)


def hash_words(txid):
    wire = int.from_bytes(bytes.fromhex(txid)[::-1], "big")
    return [wire % 2**128, wire >> 128]


def output(sats, script):
    return {"n": 0, "value": f"0.{sats:08}", "scriptPubKey": {"hex": script}}


class CoreObservation:
    """RPC responses with independently chosen header, proof and transaction fields."""

    def __init__(self, receipt):
        self.tip = {"chain": "regtest", "initialblockdownload": False,
                    "bestblockhash": "ff" * 32, "blocks": 111}
        self.proofs = {height: bytes([height]).hex() * 80 + "01" for height in (104, 110)}
        self.blocks = {0: GENESIS, 111: self.tip["bestblockhash"]}
        for height, proof in self.proofs.items():
            header = bytes.fromhex(proof[:160])
            self.blocks[height] = hashlib.sha256(hashlib.sha256(header).digest()).digest()[::-1].hex()
        funding_id = receipt["funding_outpoint"].split(":")[0]
        payout_id = receipt["confirmed_spend"]
        self.tx = {104: {"txid": funding_id, "vout": [output(24000, RESERVE)]},
                   110: {"txid": payout_id, "hash": receipt["confirmed_spend_wtxid"],
                         "version": 2, "locktime": 0,
                         "vin": [{"txid": funding_id, "vout": 0, "sequence": 6}],
                         "vout": [output(23750, DESTINATION)]}}
        for height, tx in self.tx.items():
            tx.update(hex=PAYOUT if height == 110 else "0102", blockhash=self.blocks[height], in_active_chain=True)
        self.verified = {proof: [self.tx[height]["txid"]] for height, proof in self.proofs.items()}
        self.reorg = False
        self.tip_reads = 0

    def rpc(self, method, params):
        if method == "getblockchaininfo":
            self.tip_reads += 1
            return self.tip | ({"bestblockhash": "ee" * 32} if self.reorg and self.tip_reads > 1 else {})
        if method == "getblockhash":
            return self.blocks[params[0]]
        if method in ("getrawtransaction", "gettxoutproof"):
            height = next(height for height, block in self.blocks.items() if block == params[-1])
            return self.tx[height] if method == "getrawtransaction" else self.proofs[height]
        if method == "verifytxoutproof":
            return self.verified[params[0]]
        raise AssertionError((method, params))


class ExactMeltChainTest(unittest.TestCase):
    def setUp(self):
        self.receipt = json.loads((FIXTURE / "Cashu-Melt-Redemption-Cairo-Execution.json").read_bytes())
        self.core = CoreObservation(self.receipt)
        funding_id = self.receipt["funding_outpoint"].split(":")[0]
        melt = int(self.receipt["wallet_melt_commitment"], 16)
        self.words = [
            1, 23, int(self.receipt["program"]["program_hash"], 16),
            int.from_bytes(b"PROOFDESK_CSV_REDEEM_V1", "big"), *hash_words(funding_id),
            0, 24000, 1, int(RESERVE[:62], 16), int(RESERVE[62:], 16), 3,
            104, 110, melt % 2**128, melt >> 128, 0, int(DESTINATION, 16), 22, 23750,
            *hash_words(self.receipt["confirmed_spend"]), *hash_words(self.receipt["confirmed_spend_wtxid"]),
        ]

    def observe(self):
        return observe(self.core, self.receipt, self.words, 111, "ff" * 32)

    @unittest.skipUnless(OPENSSL, "OpenSSL is required for the independent holder signature test")
    def test_opens_the_exact_stark_witness_and_rejects_signature_mutations(self):
        def arguments(raw):
            full, tail = divmod(len(raw), 31)
            words = [int.from_bytes(raw[offset:offset + 31], "big") for offset in range(0, 31 * full, 31)]
            return self.words[4:19] + [full, *words, int.from_bytes(raw[31 * full:], "big"), tail]

        raw = bytearray.fromhex(PAYOUT)
        observed = audit_holder_transaction(arguments(raw), self.receipt, self.words, OPENSSL)
        self.assertTrue(observed["holder_signature_verified"])
        self.assertEqual(observed["bip143_sighash_all"], "0010ae6e931db779179d4e5fce2ae560201dbb9d3f2e6f0b7dae40d7cb23590b")
        self.assertEqual(observed["signature_mutations_rejected"], ["funding_txid", "funding_vout", "sequence", "reserve_script",
                                                                "reserve_amount", "payout_amount_and_fee", "beneficiary", "signature"])
        txid = _transaction(raw.hex()).txid
        raw[-5] ^= 1
        self.assertEqual(_transaction(raw.hex()).txid, txid)
        with self.assertRaisesRegex(ValueError, "does not open the Cairo payout"):
            audit_holder_transaction(arguments(raw), self.receipt, self.words, OPENSSL)

    def test_records_both_inclusions_and_the_exact_witness_transaction(self):
        result = self.observe()
        self.assertEqual(result["funding"]["txoutproof"], self.core.proofs[104])
        self.assertEqual(result["payout"]["txoutproof"], self.core.proofs[110])
        self.assertEqual(result["payout"]["wtxid"], self.receipt["confirmed_spend_wtxid"])
        self.assertEqual(result["wallet_melt_commitment"], self.receipt["wallet_melt_commitment"])
        self.assertEqual((result["relative_delay_blocks"], result["change_sats"], result["fee_sats"]), (6, 0, 250))

    def test_refuses_a_changed_anchor_network_or_observed_tip(self):
        for mutate, reason in (
            (lambda: self.core.blocks.update({111: "dd" * 32}), "exact_melt_chain_anchor_mismatch"),
            (lambda: self.core.blocks.update({0: "dd" * 32}), "protected_wrong_genesis"),
            (lambda: setattr(self.core, "reorg", True), "chain_changed_retry"),
        ):
            with self.subTest(reason=reason):
                self.core = CoreObservation(self.receipt)
                mutate()
                with self.assertRaisesRegex(Refused, reason):
                    self.observe()

    def test_refuses_a_different_melt_commitment(self):
        self.words[14] ^= 1
        with self.assertRaisesRegex(Refused, "exact_melt_receipt_mismatch"):
            self.observe()

    def test_refuses_transaction_and_merkle_substitutions(self):
        for mutate, reason in (
            (lambda: self.core.tx[104]["vout"][0].update(value="0.00024001"), "exact_melt_output_mismatch"),
            (lambda: self.core.tx[110]["vin"][0].update(sequence=5), "exact_melt_payout_mismatch"),
            (lambda: self.core.tx[110].update(hash="dd" * 32), "exact_melt_payout_mismatch"),
            (lambda: self.core.tx[110].update(hex="00" + PAYOUT[2:]), "exact_melt_payout_mismatch"),
            (lambda: self.core.tx[110]["vout"][0]["scriptPubKey"].update(hex="51"), "exact_melt_output_mismatch"),
            (lambda: self.core.tx[104].update(in_active_chain=False), "exact_melt_transaction_not_active"),
            (lambda: self.core.proofs.update({104: self.core.proofs[110]}), "exact_melt_invalid_inclusion"),
            (lambda: self.core.verified.update({self.core.proofs[110]: []}), "exact_melt_invalid_inclusion"),
        ):
            with self.subTest(reason=reason):
                self.core = CoreObservation(self.receipt)
                mutate()
                with self.assertRaisesRegex(Refused, reason):
                    self.observe()


class ExactMeltWitnessContextTest(unittest.TestCase):
    def setUp(self):
        payout_fixture, _, _, _ = fixture()
        funding, payout = (payout_fixture["public_transactions"][key] for key in ("funding", "payout"))
        prevout, paid = payout_fixture["reserve"], payout_fixture["payout"]
        self.receipt = {"network": "regtest", "statement_sha256": "12" * 32,
                        "funding_outpoint": f"{prevout['txid']}:0", "confirmed_spend": paid["txid"],
                        "confirmed_spend_wtxid": paid["wtxid"], "wallet_melt_commitment": "31" * 32,
                        "reserve_sats": 25000, "payout_sats": 24750, "payout_fee_sats": 250,
                        "relative_delay_blocks": 6}
        melt = int(self.receipt["wallet_melt_commitment"], 16)
        self.words = [1, 23, 0, int.from_bytes(b"PROOFDESK_CSV_REDEEM_V1", "big"), *hash_words(prevout["txid"]),
                      0, 25000, 1, int(prevout["script"][:62], 16), int(prevout["script"][62:], 16), 3, 104, 110,
                      melt % 2**128, melt >> 128, 0, int(paid["script"], 16), 22, 24750,
                      *hash_words(paid["txid"]), *hash_words(paid["wtxid"])]
        witness = payout_fixture["bitcoin_chain_evidence"]
        payout_roots = {index: bytes.fromhex(header)[36:68] for index, header in enumerate(witness["headers"], 104)}
        genesis = bytes.fromhex("01000000" + "00" * 32 + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
                                + "dae5494dffff7f2002000000")
        self.assertEqual(hash256(genesis)[::-1].hex(), GENESIS)
        headers = [genesis]
        for height in range(1, 112):
            headers.append(little(4) + hash256(headers[-1]) + payout_roots.get(height, bytes(32)) + bytes(12))
        self.anchor = hash256(headers[-1])[::-1].hex()
        self.context = {"schema": WITNESS_CONTEXT_SCHEMA, "network": "regtest", "genesis": GENESIS,
                        "statement_sha256": self.receipt["statement_sha256"], "anchor_height": 111,
                        "anchor_hash": self.anchor, "wallet_melt_commitment": self.receipt["wallet_melt_commitment"],
                        "relative_delay_blocks": 6, "fee_sats": 250, "change_sats": 0,
                        "funding": {"txid": prevout["txid"], "height": 104, "outpoint_vout": 0, "amount_sats": 25000,
                                    "block": hash256(headers[104])[::-1].hex(), "script": prevout["script"],
                                    "raw_transaction": funding},
                        "payout": {"txid": paid["txid"], "wtxid": paid["wtxid"], "height": 110, "amount_sats": 24750,
                                   "block": hash256(headers[110])[::-1].hex(), "script": paid["script"],
                                   "raw_transaction": payout},
                        "bitcoin_chain_evidence": witness | {"headers": [header.hex() for header in headers]}}

    def verify(self, *, anchor=None):
        return verify_witness_context(self.context, self.receipt, self.words, 111,
                                      self.anchor if anchor is None else anchor)

    def test_checks_mined_witness_with_a_later_pinned_checkpoint(self):
        result = self.verify()
        self.assertTrue(result["witness_inclusion_verified"])
        self.assertEqual(result["payout_wtxid"], self.receipt["confirmed_spend_wtxid"])
        with self.assertRaisesRegex(ValueError, "independent pins"):
            self.verify(anchor="89" * 32)

    def test_refuses_changed_bridge_header(self):
        self.context["bitcoin_chain_evidence"]["headers"][105] = "00" * 80
        with self.assertRaisesRegex(ValueError, "do not connect regtest genesis"):
            self.verify()

    def test_refuses_changed_coinbase_witness_with_same_txid(self):
        chain = self.context["bitcoin_chain_evidence"]
        raw = bytearray.fromhex(chain["payout_coinbase"])
        raw[-5] ^= 1
        self.assertEqual(_transaction(raw.hex()).txid, _transaction(chain["payout_coinbase"]).txid)
        chain["payout_coinbase"] = raw.hex()
        with self.assertRaisesRegex(ValueError, "outside the pinned BIP141 commitment"):
            self.verify()

    def test_refuses_mutated_reserve_and_fee_metadata(self):
        self.context["funding"]["amount_sats"] += 1
        with self.assertRaisesRegex(ValueError, "funding metadata"):
            self.verify()
        self.context["funding"]["amount_sats"] -= 1
        self.context["fee_sats"] -= 1
        with self.assertRaisesRegex(ValueError, "fee_sats differs"):
            self.verify()

"""A verifier-approved payout reserve on isolated patched regtest.

The host verifies M16 before approving this reserve. Script binds its complete
output vector and approval annex; it does not execute the M16 or M14 verifier.
The NUMS P2TR reserve retains the BIP341 key-path discrete-log assumption.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
import json
from pathlib import Path
import struct
import tempfile

from . import btc, desk, ec
from .errors import Refusal
from .ledger import Ledger
from .menu import Menu
from .rpc import RPCError

TXCOMMIT_KEY = b"\x02" + btc.sha256(b"BIPSpace/Keyless-CHECKSIG/TXCOMMIT-draft")
NUMS_X = bytes.fromhex("50929b74c1a04954b78b4b6035e97a5e078a5a0f28ec96d547bfee9ace803ac0")
REGTEST_GENESIS = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206"
MAX_MONEY = 21_000_000 * 100_000_000


def _output(value: int, script: bytes) -> bytes:
    return struct.pack("<Q", value) + btc.ser_compact(len(script)) + script


@dataclass(frozen=True)
class Approval:
    context_record: bytes
    recipient_script: bytes
    payout_sats: int
    link: bytes
    mining_fee_sats: int

    @property
    def context(self) -> bytes:
        return ec.tagged_hash("IOB/Keyless-M16/v1", self.context_record)

    @property
    def annex(self) -> bytes:
        return b"\x50" + self.context

    @property
    def reserve_sats(self) -> int:
        return self.payout_sats + self.mining_fee_sats

    def outputs(self) -> list[btc.TxOut]:
        return [btc.TxOut(self.payout_sats, self.recipient_script),
                btc.TxOut(0, b"\x6a" + btc.push(self.link))]

    @property
    def outputs_hash(self) -> bytes:
        return btc.sha256(b"".join(_output(o.value, o.script_pubkey) for o in self.outputs()))

    @property
    def annex_hash(self) -> bytes:
        return btc.sha256(btc.ser_compact(len(self.annex)) + self.annex)

    @property
    def script(self) -> bytes:
        tag = btc.sha256(b"TapSighash")
        return b"".join((
            b"\x6b\x6b\x82", btc.push(b"\x20"), b"\x88",
            btc.push(b"\x00\x00" + struct.pack("<iI", 2, 0)), b"\x7c\x7e",
            btc.push(btc.sha256(struct.pack("<Q", self.reserve_sats))), b"\x7e\x6c\x82",
            btc.push(b"\x20"), b"\x88\x7e",
            btc.push(btc.sha256(struct.pack("<I", 0xfffffffd))), b"\x7e",
            btc.push(self.outputs_hash), b"\x7e",
            btc.push(b"\x03\x00\x00\x00\x00" + self.annex_hash), b"\x7e\x6c\x82",
            btc.push(b"\x25"), b"\x88\x7e", btc.push(tag + tag), b"\x7c\x7e\xa8",
            btc.push(TXCOMMIT_KEY), b"\xad\x51",
        ))

    @property
    def leaf_hash(self) -> bytes:
        script = self.script
        return ec.tagged_hash("TapLeaf", b"\xc0" + btc.ser_compact(len(script)) + script)

    def taproot(self) -> tuple[bytes, bytes]:
        tweak = int.from_bytes(ec.tagged_hash("TapTweak", NUMS_X + self.leaf_hash), "big")
        if tweak >= ec.N:
            raise Refusal("keyless_tweak_invalid", "TapTweak exceeds the group order")
        output = ec.add(ec.parse(b"\x02" + NUMS_X), ec.mul(tweak))
        if output is None:
            raise Refusal("keyless_tweak_invalid", "Taproot output is at infinity")
        return b"\x51\x20" + output[0].to_bytes(32, "big"), bytes([0xc0 | (output[1] & 1)]) + NUMS_X

    def sigmsg(self, tx: btc.Tx) -> bytes:
        """The epoch-prefixed BIP341 default-hash script message for one reserve input."""
        if len(tx.inputs) != 1 or tx.inputs[0].script_sig:
            raise Refusal("keyless_input_layout", "one native witness input is required")
        item = tx.inputs[0]
        spk, _ = self.taproot()
        return b"".join((
            b"\x00\x00", struct.pack("<iI", tx.version, tx.locktime),
            btc.sha256(item.prev_txid + struct.pack("<I", item.prev_vout)),
            btc.sha256(struct.pack("<Q", self.reserve_sats)),
            btc.sha256(btc.ser_compact(len(spk)) + spk),
            btc.sha256(struct.pack("<I", item.sequence)),
            btc.sha256(b"".join(_output(o.value, o.script_pubkey) for o in tx.outputs)),
            b"\x03\x00\x00\x00\x00", self.annex_hash,
            self.leaf_hash, b"\x02\xff\xff\xff\xff",
        ))

    def witness(self, tx: btc.Tx) -> list[bytes]:
        msg = self.sigmsg(tx)
        _, control = self.taproot()
        return [msg[10:42], msg[74:106], msg[207:], self.script, control, self.annex]

    def spend(self, txid: str, vout: int) -> btc.Tx:
        try:
            previous = bytes.fromhex(txid)
        except ValueError:
            raise Refusal("keyless_outpoint", "reserve txid is not hex") from None
        if len(previous) != 32 or not 0 <= vout <= 0xffffffff:
            raise Refusal("keyless_outpoint", "invalid reserve outpoint")
        tx = btc.Tx(2, [btc.TxIn(previous[::-1], vout, b"", 0xfffffffd)], self.outputs(), 0)
        tx.inputs[0].witness = self.witness(tx)
        return tx

    def record(self) -> dict:
        spk, control = self.taproot()
        return {"status": "approved_keyless_reserve", "network": "regtest",
                "verification": "host-M16", "consensus_policy": "fixed-approved-payout-and-annex",
                "approval": json.loads(self.context_record), "context": self.context.hex(),
                "reserve_sats": self.reserve_sats, "reserve_address": btc.spk_to_address(spk, "regtest"),
                "script_pubkey": spk.hex(),
                "script": self.script.hex(), "control": control.hex(), "annex": self.annex.hex(),
                "txcommit_key": TXCOMMIT_KEY.hex(), "key_version": 2}


def prepare(menu: Menu, order: desk.Order, ledger: Ledger, mining_fee_sats: int = 2000) -> Approval:
    if menu.out_network != "regtest":
        raise Refusal("keyless_needs_regtest", "experimental payouts require isolated patched regtest")
    if not menu.link_op_return:
        raise Refusal("keyless_link_required", "the payout must retain its IOBP payment link")
    if not order.proof_path:
        raise Refusal("proof_required", "a real M16 final proof is required")
    if type(mining_fee_sats) is not int or not 0 < mining_fee_sats < MAX_MONEY:
        raise Refusal("keyless_fee", "mining fee must be a positive satoshi amount")
    try:
        proof = Path(order.proof_path).read_bytes()
    except OSError as error:
        raise Refusal("proof_required", str(error)) from None
    with tempfile.TemporaryDirectory(prefix="iob-keyless-proof-") as directory:
        snapshot = Path(directory) / "proof.bin"
        snapshot.write_bytes(proof)
        result = desk.evaluate(menu, replace(order, proof_path=str(snapshot)), ledger)
    if result["proof"] != "verified":
        raise Refusal("proof_required", "the verifier did not accept this proof")
    amount = result["payout"]["sats"]
    if not 0 < amount < amount + mining_fee_sats <= MAX_MONEY:
        raise Refusal("keyless_fee", "reserve value exceeds the money range")
    recipient = bytes.fromhex(result["sender"]["script_pubkey"])
    link = bytes.fromhex(result["_link"])
    context = {"schema": "IOB/Keyless-M16/v1", "statement_sha256": result["statement_sha256"],
               "proof_sha256": btc.sha256(proof).hex(), "gate_policy": menu.gate_policy(),
               "pricing": {"tiers": [[t.min_value_sats, t.rate_ppm] for t in menu.tiers],
                           "fee_sats": menu.fee_sats, "max_payout_sats": menu.max_payout_sats,
                           "payout_key": menu.payout_key},
               "in_outpoint": result["in"]["outpoint"], "out_network": "regtest",
               "recipient_script": recipient.hex(), "payout_sats": amount,
               "link": link.hex(), "mining_fee_sats": mining_fee_sats}
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return Approval(encoded, recipient, amount, link, mining_fee_sats)


class KeylessPayer:
    def __init__(self, rpc, approval: Approval, reserve_txid: str, reserve_vout: int, broadcast: bool = False):
        self.rpc, self.approval = rpc, approval
        self.txid, self.vout, self.broadcast = reserve_txid, reserve_vout, broadcast

    def pay(self, spk: bytes, sats: int, link: bytes | None) -> dict:
        a = self.approval
        if (spk, sats, link) != (a.recipient_script, a.payout_sats, a.link):
            raise desk.PayError("payout differs from the verifier-approved order", False)
        try:
            chain = self.rpc.call("getblockchaininfo")
            if chain["chain"] != "regtest" or self.rpc.call("getblockhash", 0) != REGTEST_GENESIS:
                raise desk.PayError("keyless payout requires regtest genesis", False)
            if self.rpc.call("getconnectioncount") != 0:
                raise desk.PayError("keyless research node has connected peers", False)
            reserve = self.rpc.call("gettxout", self.txid, self.vout)
            expected_spk, _ = a.taproot()
            if (reserve is None or reserve["scriptPubKey"]["hex"] != expected_spk.hex()
                    or Decimal(str(reserve["value"])) * 100_000_000 != a.reserve_sats):
                raise desk.PayError("reserve is absent or differs from the approved script and amount", False)
            tx = a.spend(self.txid, self.vout)
            raw, txid = tx.serialize().hex(), tx.txid()[::-1].hex()
            admission = self.rpc.call("testmempoolaccept", [raw])[0]
            if not admission.get("allowed"):
                raise desk.PayError("mempool refuses keyless payout: " + str(admission.get("reject-reason")), False)
        except (RPCError, Refusal) as error:
            raise desk.PayError(str(error), False) from None
        if not self.broadcast:
            return {"txid": txid, "hex": raw, "broadcast": False}
        try:
            sent = self.rpc.call("sendrawtransaction", raw)
        except RPCError as error:
            raise desk.PayError(str(error), True) from None
        if sent != txid:
            raise desk.PayError("node returned a different payout txid", True)
        return {"txid": txid, "hex": raw, "broadcast": True}

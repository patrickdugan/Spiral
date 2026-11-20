#!/usr/bin/env python3
"""Observe a signed CSV recovery and reuse on a newly owned Bitcoin Core regtest.

This is a capital-recorder integration probe. It uses a public fixture key and
synthetic demand. It does not implement Ark or a BitVM dispute transaction graph.
"""
from __future__ import annotations

import argparse
import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from lab import analyze

PUBKEY = "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
CSV_BLOCKS = 3
PRINCIPAL = 100_000
SPEND_FEE = 1_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def btc(sats):
    return f"{sats // 100_000_000}.{sats % 100_000_000:08d}"


def fixture_wif():
    payload = b"\xef" + (1).to_bytes(32, "big") + b"\x01"
    raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    number, text = int.from_bytes(raw, "big"), ""
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    while number:
        number, remainder = divmod(number, 58)
        text = alphabet[remainder] + text
    return text


def witness_address(script):
    """BIP173 v0, fixed regtest HRP; Core independently validates the output."""
    program = hashlib.sha256(bytes.fromhex(script)).digest()
    bits, accumulator, data = 0, 0, [0]
    for byte in program:
        accumulator = (accumulator << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((accumulator >> bits) & 31)
    if bits:
        data.append((accumulator << (5 - bits)) & 31)
    hrp = "bcrt"
    values = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + data + [0] * 6
    checksum = 1
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for i, generator in enumerate(generators):
            if (top >> i) & 1:
                checksum ^= generator
    checksum ^= 1
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    return hrp + "1" + "".join(alphabet[v] for v in data + [(checksum >> (5 * (5 - i))) & 31 for i in range(6)])


class OwnedRegtest:
    def __init__(self, binary, datadir):
        self.binary, self.datadir = Path(binary).resolve(), Path(datadir).resolve()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.process = None
        self.log = None

    def rpc(self, method, params=None, wallet=None):
        cookie = (self.datadir / "regtest" / ".cookie").read_bytes().strip()
        suffix = "/wallet/" + urllib.parse.quote(wallet, safe="") if wallet else "/"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{suffix}",
            data=canonical({"jsonrpc": "2.0", "id": "capital-bound", "method": method, "params": params or []}),
            headers={"Authorization": "Basic " + base64.b64encode(cookie).decode(), "Content-Type": "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            result = json.loads(response.read(), parse_float=Decimal)
        if result.get("error"):
            raise RuntimeError(f"{method}: {result['error']}")
        return result["result"]

    def start(self):
        self.datadir.mkdir(parents=True, exist_ok=True)
        self.log = (self.datadir / "node.log").open("ab")
        self.process = subprocess.Popen([
            str(self.binary), f"-datadir={self.datadir}", "-regtest=1", "-server=1",
            f"-rpcport={self.port}", "-rpcbind=127.0.0.1", "-listen=0", "-connect=0",
            "-dnsseed=0", "-discover=0", "-networkactive=0", "-persistmempool=0",
            "-dbcache=16", "-par=1", "-txindex=1", "-fallbackfee=0.00001000",
        ], stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("owned regtest exited during startup")
            try:
                if self.rpc("getblockchaininfo")["chain"] != "regtest":
                    raise AssertionError("owned isolated regtest required")
                return
            except (OSError, urllib.error.URLError, RuntimeError):
                time.sleep(0.1)
        raise TimeoutError("owned regtest startup timed out")

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.rpc("stop")
                self.process.wait(timeout=15)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        if self.log:
            self.log.close()


def run_probe(binary, output):
    if not __debug__:
        raise RuntimeError("the regtest probe requires Python assertions; remove -O and PYTHONOPTIMIZE")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    events, observations, checks = [], [], {}
    started_ns = time.monotonic_ns()
    started = started_ns / 1_000_000_000
    node = None

    def save(name, value):
        raw = canonical(value) + b"\n"
        (output / name).write_bytes(raw)
        return digest(raw)

    with tempfile.TemporaryDirectory(prefix="cbm-regtest-") as temporary:
        node = OwnedRegtest(binary, temporary)
        try:
            node.start()
            node.rpc("createwallet", ["capital-bound"])
            wallet = "capital-bound"
            mine_address = node.rpc("getnewaddress", ["mining", "bech32"], wallet)
            node.rpc("generatetoaddress", [101, mine_address])
            script = "21" + PUBKEY + "ad53b2"  # <fixture key> CHECKSIGVERIFY 3 CSV
            address = witness_address(script)
            script_pubkey = "0020" + digest(bytes.fromhex(script))
            assert node.rpc("validateaddress", [address])["scriptPubKey"] == script_pubkey

            def observe(label, **fields):
                item = {"label": label, "height": node.rpc("getblockcount"),
                        "observer_elapsed_ns": time.monotonic_ns() - started_ns, **fields}
                observations.append(item)
                return item

            def event(kind, **fields):
                events.append({"kind": kind, "height": node.rpc("getblockcount"),
                               "time_s": int(time.monotonic() - started), **fields})

            funding = node.rpc("sendtoaddress", [address, btc(PRINCIPAL)], wallet)
            node.rpc("generatetoaddress", [1, mine_address])
            decoded = node.rpc("getrawtransaction", [funding, True])
            vout = next(v["n"] for v in decoded["vout"] if v["scriptPubKey"]["hex"] == script_pubkey)
            event("run_start", run_id="core-csv-recovery", evidence_level="native_regtest",
                  accounting_boundary="funded CSV output and its descendants; faucet balance excluded; instrumentation probe")
            event("lot_open", lot_id="csv", reserve_id=f"{funding}:{vout}", owner="fixture-owner",
                  amount_sat=PRINCIPAL, state="unavailable")
            destination = node.rpc("getnewaddress", ["recovery", "bech32"], wallet)
            unsigned = node.rpc("createrawtransaction", [[{"txid": funding, "vout": vout, "sequence": CSV_BLOCKS}],
                                                         [{destination: btc(PRINCIPAL - SPEND_FEE)}]])
            previous = {"txid": funding, "vout": vout, "scriptPubKey": script_pubkey,
                        "witnessScript": script, "amount": btc(PRINCIPAL)}
            signed = node.rpc("signrawtransactionwithkey", [unsigned, [fixture_wif()], [previous]])
            if not signed["complete"]:
                raise RuntimeError(f"CSV signing incomplete: {signed.get('errors')}")
            recovery_raw = signed["hex"]
            premature = node.rpc("testmempoolaccept", [[recovery_raw]])[0]
            checks["premature_csv_rejected"] = premature["allowed"] is False
            assert checks["premature_csv_rejected"]
            observe("premature", mempool=premature)
            node.rpc("generatetoaddress", [CSV_BLOCKS - 1, mine_address])
            mature = node.rpc("testmempoolaccept", [[recovery_raw]])[0]
            assert mature["allowed"] is True
            checks["mature_csv_accepted"] = True
            observe("mature", mempool=mature)

            # Restart reads the chain again. The regtest is owned by this process.
            node.stop()
            node.start()
            if wallet not in node.rpc("listwallets"):
                node.rpc("loadwallet", [wallet])
            checks["restart_preserves_maturity"] = node.rpc("testmempoolaccept", [[recovery_raw]])[0]["allowed"] is True
            assert checks["restart_preserves_maturity"]
            tip = node.rpc("getbestblockhash")
            node.rpc("invalidateblock", [tip])
            rollback = node.rpc("testmempoolaccept", [[recovery_raw]])[0]
            checks["reorg_rechecks_maturity"] = rollback["allowed"] is False
            assert checks["reorg_rechecks_maturity"]
            observe("maturity_rollback", mempool=rollback)
            node.rpc("reconsiderblock", [tip])
            assert node.rpc("testmempoolaccept", [[recovery_raw]])[0]["allowed"] is True
            observe("maturity_restored")

            recovery = node.rpc("sendrawtransaction", [recovery_raw])
            node.rpc("generatetoaddress", [1, mine_address])
            unspent = node.rpc("gettxout", [recovery, 0])
            assert unspent is not None and unspent["confirmations"] >= 1
            assert int(unspent["value"] * 100_000_000) == PRINCIPAL - SPEND_FEE
            recovery_receipt = observe("recovery_confirmed", txid=recovery, vout=0, unspent=unspent)
            receipt_hash = save("recovery-receipt.json", recovery_receipt)
            event("lot_replace", parents=["csv"], children=[{
                "lot_id": "recovered", "reserve_id": f"{recovery}:0", "amount_sat": PRINCIPAL - SPEND_FEE,
                "state": "available", "owner": "fixture-owner"}], fee_sat=SPEND_FEE,
                transaction_id=recovery, cause="timeout_spend_confirmed", release_receipt="sha256:" + receipt_hash)
            checks["recovery_unspent_confirmed"] = True

            recipient = node.rpc("getnewaddress", ["synthetic-recipient", "bech32"], wallet)
            amount = PRINCIPAL - 2 * SPEND_FEE
            event("payment_offered", invoice_id="synthetic-reuse", purpose="application", amount_sat=amount)
            event("lot_state", lot_id="recovered", state="unavailable", cause="redeployment")
            reuse_unsigned = node.rpc("createrawtransaction", [[{"txid": recovery, "vout": 0}], [{recipient: btc(amount)}]])
            reuse_signed = node.rpc("signrawtransactionwithwallet", [reuse_unsigned], wallet)
            assert reuse_signed["complete"]
            accepted = node.rpc("testmempoolaccept", [[reuse_signed["hex"]]])[0]
            assert accepted["allowed"] is True
            reuse = node.rpc("sendrawtransaction", [reuse_signed["hex"]])
            node.rpc("generatetoaddress", [1, mine_address])
            reused = node.rpc("gettxout", [reuse, 0])
            assert reused is not None and reused["confirmations"] >= 1
            assert node.rpc("gettxout", [recovery, 0]) is None
            reuse_receipt = observe("redeployment_confirmed", txid=reuse, vout=0, unspent=reused)
            reuse_hash = save("reuse-receipt.json", reuse_receipt)
            event("lot_replace", parents=["recovered"], children=[{
                "lot_id": "recipient", "reserve_id": f"{reuse}:0", "amount_sat": amount,
                "state": "available", "owner": "synthetic-recipient"}], fee_sat=SPEND_FEE,
                transaction_id=reuse, cause="spendable_observed", release_receipt="sha256:" + reuse_hash)
            event("payment_settled", invoice_id="synthetic-reuse", amount_sat=amount, receipt="sha256:" + reuse_hash)
            event("run_end")
            checks["recovered_output_reused"] = True
            ledger = analyze(events)
            assert ledger["fees_paid_sat"] == 2 * SPEND_FEE
            assert ledger["terminal_state_value_sat"]["available"] + ledger["fees_paid_sat"] == PRINCIPAL
            checks["principal_conserved_through_fees"] = True
            source = {"binary_sha256": digest(Path(binary).read_bytes()), "version": node.rpc("getnetworkinfo")["subversion"],
                      "chain": node.rpc("getblockchaininfo")["chain"], "genesis": node.rpc("getblockhash", [0])}
            save("observations.json", observations)
            save("analysis.json", ledger)
            (output / "events.jsonl").write_bytes(b"".join(canonical(e) + b"\n" for e in events))
            report = {"status": "passed", "evidence_level": "native_regtest", "source": source, "checks": checks,
                      "csv_blocks": CSV_BLOCKS, "synthetic_application_volume_sat": amount,
                      "scope": "signed CSV recovery/reuse recorder probe; wallet faucet capital outside boundary",
                      "zk_verified": False, "ark_executed": False, "bitvm_graph_executed": False,
                      "reorg_scope": "one block rollback before release; raw observations retained separately from monotone capital projection",
                      "artifact_sha256": {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}}
            save("report.json", report)
            return report
        finally:
            if node:
                node.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitcoind", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new output directory")
    args = parser.parse_args()
    print(json.dumps(run_probe(args.bitcoind, args.output), indent=2))

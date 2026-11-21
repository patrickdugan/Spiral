"""Loopback-only Bitcoin Core RPC and campaign admission checks."""
import base64
import ctypes
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

GENESIS = {
    "testnet4": "00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043",
    "regtest": "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206",
}
PORT = {"testnet4": 48332, "regtest": 18443}
COIN = 100_000_000
FUNDING_LIMIT = 2_000_000
FEE_LIMIT = 100_000
PAYMENT_LIMIT = 200
ARRIVAL_SECONDS = 48 * 3600
ASSERTION_LIMIT = 4
MIN_OUTPUT = 600
MAX_TIP_AGE = 6 * 3600


class Gate(Exception):
    """A campaign prerequisite failed."""


class RPCError(Gate):
    def __init__(self, method, code):
        self.code = code
        super().__init__(f"Bitcoin Core {method} failed (RPC code {code})")


def sats(value):
    if type(value) not in (str, Decimal, int):
        raise Gate("Bitcoin amount needs an exact decimal representation")
    amount = Decimal(value) * COIN
    if not amount.is_finite() or amount != amount.to_integral_value() or amount < 0:
        raise Gate("Invalid satoshi amount")
    return int(amount)


def btc(value):
    if type(value) is not int or value < 0:
        raise Gate("Invalid integer satoshi amount")
    return f"{value // COIN}.{value % COIN:08d}"


def wallet_names(campaign):
    return f"cbm-{campaign}-payer", f"cbm-{campaign}-recipient"


class Core:
    def __init__(self, network, datadir, port=None):
        self.network = network
        self.datadir = datadir
        self.port = PORT[network] if port is None else port
        if not 1 <= self.port <= 65535:
            raise Gate("Invalid RPC port")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def rpc(self, method, params=None, wallet=None):
        try:
            cookie = (self.datadir / self.network / ".cookie").read_bytes().strip()
        except OSError:
            raise Gate("Bitcoin Core cookie is unavailable for the selected network") from None
        if not cookie or len(cookie) > 1024:
            raise Gate("Invalid Bitcoin Core authentication cookie")
        path = "/wallet/" + urllib.parse.quote(wallet, safe="") if wallet else "/"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps({"jsonrpc": "2.0", "id": "cbm", "method": method,
                             "params": [] if params is None else params}).encode(),
            headers={"Authorization": "Basic " + base64.b64encode(cookie).decode(),
                     "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(8_388_609)
        except urllib.error.HTTPError as err:
            with err:
                raw = err.read(65536)
        except OSError:
            raise Gate(f"Bitcoin Core {method} transport is unavailable") from None
        if len(raw) > 8_388_608:
            raise Gate("Oversized Bitcoin Core response")
        try:
            result = json.loads(raw, parse_float=Decimal)
        except (ValueError, UnicodeError):
            raise Gate(f"Bitcoin Core {method} returned an invalid response") from None
        if not isinstance(result, dict) or result.get("id") != "cbm":
            raise Gate(f"Bitcoin Core {method} returned an unexpected response")
        if result.get("error"):
            raise RPCError(method, result["error"].get("code"))
        return result["result"]


def host_resources(datadir):
    if os.name == "nt":
        memory = (ctypes.c_ulonglong * 8)()
        memory[0] = ctypes.sizeof(memory)
        available = int(memory[2]) if ctypes.windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(memory)) else None
    else:
        try:
            available = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError):
            available = None
    return {"cpu_count": os.cpu_count(), "memory_available_bytes": available,
            "data_volume_free_bytes": shutil.disk_usage(datadir).free}


def chain_tip(core):
    chain = core.rpc("getblockchaininfo")
    if chain["chain"] != core.network or core.rpc("getblockhash", [0]) != GENESIS[core.network]:
        raise Gate("Bitcoin Core network and genesis must match the campaign")
    return chain


def inspect(core, campaign, confirmations):
    receipt = {"network": core.network, "genesis": GENESIS[core.network],
               "confirmations_required": confirmations, "ready": False, "blockers": []}
    try:
        minimum = 2 if core.network == "testnet4" else 1
        if not minimum <= confirmations <= 12:
            raise Gate(f"Confirmation policy must be between {minimum} and 12 blocks")
        chain = chain_tip(core)
        net = core.rpc("getnetworkinfo")
        mempool = core.rpc("getmempoolinfo")
        now = int(time.time())
        age = now - chain["time"]
        work = int(chain["chainwork"], 16)
        receipt.update(height=chain["blocks"], headers=chain["headers"],
                       tip=chain["bestblockhash"], chainwork=chain["chainwork"],
                       block_timestamp=chain["time"], median_time=chain["mediantime"],
                       tip_age_seconds=age, initial_download=chain["initialblockdownload"],
                       version=net["version"], peers=net["connections"],
                       relay_sat_per_kvb=sats(net["relayfee"]),
                       incremental_sat_per_kvb=sats(net["incrementalfee"]),
                       mempool_sat_per_kvb=sats(mempool["mempoolminfee"]),
                       policy_minimum_output_sat=MIN_OUTPUT,
                       signed_candidate_relay_check_required=True,
                       resources=host_resources(core.datadir))
        checks = [
            (net["version"] >= 310100, "Bitcoin Core 31.1 or later is required"),
            (chain["blocks"] == chain["headers"] and work > 0, "Node has unvalidated headers"),
            (receipt["resources"]["data_volume_free_bytes"] >= 64 * 1024**2,
             "Bitcoin Core data volume has less than 64 MiB free"),
        ]
        if core.network == "testnet4":
            checks.extend([
                (chain["blocks"] > 0 and not chain["initialblockdownload"], "Testnet4 is syncing"),
                (net["connections"] > 0, "Testnet4 node has no peers"),
                (-7200 <= age <= MAX_TIP_AGE and chain["mediantime"] <= now + 7200,
                 "Testnet4 tip timestamps are outside the configured window"),
            ])
        receipt["blockers"].extend(message for ok, message in checks if not ok)
        payer, recipient = wallet_names(campaign)
        loaded = core.rpc("listwallets")
        if payer not in loaded or recipient not in loaded:
            raise Gate("The two dedicated campaign wallets must be loaded")
        for name in (payer, recipient):
            info = core.rpc("getwalletinfo", wallet=name)
            if info["walletname"] != name or not info["descriptors"] or not info["private_keys_enabled"]:
                raise Gate("Each campaign wallet must be a dedicated signing descriptor wallet")
            if info.get("scanning") or info.get("unlocked_until") == 0:
                raise Gate("Campaign wallets must be available for signing")
        funds = spendable(core, payer, confirmations)
        receipt["eligible_utxo_count"] = len(funds)
        receipt["eligible_funds_sat"] = sum(row["sat"] for row in funds)
        if not funds:
            receipt["blockers"].append("The payer wallet has no mature, eligible funding outpoint")
    except (Gate, OSError, KeyError, ValueError) as err:
        receipt["blockers"].append(str(err) if isinstance(err, Gate) else
                                   "Required Bitcoin Core or host data is unavailable")
    receipt["ready"] = not receipt["blockers"]
    return receipt


def spendable(core, wallet, confirmations):
    result = []
    for item in core.rpc("listunspent", [confirmations, 9999999, [], False], wallet=wallet):
        if not (item.get("safe") and item.get("solvable") and item.get("spendable", True)):
            continue
        sat = sats(item["amount"])
        if not MIN_OUTPUT <= sat <= FUNDING_LIMIT:
            continue
        result.append({"txid": item["txid"], "vout": item["vout"], "sat": sat})
    return result


def active_output(core, outpoint, confirmations):
    evidence = core.rpc("gettxout", [outpoint["txid"], outpoint["vout"], True])
    if not evidence or evidence["confirmations"] < confirmations:
        return None
    if evidence["coinbase"] and evidence["confirmations"] < 101:
        return None
    if sats(evidence["value"]) != outpoint["sat"]:
        raise Gate("Active outpoint value differs from the journal")
    return evidence


def inclusion(core, txid, blockhash):
    header = core.rpc("getblockheader", [blockhash])
    if header["confirmations"] <= 0 or core.rpc("getblockhash", [header["height"]]) != blockhash:
        raise Gate("Transaction block is outside Bitcoin Core's active chain")
    proof = core.rpc("gettxoutproof", [[txid], blockhash])
    if core.rpc("verifytxoutproof", [proof]) != [txid]:
        raise Gate("Bitcoin Core rejected its transaction inclusion receipt")
    return {"kind": "core_merkle_inclusion", "txid": txid, "blockhash": blockhash,
            "height": header["height"], "block_timestamp": header["time"],
            "confirmations": header["confirmations"], "merkle_proof": proof,
            "scope": "Bitcoin Core active-chain inclusion"}

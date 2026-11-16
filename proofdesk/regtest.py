"""An explicitly separate Bitcoin Core regtest admission path, never labelled ZK."""
from decimal import Decimal
import hashlib
import time

from .domain import Evidence, Refused, canonical, hash32


def payment_from_regtest(core, txid: str, vout: int) -> Evidence:
    hash32(txid,"txid")
    if type(vout) is not int or not 0 <= vout < 2**32:
        raise Refused("invalid_vout")
    before = core.rpc("getblockchaininfo",[])
    if before.get("chain") != "regtest" or before.get("initialblockdownload") is not False:
        raise Refused("isolated_regtest_required")
    tx = core.rpc("getrawtransaction",[txid,True])
    if tx.get("txid") != txid or not tx.get("blockhash") or tx.get("confirmations",0) <= 0:
        raise Refused("confirmed_payment_required")
    output = next((o for o in tx.get("vout",[]) if o.get("n") == vout),None)
    if output is None:
        raise Refused("invalid_vout")
    header = core.rpc("getblockheader",[tx["blockhash"]])
    if core.rpc("getblockhash",[header["height"]]) != tx["blockhash"]:
        raise Refused("payment_reorged")
    tip = core.rpc("getblockheader",[before["bestblockhash"]])
    after = core.rpc("getblockchaininfo",[])
    if before["bestblockhash"] != after["bestblockhash"]:
        raise Refused("chain_changed_retry")
    confirmations = before["blocks"] - header["height"] + 1
    if any("coinbase" in vin for vin in tx.get("vin",[])) and confirmations < 100:
        raise Refused("immature_coinbase")
    value = Decimal(str(output["value"])) * 100_000_000
    if value != value.to_integral_value():
        raise Refused("invalid_amount_encoding")
    script = bytes.fromhex(output["scriptPubKey"]["hex"])
    context = {"network":"regtest","txid":txid,"vout":vout,"block":tx["blockhash"],
               "tip":before["bestblockhash"],"value_sats":int(value),"script":script.hex()}
    context_hash = hashlib.sha256(canonical(context)).hexdigest()
    evidence = Evidence("regtest",txid,vout,int(value),hashlib.sha256(script).hexdigest(),tx["blockhash"],
                        header["height"],before["bestblockhash"],before["blocks"],int(tip["chainwork"],16),
                        confirmations,context_hash,context_hash,"core-regtest")
    evidence.validate()
    return evidence

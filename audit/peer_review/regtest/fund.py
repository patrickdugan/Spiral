"""One-time initial funding of the owned regtest fixture, recorded before reuse."""
from bootstrap import RUNTIME, docker, core
from launch import rpc, bark
from attest import save, DEST
import json
import time


def cln(name, *args):
    result = docker("exec", f"spiral-cln-{name}", "lightning-cli", "--network=regtest", "--lightning-dir=/data", *args)
    return json.loads(result.stdout)


def mine(count):
    core("generatetoaddress", str(count), core("getnewaddress"))
    height = core("getblockcount")
    for attempt in range(300):
        if all(cln(n, "getinfo")["blockheight"] == height for n in ["server", "peer"]):
            return height
        if attempt % 15 == 0:
            print(f"Waiting for controlled CLN nodes to reach {height}", flush=True)
        time.sleep(1)
    raise RuntimeError("CLN chain sync timeout")


def main():
    path = DEST / "initial-funding.json"
    if path.exists():
        raise RuntimeError("Initial funding already recorded; inspect and continue without adding money")
    before = {"chain": core("getblockchaininfo"), "server": json.loads(rpc("wallet").stdout),
              "cln": cln("server", "listfunds"), "bark": json.loads(bark("onchain", "balance").stdout)}
    addresses = {"server": before["server"]["rounds"]["address"],
                 "cln": cln("server", "newaddr")["bech32"],
                 "bark": json.loads(bark("onchain", "address").stdout)["address"]}
    # Dedicated fixture supply: 1M server round reserve, 1M LN wallet, 200k client.
    outputs = {addresses["server"]: 0.01, addresses["cln"]: 0.01, addresses["bark"]: 0.002}
    txid = core("sendmany", "", json.dumps(outputs))
    save("initial-funding.json", {"before": before, "addresses": addresses,
                                 "amounts_sat": {"server": 1000000, "cln": 1000000, "bark": 200000},
                                 "txid": txid, "phase": "broadcast"})
    mine(6)
    peer = cln("peer", "getinfo")["id"]
    cln("server", "connect", peer, "127.0.0.1", "12935")
    funding = cln("server", "fundchannel", peer, "500000sat")
    save("initial-channel-funding.json", funding)
    mine(6)
    for _ in range(30):
        channels = cln("server", "listpeerchannels")
        if channels["channels"] and all(c["state"] == "CHANNELD_NORMAL" for c in channels["channels"]):
            break
        time.sleep(1)
    else:
        raise RuntimeError("channel not operational")
    save("initial-funded-state.json", {"height": core("getblockcount"), "server": json.loads(rpc("wallet").stdout),
                                      "cln_funds": cln("server", "listfunds"), "channels": channels,
                                      "bark_onchain": json.loads(bark("onchain", "utxos").stdout)})
    print("Initial funding and channel are recorded; no subsequent external top-ups authorized by this script.")


if __name__ == "__main__":
    main()

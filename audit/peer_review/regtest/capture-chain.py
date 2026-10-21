"""Read-only full canonical header capture for deterministic offline replay."""
import base64
import json
import time
import urllib.request
from attest import save


def batch(method, parameters):
    result = []
    for start in range(0, len(parameters), 200):
        params = parameters[start:start + 200]
        body = [{"jsonrpc": "2.0", "id": i, "method": method, "params": p} for i, p in enumerate(params)]
        req = urllib.request.Request("http://127.0.0.1:18483", json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(b"spiral:owned-regtest-only").decode()})
        with urllib.request.urlopen(req, timeout=30) as response:
            rows = sorted(json.load(response), key=lambda row: row["id"])
        if any(row.get("error") for row in rows):
            raise RuntimeError("read-only RPC batch failed")
        result.extend(row["result"] for row in rows)
    return result


if __name__ == "__main__":
    before = batch("getblockchaininfo", [[]])[0]
    hashes = batch("getblockhash", [[h] for h in range(before["blocks"] + 1)])
    headers = batch("getblockheader", [[h, True] for h in hashes])
    after = batch("getblockchaininfo", [[]])[0]
    assert before["bestblockhash"] == after["bestblockhash"], "tip changed during collection"
    save("canonical-chain.json", {"evidence_class": "observed-regtest", "captured_unix_ns": time.time_ns(),
         "chain_before": before, "chain_after": after, "headers": headers})
    print(json.dumps({"headers": len(headers), "tip": after["bestblockhash"]}))

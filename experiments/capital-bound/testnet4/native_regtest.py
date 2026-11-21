"""Mine the matched native workloads, exercising restart and rollback."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from campaign import main
from core import wallet_names

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core_regtest import OwnedRegtest


def case(binary, root, profile):
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as view:
        node = OwnedRegtest(binary, Path(tmp))
        observer = None
        try:
            node.start()
            rpc = node.rpc
            if profile == "canary":
                observer = OwnedRegtest(binary, Path(view))
                observer.start()

            def sync_observer():
                if observer is None:
                    return
                before = observer.rpc("getblockcount")
                for height in range(before + 1, rpc("getblockcount") + 1):
                    blockhash = rpc("getblockhash", [height])
                    assert observer.rpc("submitblock", [rpc("getblock", [blockhash, 0])]) is None

            payer, recipient = wallet_names(profile)
            for name in ("faucet", payer, recipient):
                rpc("createwallet", [name, False, False, "", False, True, True])
            miner = rpc("getnewaddress", wallet="faucet")
            rpc("generatetoaddress", [101, miner])
            payin = rpc("getnewaddress", wallet=payer)
            funding = rpc("sendtoaddress", [payin, "0.00100000"], wallet="faucet")
            rpc("generatetoaddress", [2, miner])
            vout = rpc("listunspent", [2], wallet=payer)[0]["vout"]
            commands = ["--network", "regtest", "--campaign", profile, "--state", str(root),
                        "--datadir", tmp, "--rpcport", str(node.port)]
            if observer:
                commands += ["--observer-datadir", view, "--observer-port", str(observer.port)]

            def run(*cmd, expect=0):
                status = main([*commands, *cmd])
                if status != expect:
                    raise AssertionError(f"{cmd}: expected {expect}, got {status}")

            run("preflight")
            run("plan", "--funding", f"{funding}:{vout}", "--profile", profile)
            run("dry-run")
            run("broadcast-canary", expect=2)
            run("broadcast-canary", "--broadcast")
            run("broadcast-canary", "--broadcast")
            node.stop()
            node.start()
            # A direct send may be evicted by an intentional no-mempool restart.
            run("broadcast-canary", "--broadcast", "--retry-same")
            blocks = rpc("generatetoaddress", [2, miner])
            sync_observer()
            run("reconcile")
            get = lambda: json.loads((root / "results.json").read_text(encoding="utf-8"))
            before = get()
            assert len(before["confirmed_txids"]) == 1 and before["terminal_unavailable_sat"] == 0
            run("broadcast-canary", "--advance", "--broadcast", "--retry-same")
            rpc("invalidateblock", [blocks[0]])
            if observer:
                observer.rpc("invalidateblock", [blocks[0]])
            run("reconcile")
            reverted = get()
            assert reverted["confirmed_application_sat"] == 0
            assert reverted["terminal_unavailable_sat"] == 100_000
            rpc("reconsiderblock", [blocks[0]])
            if observer:
                observer.rpc("reconsiderblock", [blocks[0]])
            run("observe")
            phases = {"individual": 6, "batched": 3, "canary": 2}[profile]
            for _ in range(phases - 1):
                # The synthetic trace spans four seconds and uses a common arrival clock.
                time.sleep(2.1 if profile == "canary" else 1.6)
                run("dry-run", "--advance")
                run("broadcast-canary", "--advance", "--broadcast")
                rpc("generatetoaddress", [2, miner])
                sync_observer()
                run("observe")
            run("reconcile")
            result = get()
            assert len(result["confirmed_txids"]) == phases
            assert result["settled_by_deadline_count"] == (2 if observer else 6)
            assert result["settled_by_deadline_sat"] == (2_800 if observer else 11_400)
            assert result["native_merkle_receipts"] == (4 if observer else phases)
            assert result["peak_funded_sat"] == 100_000
            assert result["confirmed_fees_sat"] == phases * 400
            assert len(result["recovery_and_reuse"]) == phases
            assert sum("reuse_after_recovery_seconds" in row
                       for row in result["recovery_and_reuse"]) == phases - 1
            return result
        finally:
            node.stop()
            if observer:
                observer.stop()


def check_artifacts(directory):
    import hashlib

    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((directory / p).read_bytes()).hexdigest() == h
               for p, h in manifest.items())
    assert not any(k in (directory / "transactions.jsonl").read_text(encoding="utf-8")
                   for k in ('"raw"', '"cookie"', '"wallets"'))
    assert json.loads((directory / "testnet4-readiness.json").read_text(encoding="utf-8"))["ready"]


def run(args):
    rows = {}
    for profile in ("individual", "batched", "canary"):
        location = args.out / profile
        rows[profile] = case(args.bitcoind, location, profile)
        check_artifacts(location)
    baseline, batch = rows["individual"], rows["batched"]
    assert baseline["offered_sat"] == batch["offered_sat"]
    assert baseline["settled_by_deadline_sat"] == batch["settled_by_deadline_sat"]
    assert baseline["confirmed_fees_sat"] - batch["confirmed_fees_sat"] == 1_200
    comparisons = {
        "scope": "isolated regtest, one matched workload",
        "source_sha": args.source_sha,
        "baseline": baseline,
        "batched": batch,
        "independent_canary": rows["canary"],
        "batch_fee_savings_sat_at_fixed_fee_per_transaction": 1_200,
        "batch_settlement_virtual_bytes_saved": (baseline["settlement_virtual_bytes"]
                                                  - batch["settlement_virtual_bytes"]),
        "unavailable_sat_blocks_difference": (baseline["unavailable_sat_blocks"]
                                              - batch["unavailable_sat_blocks"]),
        "matched_pairs": 1,
        "confidence_interval": None,
        "regtest_checks": ["explicit broadcast", "same-transaction retry", "node restart",
                           "confirmed rollback", "recovery", "actual reuse", "artifact digests"],
    }
    (args.out / "comparison.json").write_text(json.dumps(comparisons, indent=2) + "\n",
                                                encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitcoind", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-sha", default=None)
    run(parser.parse_args())

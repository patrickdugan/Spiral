#!/usr/bin/env bash
set -euo pipefail
umask 077

core=/root/opt/bitcoin-31.1/bin/bitcoind
printf '%s  %s\n' 986e63b3c8770f08d0059820ad3dd085d1ab9e1bea23946c243f858a06888a08 "$core" | sha256sum -c --quiet -
rust=/root/.cargo/bin/cargo
"$rust" test --release --locked --offline -p shz-nova-bitvm --features mnr04-nova mnr04::
"$rust" build --release --locked --offline --bin shz --features mnr04-nova

run=$(mktemp -d /var/tmp/shz-mnr04-netting.XXXXXXXX)
printf 'Replaying on Core in %s\n' "$run"
bash <(tr -d '\r' < scripts/bench-mnr04.sh) "$CARGO_TARGET_DIR/release/shz" "$core" "$run/replay"
python3 - "$run/replay" <<'PY'
import hashlib, json, pathlib, sys

run = pathlib.Path(sys.argv[1])
report = json.loads((run / "benchmark.json").read_bytes())
core = report["core"]
native = core["native"]
verified = report["independent_verification"]
accounting = core["native_pnl_accounting"]
proof = run / "proof" / "proof.bin"
destinations = ("bob-ab", "bob-bc", "alice", "carol", "anchor")
assert core["consensus_accepted"] and core["reorg_watchtower_frozen"]
assert native["funded_sats"] == accounting["total_input_sats"] == 244_000_000
assert native["fee_sats"] == accounting["total_fee_sats"] == 2670
assert [accounting["vault_residuals_sats"][key] for key in destinations] == native["payout_sats"]
assert verified["vk_sha256"] == "7fc71a8518976ede1ad97855ee164e63356e4ef11cda43565e1177fa5f082db1"
assert hashlib.sha256(proof.read_bytes()).hexdigest() == verified["proof_sha256"]
assert verified["proof_bytes"] == proof.stat().st_size == 12_224
print(json.dumps({"run": str(run), "txid": native["txid"], "wtxid": native["wtxid"],
                  "proof_sha256": verified["proof_sha256"], "proof_bytes": verified["proof_bytes"],
                  "payout_sats": native["payout_sats"], "fee_sats": native["fee_sats"]}))
PY

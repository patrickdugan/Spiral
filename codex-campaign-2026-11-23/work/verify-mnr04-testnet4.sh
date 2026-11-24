#!/usr/bin/env bash
set -euo pipefail
umask 077
bin=/var/tmp/shz-mnr04-target/release/shz
fixture=evidence/mnr03_testnet4_bob_offline_receipt.json
out=/var/tmp/shz-mnr04-testnet4-20261123
mkdir "$out"
"$bin" mnr04-prove "$fixture" "$out/proof" > "$out/prove.json"
"$bin" mnr04-verify "$fixture" "$out/proof" 7fc71a8518976ede1ad97855ee164e63356e4ef11cda43565e1177fa5f082db1 > "$out/verified.json"
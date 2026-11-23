# Private Signet: Keyless-CHECKSIG / BitVM experiment

A **local, self-mined Bitcoin Core custom Signet**: a miner node holding a
disposable block-signing key, an observer node that validates independently,
and Bitcoin Core's official `contrib/signet/miner`. On top of it, an A/B
harness compares a vanilla DLC settlement with the proposed Keyless-CHECKSIG
(TXCOMMIT) construction, the latter on a patched Bitcoin Core regtest.

**Status (2026-11-23):** working.

- **Private Signet:** 101 signed blocks mined, observer agreement on every
  hash and on chainwork, and a wallet transaction confirmed.
- **Vanilla DLC:** an adaptor-signature DLC was settled on the private Signet
  under stock consensus.
- **Keyless-CHECKSIG A/B:** 37 trials on three regtest validators (patched
  Core with the rules on, the same binary with them off, and stock Core) all
  match their expected verdicts.
- **Keyless-CHECKSIG on a patched custom Signet:** an arm B settlement was
  included by the authorized signer and accepted by the patched observer and
  by a stock legacy node. A forbidden spend in a correctly signed block was
  rejected by both patched nodes; the stock node accepted it and forked
  (RESULTS.md, K4 / C1).

Results, measurements and the security analysis are in [RESULTS.md](RESULTS.md),
and the raw receipts in [evidence/](evidence/).

Keyless-CHECKSIG is **not** active on any public network. The patched
build refuses `-keylessresearch` on the default Signet; it needs a custom
`-signetchallenge`. A stock node does
not enforce its commitment semantics: on stock rules every witness-v2 (P2MR)
spend is valid, theft included. Use valueless test coins and disposable keys
only.

## Requirements

- Linux or WSL2 with Python 3.10+ (standard library only).
- Bitcoin Core `bitcoind` and `bitcoin-cli` on PATH, or as absolute paths in
  `BITCOIND` and `BITCOIN_CLI`. `bitcoin-util` (`BITCOIN_UTIL`) is optional:
  without it the official miner grinds proof-of-work itself, which takes about
  12 s per block at Signet's minimum difficulty.
- The official Signet miner from the **same** Core version (`SIGNET_MINER`).
  A sparse checkout is enough:

~~~bash
git clone --depth 1 --branch v31.1 --filter=blob:none --sparse https://github.com/bitcoin/bitcoin.git core-src
git -C core-src sparse-checkout set contrib/signet test/functional/test_framework
export SIGNET_MINER=$PWD/core-src/contrib/signet/miner
~~~

Pinned versions used for the recorded runs:

| Component | Local run | CI |
|---|---|---|
| Bitcoin Core | 31.1 (`/Satoshi:31.1.0/`) | 30.2 release tarball, SHA256 `6aa7bb4f…75d8` |
| Signet miner | v31.1 tag `9be056a8`, miner SHA256 `2df980a4…dffe` | v30.2 tag |
| Python | 3.12.3 | 3.12 |
| Patched Core (A/B) | `d0f6d995` (v30.0) + Spiral patch, diff SHA256 `e6b3e5db…2bc6` | same, built in CI |
| Patched Core (Signet, with wallet) | same + `core/patch_core_signet.py`, diff SHA256 `6eb2ae41…ebcf1` | same, built in CI |

## Run

From the Spiral repository root:

~~~bash
export SPIRAL_SIGNET_HOME=$HOME/.local/share/spiral-private-signet   # empty, private
python3 "Private Signet/lab.py" init           # bootstrap key, miner + observer
python3 "Private Signet/lab.py" mine --blocks 101
python3 "Private Signet/lab.py" agree          # genesis, height, every hash, chainwork
python3 "Private Signet/lab.py" fund-demo      # fresh wallet, signed payment, mined, UTXO on both nodes
python3 "Private Signet/ab/run_signet_dlc.py"  # vanilla adaptor DLC settled on the Signet
python3 "Private Signet/ab/run_signet_rollover.py"  # Alice/Bob -> Carol/Bob on-chain; reject old CET
python3 "Private Signet/lab.py" destroy        # stop both nodes, delete the lab home
~~~

Patched-Core A/B on regtest (build steps are in `.github/workflows/private-signet.yml`):

~~~bash
python3 BIPSpace/Keyless-CHECKSIG/core/patch_core.py <core-d0f6d995>
python3 BIPSpace/Keyless-CHECKSIG/verifiers/patch_core_regtest.py <core-d0f6d995>
# build bitcoind, then:
python3 "Private Signet/ab/run_ab_regtest.py" --patched <patched bitcoind> --stock <stock bitcoind> --output ab.json
~~~

Patched custom Signet with a stock legacy node (apply `core/patch_core_signet.py`
too and build with the wallet):

~~~bash
export SPIRAL_SIGNET_HOME=$HOME/.local/share/spiral-keyless-signet SPIRAL_SIGNET_PORT_BASE=39532
export BITCOIND=<patched bitcoind> BITCOIN_CLI=<patched bitcoin-cli> BITCOIN_UTIL=<patched bitcoin-util>
export SPIRAL_SIGNET_BITCOIND_ARGS=-keylessresearch=1 BITCOIND_LEGACY=<stock bitcoind>
python3 "Private Signet/lab.py" init
python3 "Private Signet/lab.py" mine --blocks 101
python3 "Private Signet/ab/run_signet_keyless.py"   # K4, C1, K3; then all nodes agree
~~~

`SPIRAL_SIGNET_PORT_BASE` moves all loopback ports (default 39432). The
lab never opens public seeds, mainnet, Testnet4 or another node's data
directory.

## What is running

| Node | RPC | P2P | Purpose |
|---|---:|---:|---|
| Bootstrap (stopped after init) | base | base+1 | Generate the signer key in a throwaway OP_TRUE Signet |
| Miner | base+10 | base+11 | Signer wallet `signer`, reward wallet `funds` |
| Observer | base+20 | base+21 | Independent validation; connects only to the miner |
| Legacy (optional, `BITCOIND_LEGACY`) | base+30 | — | Stock binary, old rules; follows the miner, no listener |

The challenge is `PUSH33 <signer pubkey> OP_CHECKSIG`. The signer's private
descriptors stay in `PRIVATE-descriptor-backup.json` under the lab home
(mode 0600). They must never be committed; `evidence/` holds only public
receipts.

## Defects fixed in the scaffold

| Defect | Effect | Fix |
|---|---|---|
| `init` called the miner RPC through `read_state()` before `state.json` existed | `init` aborted after starting the miner | pass the challenge explicitly; write a provisional state |
| Miner `--cli` lacked `-signet` | bitcoin-cli would not address the Signet node | add `-signet` |
| Bare P2PK challenge, but only `wpkh`/`tr`/… ranges imported | `PSBT signing failed`; no block (control run in `evidence/signet/signing-control.txt`) | import a private `pk()` descriptor for the challenge key |
| `-rpcwait` does not wait for the cookie file | observer start failed intermittently | wait for `.cookie` first |
| Miner backdates blocks; a fresh descriptor wallet skips blocks before its birth time | 101 blocks mined, 24 coinbases credited, "Insufficient funds" | `rescanblockchain` after mining |
| `bitcoin-util` was mandatory | mining impossible without it | optional; the miner grinds itself |

## Follow-on: exclusive payout rights after an on-chain rollover

[ROLLOVER_DESIGN.md](ROLLOVER_DESIGN.md) defines a fresh Carol/Bob Taproot
DLC funded by an Alice/Bob-signed transition. The integration runner checks
that Alice's original valid CET is rejected once that original outpoint is
confirmed spent, the former Alice/Bob key pair cannot sign the successor,
and a fresh Carol/Bob adaptor CET pays the buyer. This needs Bob's
cooperation and an on-chain confirmation, with a possible race before
confirmation and chain-reorganization risk afterward. It is a baseline
for investigating a stronger off-chain or keyless transfer mechanism.

## Static validation

~~~bash
python3 -m unittest discover -s "Private Signet" -p test_lab.py -v
python3 -m unittest discover -s "Private Signet/ab" -p test_ab.py -v
~~~

## References

- [BIP325, Signet](https://bips.dev/325/)
- [Bitcoin Core Signet miner](https://github.com/bitcoin/bitcoin/blob/master/contrib/signet/README.md)
- [Keyless-CHECKSIG research BIP](../BIPSpace/Keyless-CHECKSIG/bip-keyless-checksig.md)
- [A/B protocol](AB_TEST_PLAN.md)

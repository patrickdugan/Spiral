# Testnet4 BitVM primitives and Nova in BitVM3

This directory stages three demos:

| Demo | Execution | Meaning |
| --- | --- | --- |
| NAND | Stock Tapscript | Refute a fixed false `NAND(a,b)=out` claim with three committed openings and a challenger signature. |
| Half-adder | Stock Tapscript | A five-NAND trace has one refutation leaf per gate. The false sum is gate 3. |
| Nova / BitVM3 M14 | Native and actual garbled circuit | Verify the existing SP1/BLAKE3-v2 proof of a complete Nova verifier for Testnet4 heights 0–4; reject a tampered proof input and a different statement. |

The first two are fixed-claim fraud-proof primitives, not a complete BitVM bridge or dispute graph. Each wire's **claimed bit and opening hash are pinned in the funded Script**. A refutation succeeds only when the three openings match and the claimed NAND equation is false. A separate Schnorr-protected leaf refunds collateral after two blocks. Keys are generated freshly; example/public-vector keys never receive public test coins. The NUMS internal key is a Taproot construction, not P2MR.

The Nova proof is real, and the M14 test runs all **785,442,492 non-free gates** with **8,635,080 input bits** in each of three cases. It uses the upstream deterministic seed and streaming half-gates API. To fit WSL RAM, the garbler and evaluator run sequentially through one **12,567,079,872-byte temporary ciphertext file** per case. The file is removed after each case; allow at least 13 GB of scratch disk space. A separate Rust test checks the file transport, including truncated records. Gate counts and all proof acceptance/rejection assertions remain enabled. It does not implement deployed OT, cut-and-choose or the Bitcoin dispute transaction graph. It reuses a completed proof and performs no GPU proving. Its optional Testnet4 `OP_RETURN` is `BVM3 || 01 || SHA256(canonical receipt)`: **a receipt commitment, not execution of Nova by Bitcoin**. Receipt format validation is not cryptographic proof authentication by the anchor.

Public contracts use deployed opcodes and ordinary BIP340/BIP341 signatures (`key_version=0`). Experimental Keyless CHECKSIG/TXCOMMIT and CAT remain a separate patched-regtest research demo; public Testnet4 does not activate them.

## Requirements and quick local run

Use installed Python 3.12, pytest, Bitcoin Core 31.1 and an existing Rust toolchain with cached GSV dependencies. No installer runs. Python transaction/Script helpers reuse this repository's `in-and-out-burger/iob` and BIP341 serializer; the latter is called with explicit stock key versions. Run from this directory, or adjust the paths below.

```powershell
$env:TEMP = '<writable scratch directory>'
$env:TMP = $env:TEMP
python -m pytest tests -q --basetemp '<fresh pytest directory>'
```

On Linux/WSL, mine and validate the contracts with **stock** Core and zero peers:

```bash
python3 scripts/regtest.py \
  --core /path/to/bitcoin-31.1/bin/bitcoind \
  --fixture-source /path/to/bitcoin-rs-keyless \
  --output /path/to/fresh-stock-regtest-run
python3 scripts/check_receipts.py /path/to/fresh-stock-regtest-run/report.json
```

`--fixture-source` supplies the node/RPC harness from bitcoin-rs commit `cbc0a28badcb93cd643729ac7105c0bdf99a9158`; it enables no research feature in Core. The campaign tests four NAND input combinations, the half-adder, honest-claim refusal, altered openings/signatures/outputs/control paths/annexes, premature refunds, replay and restart. Receipts contain raw positive blocks and transactions. The independent checker checks PoW, block links, Merkle roots, witness commitments, claim openings, Taproot controls and Schnorr signatures.

## Nova / BitVM3

Use a dedicated checkout of [patrickdugan/garbled-snark-verifier](https://github.com/patrickdugan/garbled-snark-verifier/tree/fcddd4d773f52953387eed4b55beaab47c84155a) at `fcddd4d773f52953387eed4b55beaab47c84155a`. Preserve other workers' checkouts. `scripts/nova_gc.py` refuses unrelated tracked/untracked changes and appends only the supplied exact test overlay to `nova-bitvm3/m14/e2e/tests/garbled.rs`. It accepts a checkout already carrying that exact overlay. The proof SHA-256 is `79c4af1113506bba24415d058557bba93583d5177ec074f13ba30f705c85daad`; the public final statement SHA-256, after normalizing CRLF to LF only, is `06fa3156d86ffb98f0a853cbd350b144f81d1586c6eda7d70c436267f821b007`. The receipt separately records the actual statement file's raw hash. For WSL builds, use a Linux-filesystem checkout; transferring a Git bundle avoids slow per-file access to a Windows checkout.

```bash
python3 scripts/nova_gc.py \
  --source /path/to/dedicated-gsv-checkout \
  --toolchain /path/to/existing/rust-toolchain/bin \
  --target /path/to/dedicated-build-cache \
  --output /path/to/fresh-nova-run \
  --jobs 2 --build-timeout 3600 --timeout 3600 --aesni
```

This builds with `--offline --locked`, records exact commands, tool versions, fixture/source/diff/binary/log digests, runs the transport integrity test and then runs each full verifier case in a fresh process. `--timeout` applies to each case. Each process must execute exactly its selected case, retain every gate/proof assertion and exit successfully; the overall receipt is passed only after all three succeed. This avoids one case's memory retention or runtime exhausting the next case's allowance. Native final verification also checks the real proof and rejects the wrong statement. A timed-out or stopped attempt is a failed attempt; reuse its cache in a **fresh** output directory. Do not report a build-only run as verification. The overlays only append tests; no upstream verifier code is changed.

On x86-64, `--aesni` first compiles and executes a CPU-feature probe, checks the compiler configuration, and sets `RUSTFLAGS=-C target-feature=+aes,+sse2` for this process. The upstream implementation otherwise chooses software AES, which is much slower. The resulting binary requires those CPU features; omit this option on other hardware. `--build-only` warms the cache and returns `built_not_verified`; it cannot produce an anchorable passed receipt.

The inner compressed Nova proof is a separate 12,040-byte object inside the 12,596-byte `.nht4` bundle. Its SHA-256 is `66c903b0e23876bf7c50414d6b2bfe451a256a6f44a7ba0d5b1c27e30addd7e4`; the bundle SHA-256 is `ffa1fdbc8a7ef712941434db51c2c780232f5a2190f225bca640ab5a4d6c5f3c`. The guest statement binds the network, k=1, four steps, checkpoint, final state, verifier key and inner proof. This demo verifies the completed wrapper; it does not regenerate that expensive proof.

## Genuine Testnet4

Use a synced observer and the dedicated offline wallet. All endpoints must report `chain=testnet4` and genesis `00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043`. A `tb1` prefix alone does not identify Testnet4. Existing observer wallets are never accessed.

On Windows, create a **fresh** offline signer with the installed Core binary:

```powershell
.\scripts\start-signer.ps1 `
  -BitcoinDirectory '<Core bin directory>' `
  -PrivateDirectory '<outside this source checkout>\signer' `
  -SetupFile '<public evidence directory>\wallet-setup.json'
$env:PYTHONPATH = $PWD
python -m bitvm_demo plan --private-dir '<outside checkout>\protocol' --output '<fresh public plan directory>'
```

The start script pins the observed Windows Core 31.1 binary digest. For a different installed build, independently verify its identity and explicitly pass `-ExpectedCoreSha256`. It starts only a Testnet4 node with zero peers, wallet broadcasting disabled, loopback RPC and a new `bitvm-demo` wallet. Keep the private data directory and protocol state out of Git/public evidence. Stop this owned node later with its exact datadir, Testnet4 and recorded RPC port; never stop other workers' nodes.

Set common command arguments (PowerShell):

```powershell
$demoRpc = @('--cli', '<bitcoin-cli.exe>', '--observer-data', '<synced Testnet4 datadir>', '--signer-owner', '<signer>\owner.json')
python -m bitvm_demo status @demoRpc
python -m bitvm_demo signing-check @demoRpc --wallet-setup '<wallet-setup.json>'
python scripts/check_testnet_fixture.py --cli '<bitcoin-cli.exe>' --observer-data '<synced Testnet4 datadir>' --gsv-source '<dedicated GSV checkout>' --output '<fresh fixture receipt.json>'
```

`signing-check` signs a synthetic previous output offline and independently verifies the key-path signature and output binding. It broadcasts nothing. The fixture command compares headers 0–4 with the observer, including the claimed height-4 hash and chainwork.

Send **100,000 Testnet4 sats (0.001 tBTC)** to the newly generated setup address and wait for confirmation. The funding command checks the public Testnet4 API's genesis, then requires its coin value/script/confirmation to agree with the verified observer and dedicated wallet. It uses one confirmed 60,000–1,000,000-sat coin; smaller/larger coins are ignored. Funding creates two 20,000-sat contracts, a receipt anchor when a passed Nova receipt is supplied, and owned change. It charges 2,000 sats; each refutation returns 18,000 sats to a fresh owned address with a 2,000-sat fee.

```powershell
python -m bitvm_demo fund @demoRpc `
  --wallet-setup '<wallet-setup.json>' --private-dir '<protocol>' `
  --nova-receipt '<passed Nova report.json>' --output '<fresh funding directory>'
# Review the signed funding receipt. Repeat with a fresh output directory and --broadcast to send.
# After its confirmation:
python -m bitvm_demo refute @demoRpc `
  --funding '<broadcast funding directory>\funding.json' --private-dir '<protocol>' `
  --output '<fresh refutation directory>'
# Add --broadcast to send the two prepared refutations; then wait for confirmations.
```

Commands default to signing and mempool admission checks. Only explicit `--broadcast` sends transactions. The signer remains offline; the observer sends. Save receipts for funding, refutations and confirmed blocks. Without test coins/confirmations the public portion remains staged, and local regtest success must not be described as a public Testnet4 spend.

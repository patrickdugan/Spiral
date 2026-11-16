# Cashu to Ark withdrawal

The encrypted Node wallet supports the CDK custom `arkoor` melt method through
the locally ported [Bark payment processor](../integrations/bark-processor).
The port starts from `cashubtc/cdk-payment-processors` commit
`d7244e261506b51d5b309a558bf19cd4ffc32f13` and pins CDK 0.18.3 and Bark 0.8.1.
Wallet dispatch is restricted to the desk's isolated `regtest` profile.

Use the same vault, mint and desk endpoints used for the original deposit. Keep
`PROOF_GROVE_WALLET_PASSWORD` in the client environment. Obtain a fresh receiving
address from the recipient's Bark wallet, then quote the withdrawal:

```bash
node wallet/cli.mjs ark-quote --id SOURCE_OPERATION_ID --destination ARK_ADDRESS --amount 10000 --max-fee 0 --vault .runtime/my-wallet.sqlite --mint http://127.0.0.1:MINT_PORT --desk http://127.0.0.1:DESK_PORT
node wallet/cli.mjs ark-pay --payment PAYMENT_ID --vault .runtime/my-wallet.sqlite --mint http://127.0.0.1:MINT_PORT --desk http://127.0.0.1:DESK_PORT
node wallet/cli.mjs ark-status --payment PAYMENT_ID --vault .runtime/my-wallet.sqlite --mint http://127.0.0.1:MINT_PORT --desk http://127.0.0.1:DESK_PORT
```

`ark-quote` binds the saved payment to its mint quote, destination, amount, input
balance and fee limit. The fee limit includes Cashu input fees and the quoted
payment fee reserve. A changed destination, insufficient balance, expired quote,
spent inputs or increased fee stops dispatch. `ark-list` displays saved payments;
`list` displays each deposit's original amount and current Cashu balance.

Before submitting a melt, `ark-pay` commits the exact input proofs and change
output secrets in the encrypted vault, and reserves the source balance. An
uncertain result keeps that reservation. Repeating `ark-pay` cannot resend it.
Use `ark-status` after a restart to query the original quote. The client requires
spent original inputs, reconstructs only the saved change outputs, verifies DLEQ
signatures and unspent states, and checks the actual fee before replacing the
old proofs with change. It can use NUT-09 when the paid quote omits change
signatures. An unpaid or inconsistent result keeps the proofs reserved for
further reconciliation. There is no automatic cancellation or unlock after an
uncertain dispatch.

`cashu_redeemed` establishes the mint-reported redemption and verified change.
It is not proof that the recipient owns an Ark payment. Independently read the
recipient's Bark wallet, match its fresh address and exact amount to a received
movement, and identify the new VTXOs. Bark validates their signatures and
ownership. Arkoor reception has counterparty risk until a refresh or an exit
removes the dependency on the sender. The caretaker can reconcile a delegated
refresh and check its successor anchors against Core. Ark timelocks and refresh
requirements still apply. The released REST signer has no fee cap at signing;
production refresh writes remain disabled.

## Reproduce the combined native test

Install the wallet's locked dependencies. In Linux/WSL, build the processor with
Rust, protoc, clang, cmake and pkg-config:

```bash
cd integrations/bark-processor
cargo test --locked --lib
cargo build --locked --features regtest-control --bin cdk-payment-processor-bark --example regtest-liquidity
cd ../..
python3 tests/run-ark-stack.py --bark /ABS/barkd-0.8.1-linux-x86_64 --server-config-template /ABS/captaind.default.toml --test-cashu-exit --cdk /ABS/cdk-mintd-0.18.3-x86_64 --node /ABS/node --processor /ABS/target/debug/cdk-payment-processor-bark --liquidity-helper /ABS/target/debug/examples/regtest-liquidity
```

The foreground supervisor creates a new Core 31/Ark 0.8.1 stack, binds host ports
only on loopback and verifies resource ownership before cleanup. It verifies
official CDK/Bark binary hashes and pins container images. It never selects an
existing user wallet. The `regtest-control` helper requires the regtest network
and a loopback Core source before opening its wallet; it is not exposed as an
RPC service. All mnemonics, passwords and coins in this test are public fixtures.

The test uses BDK for deposit accounting and a separately prefunded Ark wallet
for withdrawals. The upstream Bark deposit path deducts boarding costs; this
prototype does not silently credit its net amount as the gross proof amount.
Neither arrangement proves the mint's reserves or makes it noncustodial.

The test funds a 25,000 sat quote, admits the actual Core payment, issues verified
Cashu proofs and withdraws 10,000 sats to a fresh Ark address. A proxy drops the
successful melt reply. New wallet processes reconcile it without another melt,
recover 15,000 sats of change, check the recipient's VTXOs and refresh them into
a Core-confirmed successor. The report records the separate refresh fee and
checks the successor again after the mint and processor stop. With
`--test-cashu-exit`, it then funds separate CPFP fee coins, exports the exact
successor's exit package, stops the Ark server, pauses the owner wallet and runs
the independent Core-only watcher. The owner resumes to sign the final claim
while both mint and Ark server stay offline. The report binds the exit input to
the withdrawal's exact successor and separates refresh, CPFP and final claim
fees. Use `--test-cashu` for the withdrawal/refresh portion alone. No bearer proof
or private wallet key is written to the public report.

The historical M16 verifier, this combined regtest test and the separate
[offline exit test](ark-recovery.md) establish different facts. This test does
not create a new Nova proof, demonstrate a funded BitVM bridge or prove reserve
solvency. The exit extension uses extra valueless fixture coins for fees.

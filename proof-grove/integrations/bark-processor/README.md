# Proof Grove Bark payment processor port

This is a local adaptation of [`cashubtc/cdk-payment-processors`, `crates/bark`](https://github.com/cashubtc/cdk-payment-processors/tree/d7244e261506b51d5b309a558bf19cd4ffc32f13/crates/bark), commit `d7244e261506b51d5b309a558bf19cd4ffc32f13`. It pins CDK **0.18.3** and Bark **0.8.1**, revision `303682063ed7559b06dcf37c5cb37bb7037b943f`. See `UPSTREAM.json`, the retained MIT/Apache licenses and `CHANGELOG.md`.

The upstream implementation supplies a standalone gRPC `MintPayment` backend, durable payment intents and on-chain, BOLT11 and custom `arkoor` methods. This port's combined native test exercises **outgoing arkoor** alongside CDK's independent BDK on-chain deposit backend. It does not certify every upstream payment path.

## Build

Install Rust, protoc, clang, cmake and pkg-config, then:

```bash
cargo check --locked --all-targets --features regtest-control
cargo test --locked --lib
cargo build --locked --features regtest-control --bin cdk-payment-processor-bark --example regtest-liquidity
cargo fmt -- --check
```

The optional `regtest-tests` feature retains the upstream full CLN/Nix integration harness for provenance. That harness has not been ported or verified with Bark 0.8.1; use Proof Grove's supervisor for this integration. The upstream Nix files are not included.

## Configuration

The daemon loads `config.toml` in its working directory. The upstream public example is in `config.toml.example`. It contains public example keys, never use them for real funds. Proof Grove generates fresh **valueless regtest fixtures**:

```toml
address = "127.0.0.1"
port = 50051
allow_insecure = true

[bark]
mnemonic = "PUBLIC_REGTEST_FIXTURE_ONLY"
network = "regtest"
server_address = "http://127.0.0.1:ARK_PORT"
bitcoind_address = "http://127.0.0.1:CORE_PORT"
bitcoind_user = "second"
bitcoind_password_env = "PG_TEST_RPC_PASSWORD"
data_dir = "/ABS/NEW_FIXTURE_WALLET"
event_poll_interval_ms = 500
payment_methods = ["arkoor"]
```

`bitcoind_password_env` names an environment variable; its value is not a password. When a Core source is configured, Esplora is disabled. The URL must use loopback HTTP/HTTPS without embedded credentials, query or fragment. This local-source restriction does not validate ownership of an existing wallet; the supervisor always allocates a new data directory.

CDK 0.18 uses a bare gRPC host, without a URI scheme:

```toml
[payment_backend]
backend = "grpcprocessor"
unit = "sat"

[grpc_processor]
supported_units = ["sat"]
address = "127.0.0.1"
port = 50051
allow_insecure = true
```

Advertise only `arkoor` when another backend owns the `sat/onchain` pair. In this test, BDK credits the deposit and separate Ark liquidity funds the withdrawal. The Bark on-chain backend boards deposits after confirmation and deducts boarding costs; it must not silently replace gross-value deposit accounting.

Cleartext gRPC is explicitly enabled for this loopback fixture. Upstream mTLS support is retained (`tls_enable`, `tls_cert_path`, `tls_key_path`, `tls_client_ca_path`); its configuration and other payment methods are outside this combined test. The service handles SIGINT and SIGTERM.

## Fixture liquidity helper

The explicit `regtest-control` feature exposes `regtest-liquidity` as a local example binary, not as a gRPC method. It refuses non-regtest configurations and requires the local Core profile before opening a wallet. It supports `address`, `board AMOUNT_SATS` and `status`. Run it only while the processor is stopped; never let both processes mutate the same wallet.

See [withdrawal guide](../../docs/cashu-ark-withdrawal.md) for the owned Core/Ark/CDK supervisor, lost-response recovery and recipient validation. A mint payment string such as `arkoor-movement-123` is a local receipt identifier, not proof of Bitcoin settlement or a recipient VTXO. Cashu stays custodial until redemption; this port supplies no solvency proof.

# Bounded testnet4 execution preparation

`preflight.py` is a read-only preparation gate for section 3 of the
[existing protocol](../testnet4_plan.md). It has offline adversarial tests;
its live run currently stops at unconfirmed wallet funds. No funding,
activation or payment-clock observation is produced by a successful preflight.

The user identified an existing local testnet4 installation on 2026-10-21.
It was stopped; it has now been started and caught up at height 157210.
A separate experiment wallet observes 500,000 test sats supplied by the user
and 10,000 test sats from a faucet, both unconfirmed at the captured checkpoint.
See [the public funding observation](funding-observation-20261021.json).
The earlier absent-endpoint preflight is historical and did not discover this
stopped installation. Four dedicated CLN peers are now synchronized at height
157211 with empty wallets and exactly the required diamond connections; see
[peer setup evidence](peer-provisioning-20261021.json). The
[live gate](preflight-pending-funding-20261021.json) records 510,000 pending sats
and refuses channel funding until confirmation. The preflight script
checks that starting condition; it does not start services, connect peers,
create wallets, open channels or send payments.

## Executed local setup

`provision.py` prepares empty peers in a separate private WSL runtime. It uses
the pinned CLN v26.06.7 image and checks the running daemon binary digest. The
existing Windows Core 31.1 daemon stays bound to Windows loopback. An
authenticated WSL loopback bridge (`interop_rpc.py`) invokes its Windows CLI
through WSL executable interop with an RPC allowlist and no shell. Wallet
methods are unavailable through the bridge, and transaction broadcast is
disabled in the current private bridge configuration. Daemon secrets and
wallets remain outside Git.

The CLN image's bundled Bitcoin CLI rejected `-testnet4` during startup, despite
the daemon supporting that network. The effective configuration therefore
selects the already pinned Linux Core 31.0 CLI explicitly; its executable hash
and source image are recorded alongside Core 31.1 and CLN. This adapter adds
local RPC transport overhead, which must be distinguished from future network
clock measurements. The setup does not change the user's saved Core config.

Pass `provision.py` a trusted private JSON file with `windows_cli` (WSL path),
`windows_datadir` (Windows path), and `core_binary` (WSL path). It writes private
configuration under `/var/tmp/spiral-testnet4-runtime`, starts four loopback
peers with automatic peer discovery disabled, and connects only the diamond.
It refuses stopped or mismatched existing containers instead of discarding
wallets. Existing peer state is preserved; the separate preflight checks that
the wallets and channels are still empty before the first funding cycle.

The 44 offline tests cover the preflight, descriptor redaction, bridge method
and CLI-option restrictions, exact decimal transport, and uncertain broadcast
handling, durable action intents, dual-clock deadlines, explicit routes,
bilateral fee conservation, and observer journal integrity. The live setup checkpoint verifies four distinct synchronized empty
peers and both directions of every diamond connection. None of these checks
constitutes a completed funding/activation or payment-clock experiment.

The [operational protocol](operational_protocol.md) now fixes the exact
510,000-sat budget, four private channel openings, balanced 200-invoice workload,
two-second minimum spacing, 48-hour stop and observation/censoring rules before
any experiment spending. `experiment.py` implements explicit phases with
exclusive durable intent records. An uncertain action is inspected through
authoritative state, never blindly retried. Its monetary phases have not yet
been validated live.

The passive `clock_observer.py` collector is installed and answering on all four
peers. It subscribes to notifications without registering hooks. The
[instrumentation checkpoint](observer-preparation-20261021.json) records its
hash, health replies, unchanged CLN executable hashes and the separately added
Debian Python 3.11.2 runtime/standard-library package versions. Both deposits
remain in the mempool at height 157212; that observed tip contains only its
coinbase transaction. The 500,000-sat deposit has an unconfirmed parent. No
experiment run manifest or 48-hour deadline has been started yet.

`capture.py` reads an existing run without restarting or repeating any action.
`analyze.py` independently reconstructs the funding transaction graph, verifies
each wallet/channel output's ownership evidence, checks both ends of each
terminal payment, and bounds sampled sender reservations. It rejects extra
financing, duplicate representations, altered routes, lost value, invalid
preimages, clock-epoch changes and submission times beyond the hard stop. The
initial preflight outpoints and exact pre-send routes are saved durably for
this reconstruction and for observing a resumed attempt without changing it.

The offline report separates attempted offered value, delivered value and
unattempted planned demand. Zero denominators are null. Unresolved reservation
upper bounds stay null; missed active samples never become zero-duration claims.
`terminal_workload_reconciled` describes the arithmetic checkpoint only:
notification coverage and activation-threshold timing still require inspection
of the captured event traces. These offline checks have not yet validated a
funded testnet4 run.
The full 200-payment report path is exercised only with an explicitly synthetic
fixture; it is a verifier test, not an observed operational result.

## Private configuration and invocation

Run inside the host/WSL environment where the CLI executables, configuration
files and daemon binary paths are readable. Copy `config.example.json` outside
the repository and replace every placeholder. Authentication belongs in private
Core configuration/cookie files, not committed JSON or command-line passwords.
CLI prefixes are trusted local execution configuration, invoked as argv with
`shell=False`. For containers a prefix can include a trusted `docker exec`
wrapper. Never accept these prefixes from an untrusted observation artifact.

Each endpoint declares the exact source revision, executable SHA-256, a readable
binary path and expected RPC version. The script hashes the file and compares
the running RPC version. The operator must separately attest that this file is
the executable serving that endpoint and that the declared source produced it;
matching a local file and version alone does not prove that association.

Use the dedicated Core wallet containing the entire initial test budget. CLN
wallets must initially be empty and have no channels. This captures the funding
cycle from its start, avoiding unobserved earlier transfers. Re-running against
an already funded/active experiment is intentionally rejected: reconcile the
existing run instead of attempting another funding cycle.

```sh
python3 audit/peer_review/testnet4/preflight.py /private/testnet4-config.json /private/testnet4-preflight-001.json
python3 -m unittest discover -s audit/peer_review/testnet4 -p 'test_*.py' -v
```

The output path must not exist. Failure writes `not_ready` and exits 2; success
writes `eligible_for_funding_cycle` and exits 0. The transcript records RPC read
intervals with monotonic nanoseconds as decimal strings. RPC failures suppress
argv/stdout/stderr to avoid leaking credentials. Successful responses are public
node/wallet observations; wallet descriptors and parent extended public keys
are excluded from the public UTXO transcript. Review outputs before publishing. No private key, seed,
preimage, signing or mutating RPC appears in the allowlists.

## Checked gates

- Core reports `testnet4`, the actual genesis matches
  `00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043`,
  IBD is false, blocks equal headers and network peers are present.
- The named dedicated wallet can sign, is not scanning, has no locked,
  pending, immature, unsafe or watch-only funds, and its unique confirmed
  UTXOs exactly reconcile to its trusted balance using decimal arithmetic.
- The wallet has at least 400,000 sats plus the declared positive fee reserve,
  and no more than the protocol's 1,000,000-test-sat cap. The reserve is a
  declared budget, not a prediction that current fee quotes fit it.
- All four distinct CLN IDs report testnet4, the same height and expected
  versions without sync warnings. Their wallets/channels are empty and their
  connections exactly match `a-b`, `a-c`, `b-d`, `c-d` in both directions.
- Core's tip is unchanged across sequential reads. A race fails the observation;
  it is not hidden by an automatic retry or labeled cross-service atomicity.

Genesis comes from [Core v31.0 chain parameters](https://github.com/bitcoin/bitcoin/blob/v31.0/src/kernel/chainparams.cpp#L344).
CLN network/height/sync warnings and wallet/channel fields follow the official
[getinfo](https://docs.corelightning.org/reference/getinfo) and
[listfunds](https://docs.corelightning.org/reference/listfunds) interfaces.
The executed regtest pins remain historical evidence, not testnet execution pins.

## Work still required after eligibility

Record the live source/binary/configuration manifest and initial-state hashes,
then capture one funding/activation cycle for four 100,000-sat channels and
200 low-rate 1,000/2,000-sat payments over controlled routes. Keep all setup and
payment fees within the declared total budget. Enforce the 48-hour hard stop,
retain uncertain actions without resending, and right-censor unfinished waits.
Record submission, mempool, inclusion, activation, route attempts, errors,
in-flight principal, reservation duration, settlement fees and both endpoints'
final balances. Reconcile each settled batch and publish all observations.

Neither the preflight tests nor the existing historical header replay fulfill
those operational-clock measurements. No BIP 448 or LayerTree consensus
enforcement is attempted on public testnet4.

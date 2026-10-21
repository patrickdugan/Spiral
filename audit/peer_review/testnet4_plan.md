# Implementation checks before extending the paper's experiments

Status: proposed protocol, written 2026-10-21 after reviewing commit
`6a9df365f727cf2471ae52e00b36e8816d0081bc`. It has not been preregistered or
executed. Existing evidence was rechecked with `check_empirical.py`.

## Priority and release boundary

Correct the archived effect labels and unsupported bounds before circulating
the paper. A carefully scoped model paper can then be released for public
comment with implementation checks listed as unfinished. The most informative
implementation experiment is tracing Ark server capital through a complete
payment and expiry cycle. Testnet4 becomes useful for the confirmation and
operational clocks once a local accounting trace is understood.

No GPU is needed. Proposed engineering budgets below are planning estimates,
not measured performance figures. This workspace has no Bitcoin Core,
Lightning, or Docker executable, and no accessible testnet4 node was supplied.
No daemon was started and no transaction was constructed or broadcast during
this review.

## Source and execution pin matrix

Support was checked on 2026-10-21. Git blob hashes below bind the exact source
text inspected. They do not identify an installed binary. Fill the execution
pin with a release tag, full commit, binary or container digest, and effective
configuration before the corresponding experiment starts.

| Component | Support evidence and source pin | Network selector | Execution pin |
|---|---|---|---|
| Bitcoin Core | [v28.0 `src/chainparamsbase.cpp`](https://github.com/bitcoin/bitcoin/blob/v28.0/src/chainparamsbase.cpp), blob `aadd04e509f22f6c4fbc3cbebf32f32ef601f39b`; testnet4 added in 28.0 | `-testnet4` / `-chain=testnet4`; `-regtest` for the local stack. The inspected source uses testnet4 RPC port 48332. | Unset; no Core executable available in this workspace. The introduction version is support evidence, not a recommendation to deploy an old release. |
| LND | [0.19.0 release notes](https://github.com/lightningnetwork/lnd/blob/master/docs/release-notes/release-notes-0.19.0.md) record testnet4 support; inspected [sample configuration](https://github.com/lightningnetwork/lnd/blob/master/sample-lnd.conf), blob `56c08003f29a1847dba2c23362251a00d5d2740f` | `--bitcoin.testnet4`; select `--bitcoin.node=bitcoind`. `--bitcoin.regtest` selects the local chain. | Unset; no `lnd` executable available. |
| Core Lightning | Inspected [`doc/lightningd-config.5.md`](https://github.com/ElementsProject/lightning/blob/master/doc/lightningd-config.5.md), blob `b05e732254836ab7c8a74717ee5c83000a122a46`; current documentation lists testnet4 | `--network=testnet4` or `--testnet4`; `--network=regtest` for local tests | Unset; no `lightningd` executable available. |
| Bark/captaind | [Official Docker Compose guide](https://second.tech/docs/ark-server/docker-compose) and [manual guide](https://second.tech/docs/ark-server/manual-setup), retrieved 2026-10-21; repository is `https://gitlab.com/ark-bitcoin/bark` | Official Compose uses regtest; manual guide uses `network = "signet"`. A testnet4 server configuration has not been verified here. | Unset; capture a full Bark commit and image digests before running. No Docker executable available. |

The experiment manifest must also record the actual chain genesis hash and
best block hash. A version string alone cannot establish that every component
is connected to the intended network. The server's configured expiry,
confirmation thresholds, and round cadence belong beside the software pins.

## 1. Trace current Ark recovery on an owned regtest stack

**Question.** When a deployed Ark implementation pays a Lightning invoice from
its own channels, when can the corresponding capital become spendable again?
Second's current documentation says successful outgoing HTLCs remain off chain
and the round is swept at expiry. Treat next-round recovery as a hypothetical
variant until an implementation demonstrates it.

**Environment.** Pin a Bark/captaind commit and its dependency/container
digests. Second supplies a [regtest Docker Compose stack](https://second.tech/docs/ark-server/docker-compose)
with PostgreSQL, Bitcoin Core, and optional Core Lightning. Use one server,
two Bark clients, and a controlled Lightning counterparty. Save a fresh local
chain snapshot for paired reruns. Run standard expiry parameters for the
accounting result; an accelerated expiry is separately labeled a harness
smoke test.

**Trace.** Start with known on-chain outpoints and channel balances. Record
the full provenance of every unit counted in server capital, including
spendable wallet funds, client-backed value, Lightning directional capacity,
and fronted value awaiting recovery. Capture balances and the owning outpoint
at each event. Conduct successful outbound Lightning payment, cooperative
failure/revocation, successful inbound receipt followed by refresh, and a
complete normal expiry sweep. During the outbound trace attempt to reuse the
claimed capital in the next ordinary round without adding fresh funds.

**Measurements.** For each settled amount `q`, record payment settlement,
next round participation, original expiry height, sweep inclusion, and actual
eligibility for a subsequent spend. Record local monotonic time as well as
block height. Integrate fronted-and-unrecovered value over that interval to
obtain the empirical `q * L`; integrate every other charged stock separately.
The same asset must have one capital classification at each time. Invoice
success alone is insufficient evidence of server recovery.

**Decision.** A successful early reuse must identify the on-chain asset or
enforceable credit that funded it and its associated obligation. A server
bookkeeping entry or reuse financed by another asset cannot establish recovery
of the first asset. If normal reuse waits for expiry, the expiry branch is the
deployment interpretation; the round branch remains an alternative design.
Publish the observed state transitions and any discrepancy with the model.

**Budget.** Start with a 4-vCPU / 8-GB development host and two hours of local
runtime after images are available. Run one trace per path and five clean
restarts of the successful outbound case as a determinism check. These five
traces check implementation behavior; they do not estimate a network-wide
economic distribution. Expected human effort: one or two implementation days
once the version is pinned.

## 2. Match service levels in the local comparison

**Question.** How much capital does each object require to deliver the same
workload at an agreed failure rate? A capital-duration ratio with different
denominators can improve when a system rejects traffic, so raw ratios should
be accompanied by delivered volume and failure rate.

**Design.** Freeze canonical demand sequences and initial-state hashes. Use a
disjoint pilot to choose provisioned budgets for each object, then evaluate
the frozen budgets on new seeds. Declare a minimum delivery target, such as
99% of offered value, before seeing those seeds. Record both event success and
value delivery. Include balanced independent demand and shared drift; a second
factor assigns pre-existing balances or zero initial balances. Compare
receive-heavy credit-leaf scenarios separately from two-way net-balance
scenarios.

**Measurement.** Report locked capital-time over both offered and delivered
value, failure causes, peak deficit, forecast rule, rebalancing costs, and
end-of-horizon obligations. The implementation accounting from experiment 1
determines the recovery clock. State the model's horizon and terminal rule so
that shifting an obligation beyond the last round does not erase its cost.

**Decision.** If an object requires more capital to meet the same delivery
target, report that even when an unadjusted duration ratio looked favorable.
Use paired-seed intervals and publish all cells. A conservation invariant
remains an accounting check; measured delivery gains stay specific to the
tested workload and policy class.

**Budget.** Reserve a two-hour CPU cap for the first exploratory grid, with a
pilot runtime before choosing the number of holdout seeds. This work can run
inside the existing reference model. A new confirmatory campaign requires a
committed pre-run protocol and fresh seeds after exploratory choices are made.

## 3. Use testnet4 for a bounded Lightning and confirmation check

**Question.** Which operational costs omitted by the instantaneous simulator
matter when channels and HTLCs run on an implementation?

**Support.** Bitcoin Core added testnet4 in
[28.0](https://bitcoincore.org/en/releases/28.0/).
[LND 0.19.0](https://github.com/lightningnetwork/lnd/blob/master/docs/release-notes/release-notes-0.19.0.md)
added it, and [Core Lightning](https://docs.corelightning.org/reference/lightningd-config)
also exposes it. Pin exact stable versions and use an already synchronized
testnet4 Bitcoin Core node with four controlled Lightning peers in a diamond.
Configure the peers directly so the experiment does not depend on public
testnet routing or discovery.

**Preflight reads.** Record `bitcoin-cli -testnet4 getblockchaininfo`,
`getnetworkinfo`, and `getmempoolinfo`, plus each Lightning node's version,
chain/network identifier, current height, and channel parameters. Record the
actual active chain and synchronization state. Use dedicated test wallets and
redact authentication material from artifacts.

**Workload.** Use four 100,000-test-sat channels and retain an explicit fee
reserve within a proposed cap of 1,000,000 test sats. Send 1,000- and 2,000-sat
invoices over controlled routes at a low rate. Measure one funding/activation
cycle and 200 payments, with a hard stop at 48 hours. A run that reaches the
time cap reports right-censored confirmation waits instead of manufacturing
completion. Build matched-state policy comparisons on regtest; public testnet
channel state cannot be rewound for identical counterfactual episodes.

**Measurements.** Capture transaction submission and mempool-observation times,
block inclusion and required-depth activation, every route attempt, failure
code, HTLC reservation duration, in-flight amount, settled fee, and final
balances on both ends. Track wall-clock time with a monotonic clock and record
the node-observed block arrival time. Miner header timestamps are a distinct
field. Verify channel balance and fee accounting after each settled batch.

**Decision.** Require all completed payments to reconcile with channel state
and fees, and require the observed activation gate to match the configured
confirmation threshold. Any counterexample becomes an implementation/model
finding. Quantify how elapsed time and concurrent reservations change the
comparison; do not extrapolate a four-node test to mainnet placement effects.
Testnet fees and free test coins cannot identify a market cost of capital.

**Budget.** The same CPU host can run the peers if it has room for the existing
synced node. Reserve 48 hours of wall time; CPU use is expected to be modest.
Measure actual memory and disk use before extending the run. Testnet coin
availability and confirmation delays are external limits, so record them.

## 4. Keep proposal-only mechanisms in explicit test environments

BIP 448 and LayerTree depend on proposed consensus rules. Public testnet4 does
not establish those rules merely because a transaction template can be
constructed. Use a separately identified patched regtest or custom signet
deployment when testing inactive opcodes. Record unmodified-node behavior as
a control, distinguishing mempool policy from consensus and any
upgradeable-opcode behavior. An unmodified node's acceptance
does not show that it enforced the proposed rule. Identify every activated
patch in the report.

Ordinary script serialization, transaction-weight accounting, parent/child
mempool policy, and contention can be tested locally now. Adversarial queueing
or fee-pinning experiments belong on controlled regtest. A test of an ordinary
shared output can calibrate generic policy costs; it cannot validate a
LayerTree covenant or its unilateral-exit guarantees.

## Artifacts required for any executed lane

Save the preregistered protocol commit where applicable, software commits and
binary/container hashes, configuration with secrets removed, initial-state
hashes, offered-demand log, event log, accounting table, and analysis script.
Every claim should identify its evidence as a reference-model result, archived
data reanalysis, regtest implementation trace, or testnet4 observation.

The retained `audit/testnet4/results/headers.csv` remains useful for historical
header validation. Its 512 headers and 511 links supply no observed funding
or payment latency. Replaying their heights against another synthetic gate
would still be a model calculation.

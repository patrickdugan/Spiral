# Bounded testnet4 execution preparation

`preflight.py` is a read-only preparation gate for section 3 of the
[existing protocol](../testnet4_plan.md). It has offline adversarial tests;
it has **not** passed against a live testnet4 deployment. No funding,
activation or payment-clock observation is produced by a successful preflight.

The required synchronized Core endpoint and dedicated test funds remain
unavailable in this chat. Four dedicated CLN peers must be provisioned against
that endpoint and connected in a diamond before opening channels. This script
checks that starting condition; it does not start services, connect peers,
create wallets, open channels or send payments.

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
python3 -m unittest discover -s audit/peer_review/testnet4 -p test_preflight.py -v
```

The output path must not exist. Failure writes `not_ready` and exits 2; success
writes `eligible_for_funding_cycle` and exits 0. The transcript records RPC read
intervals with monotonic nanoseconds as decimal strings. RPC failures suppress
argv/stdout/stderr to avoid leaking credentials. Successful responses are public
node/wallet observations; review them before publishing. No private key, seed,
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

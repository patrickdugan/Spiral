# Fee-aware fixed-budget comparison protocol

This protocol is committed with the pilot budgets before evaluating seeds
301–324. It defines a forecast, not another live Bark experiment. The earlier
fee-free structural sensitivity used seeds 101–124 and is a different result.

## Frozen design

Use all four original demand families: balanced bursts (`zero`), shared
negative drift (`drain`), shared positive drift (`accumulate`), and three
holders making small steady payments (`steady`). The generator preserves
the existing model's RNG draws, amounts and within-round ordering. Bursty
cells have 200 holders. Horizon is eight 4,320-block lifetimes, with six-block
rounds. Initial gross principal is either zero or 250,000 sats per holder,
identically assigned across mechanisms before their own fees. These are
declared balance factors; they are not fitted to held-out service results.

Pilot seeds 201–208 choose each cell's budgets. The Ark wallet, fronting ceiling,
and both channel directions are each 125% of the maximum pilot requirement,
rounded upward to integer sats. Pilot runs have ample funds to expose those
requirements. The fronting ceiling is a constraint on the funded assets, not
an additional asset added to capital. Channel groups have sizes 1, 5, 20 and
200 (1 and 3 for the steady cell). Their initial local balance is the holders'
gross principal plus the declared outbound buffer; the remote budget is 125%
of its largest pilot requirement. Each pilot artifact includes implementation
SHA-256 hashes; held-out evaluation refuses changed code or protocol.

Run all 24 holdout seeds without resizing, dropping seeds, changing workload,
or selectively extending the horizon. Minimum delivered value is 99% of gross
offered invoice value. Publish event success, both directional value totals,
failure causes, and both offered and delivered normalizations. A funded-capital
ratio is eligible for matched-service interpretation only on paired seeds
where both compared mechanisms meet that target. Report all other rows as
service failures, even if a raw capital ratio appears favorable.

## Accounting and transaction policy

`model/capital-fees.ts` reproduces the pinned integer pricing arithmetic,
including once-per-calculation rounding across expiry buckets. `fee-source.json`
binds it to source blobs and the archived effective configuration. Tests
reproduce the observed 555-sat send fee and 463/305-sat refresh fees.

The forecast retains outgoing change on its original root. It consumes
soonest-expiring inputs first; principal recovery is assigned FIFO to the
earlier commitments on each root. Payment principal and fresh refresh-root
funding contribute to F; confirmed recovery contributes to C. Receipt issuance
has matching received Lightning value and is tracked as funded issuance,
not a second outgoing front. Wallet availability and physical root stock
still charge that issuance. W=F-C persists after a fee-caused recovery
shortfall; that shortfall is not charged again as an economic loss.

Every accepted receipt uses a separate fresh round, with a root equal to the
net claim plus the observed 330-sat overhead and a 3,857-sat miner fee. Each
claim refreshes separately 288 blocks before expiry or after 99 retained-change
hops, resetting the forecast hop counter. This scheduling policy respects the
configured depth ceiling of 100 but is not a reconstruction of every genesis
transaction or the live wallet's selection policy. Failed maintenance retries
every six blocks before expiry. Expired claims remain obligations and cannot
be spent or silently swept. Fresh round outputs require 330 sats; Arkoor
retained change may be subdust.

Each inactive root is eligible for a separate 1,295-sat sweep after expiry plus
six or 144 blocks. Six is the observed snapshot detection gap, not a latency
distribution. 144 is a declared stress case. A sweep with a net output below
330 sats is uneconomic under this policy and remains unresolved. No batching
rescue, channel rebalancing, channel rotation, or additional funding is assumed.

These single-participant receipt, refresh and sweep costs deliberately make
batching explicit. The live trace verified the outgoing/refresh/recovery
transaction shape; it did not verify this per-receipt issuance policy or
estimate amortized multi-participant fees. Conclusions must stay conditional
on this policy. Successful Lightning settlement is instantaneous with zero
routing fee, matching the controlled one-hop fee observation but not measured
operational HTLC duration. Admissibility includes the configured 90% routing
fee allowance. Unused allowance is never charged for a positive simulated
interval. Seconds remain unavailable.

## Boundaries and terminal rule

Economic conservation uses operator wallet, roots and local Lightning share,
with external receipts/boards, outgoing payments and miner fees. Holder
service fees transfer value inside that boundary. Client board miner fees
are separate. The physical resource comparison includes whole channel funding
(both parties) plus onchain roots plus idle wallet reserve, counting each
underlying lot once. Holder claims and W are overlays, never added to that sum.

Report actual committed, idle, fronting, directional, and assumed in-flight
sat-blocks separately. The fixed initial funding budget times the horizon is
also published: reducing assets by paying miner fees does not create a capital
efficiency gain. Miner fees and service fees are published separately. Channels
pay the observed 166-sat opening fee per channel as a cost, outside ongoing
funding stock. No funding-rate or market-price claim is made.

At the horizon, retain every root, claim, fronting part, expired obligation,
and exhausted shortfall. Publish the future eligible recovery schedule as a
forecast, and right-censor unresolved recoveries. The event calendar integrates
each stock exactly to its own event height; a coarse/fine regression verifies
identical results across refreshes and recoveries.

## Reproduction and resource cap

From the repository root:

```sh
python audit/peer_review/pin_capital_fees.py
node --experimental-strip-types audit/peer_review/capital_fixed_budget.ts pilot all
# Commit protocol, source, verified tests and generated pilot budgets here.
node --experimental-strip-types audit/peer_review/capital_fixed_budget.ts holdout all
```

Each phase has a one-hour wall-time guard, keeping pilot plus holdout within
the proposed two-hour campaign cap. The initial exploratory implementation
checks precede the freeze and are not confirmatory observations. This is a
conditional model campaign, not a claim that unobserved live receive, failed
HTLC, exit, reorg or testnet4 clock experiments have been completed.

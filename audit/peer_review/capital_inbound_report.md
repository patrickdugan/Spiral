# Observed inventory-backed Lightning receipt

The owned regtest fixture received **2,000 sats**, credited the holder a
**1,896-sat VTXO**, and retained a **104-sat service fee**. The server's channel
share increased by all 2,000 sats. The holder's VTXO is backed by an already
funded 20,000-sat on-chain pool root, not by an additional copy of the received
Lightning value. No external fixture funding was added.

The complete fixture still balances:

```
2,200,000 initial sats
  = 2,028,761 operator economic assets
  +    99,845 client on-chain assets
  +    58,000 peer channel share
  +    13,394 cumulative miner fees
```

The peer previously received 60,000 sats and returned 2,000 in this experiment.
In the operator-only reducer boundary that return is an external inflow. In the
complete fixture it is an internal transfer. The service fee is revenue within
operator assets, not an additional asset or an external miner/routing fee.

## Execution and pins

The existing Bark/captaind revision remains
`8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a`; existing container and executable
pins are retained. CLN's executable is unchanged. Its missing hold-invoice
plugin was installed dynamically from the upstream version used by that
revision's Dockerfile:

- [BoltzExchange/hold v0.3.3](https://github.com/BoltzExchange/hold/releases/tag/v0.3.3),
  source commit `af0055b132f3b9f24d0b1d478a15005fcf8f014f`.
- Release archive SHA-256:
  `f9d916430fb70a3d75089f2d1b88d5d71d4987ef79933035978c1f44aab84be5`.
- Executed binary SHA-256:
  `f98cd795e68a214b11fe168cc08690a50837dcefc93be6b885cb69d74ef1c1a4`.
- Plugin gRPC binds `127.0.0.1:9292`; captaind connects through mutual TLS.
  Keys remain outside the repository. Only configuration additions and hashes
  are published in `regtest/evidence/inbound-plugin-runtime.json`.

`enable-inbound.py` configures this existing owned fixture. A separately
recorded configuration temporarily requests two 10,000-sat pool leaves;
upstream ignores issuance requests with only one leaf. `prepare-inbound-pool.py`
disables further issuance before mining three confirming blocks. Pool expiry is
4871; the captured tip is 4442. Historical success and failure evidence remains
immutable.

## Exact funding and claim provenance

Pool funding transaction:
`1579dc43b9c47805b95472f9a4c2ec802e562c0bea654af71a1d08b4ee92c153`.
It spends only output 1 of the previously proven reuse transaction:
`09f458267cc9f50da7af5ad1a32f39b4d83db5eb5dd44aa8ac9bc53b981da272`.

| Item | Sats |
|---|---:|
| Existing wallet input | 56,171 |
| Pool root, output 1 | 20,000 |
| Wallet change, output 0 | 35,554 |
| Miner fee | 617 |

The two-leaf pool root has no 330-sat surplus in this observed transaction.
The earlier single-participant refresh round had a different output structure;
its measured cost must not be treated as universal across inventory issuance.

Payment hash:
`885f15136dbaa25cdd03b61b8c17298a547a00613e11ad15e0ea2d0591efd1f0`.
Both channel sides capture the accepted 2,000,000-msat HTLC. Terminal evidence
includes the peer's single completed send attempt and verified preimage hash,
the hold plugin's `paid` invoice, the server's `settled` subscription with
`final_amount_msat=2000000`, and its settlement record.

Client claim:
`947259f025958e043b451208c4130bf00884cf132d51397538a2ff83fe252edc:0`.
Eight newly captured signed transactions trace its ancestry to the pool root.
The holder's total spendable claims rise from 38,347 to 40,243 sats. The server's
channel ownership rises from 440,000 to 442,000 sats; its measured spendable
capacity rises from 430,694 to 432,694 sats.

## Pool change is not necessarily reusable inventory

The selected 10,000-sat pool VTXO yields a 1,896-sat client claim and an
8,104-sat server change VTXO. The other 10,000-sat leaf remains selectable.
The change exists with `vtxo.spend_state=pool`, but is absent from `vtxo_pool`.
The allowlisted server diagnostic explains why: **exit depth 4 exceeds the
configured pool maximum of 3**. Pinned `server/src/vtxopool.rs` explicitly drops
such change from selection and retains it for expiry recovery.

Thus the root's 20,000 sats comprise 1,896 holder-backed sats, 10,000 selectable
inventory sats and 8,104 depth-excluded sats. All remain the same underlying
root economically. Neither a `pool` label nor absence of an external holder
claim establishes spendable on-chain value. Recovery of the depth-excluded
change is right-censored at this horizon, with expiry still in the future.

## Reducer and verification

`RECEIVE_LIGHTNING` now has an explicit `backing_mode: "inventory"`. It requires
settlement evidence and existing committed on-chain pool backing whose expiry
covers the new claim. `fee` remains an external receipt cost; `service_fee`
records the retained holder charge. With `pool: true`, received channel assets
are a new pool contribution. They do not increment recovered fronting `C`.
Legacy direct-liquidity receipt events retain their prior semantics.

The 49-event `regtest/evidence/inbound-lifecycle.jsonl` extends the 46-event
failure journal by a chain observation, the confirmed pool transaction and the
settled receipt. The normalizer checks all remaining on-chain economic outputs
are unspent at their recorded amounts, both channel shares, holder claims,
virtual ancestry, fee arithmetic, invariants and deterministic replay.
`F=140,308`, `C=101,354`, and `W=38,954` sats remain unchanged. State hash:
`459c3166421f6c0deb47009b250e428515415054767dd8a3f86c33f60046e1f8`.

Tests reject missing settlement proof, invented liquidity-backed inventory,
excess allocations, fees consuming the receipt, and expiry extension without
changing state. The shared pool root remains committed in full.

## Limits and preserved collection gap

The original peer-payment command terminated, but its stdout failed JSON
parsing after the Bark claim returned zero. Raw stdout and the original exit
code were not retained. Notification output may have caused the parsing error;
that cause is not established. No payment was resent. Read-only terminal
reconciliation verified the one completed attempt. Future collection requests
`--json --notifications=none`. The original intent and explicit collection-gap
record remain in the evidence directory.

The collector deliberately waited to capture acceptance before claiming, so
this elapsed interval is not a natural latency sample. The intermediate
claim-preparation interval was not sampled; the reducer reconstructs the
terminal economic transition. Whole-journal sat-seconds remain unknown.

This is one two-leaf inventory configuration, not a batching distribution.
The frozen fixed-budget campaign remains a conditional single-participant
forecast. This observation establishes that its fresh-round-per-receipt policy
does not describe this inventory path, and its ranking must not be generalized
to it. A separate inventory-policy forecast would require explicit replenishment,
depth and residual-recovery assumptions; this experiment does not silently
change the already frozen holdout protocol. Live timeout/unilateral recovery,
exit/reorg branches and bounded testnet4 clocks remain outstanding.

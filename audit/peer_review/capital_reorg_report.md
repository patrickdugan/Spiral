# Observed cooperative-exit reorganization

The owned regtest fixture orphaned the three blocks confirming its cooperative
exit, observed the same signed transaction in the mempool, and reconfirmed it
on a competing branch. The client payout lost confirmation; the offboard and
forfeit records did not reverse. Restoring the old holder claim would therefore
create a false liability and an incorrect spendability result.

## Intervention and evidence

Execution uses the same source revision
`8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a`, executable/container digests and
regtest genesis as the [exit report](capital_exit_report.md). The source's
`server/src/sync/block_index.rs:126` panics when Core's tip is below its synced
height. To exercise a competing-chain reorg without that lower-height guard,
`regtest/reorg-exit.py` paused captaind, watchmand and both CLN nodes while it
invalidated block 4443 and built four empty replacement blocks. It resumed
them at height 4446, above their previous tip of 4445. Both server database
tips then matched Core. This controlled pause is part of the experiment;
it provides no uninterrupted network-propagation timing measurement.

The script records intent before intervention and refuses a repeated intent.
All pause/unpause, invalidation, mining and client-cache synchronization records
are preserved. It sends no new payment and adds no fixture funding. The
read-only collector snapshots the same public transaction and database fields
before, during and after the reorg. No running service is needed to reproduce
the accounting:

```sh
node --experimental-strip-types audit/peer_review/regtest/normalize-reorg.ts
```

The normalizer verifies ancestry, orphaned header status, unchanged signed
transaction bytes, surviving spent claims/forfeits, channel settlements,
wallet finality and every remaining tracked on-chain output. Its report pins
the input evidence by SHA-256.

## Observed state

| Observation | Original checkpoint | Pending on replacement branch | Reconfirmed |
|---|---:|---:|---:|
| Core height | 4445 | 4446 | 4449 |
| Exit inclusion height | 4443 | none | 4447 |
| Exit confirmations | 3 | 0 | 3 |
| Client confirmed/trusted-spendable sats | 115,577 | 99,845 | 115,577 |
| Client untrusted pending sats | 0 | 15,732 | 0 |
| Server wallet change | 17,519 confirmed | 17,519 unconfirmed | 17,519 confirmed |
| Original holder claim | spent | spent | spent |

The offboard remains `wallet_commit=true`. Its transaction is
`2b693c30887a8de3a4bc601460b5dde3f88fa2895aa0ed2363908a6133e8812b`;
the signed bytes hash to
`ae41f357e6a284a3d176c7c76a214ee2d61223879f1f39b3521fbd53a8c35706`.
There is no second fee, payout or fronting entry. The original shared root and
330-sat connector remain encumbered. Reconfirmation does not recover capital.

The complete fixture still reconciles as:

`2,200,000 = 2,011,056 operator + 115,577 client + 58,000 peer + 15,367 miner fees`.

`F = 158,343`, `C = 101,354`, and `W = 56,989` sats are unchanged.

## Reducer behavior and boundaries

An orphaned funded `EXIT` now freezes the last reconciled economic checkpoint,
as an orphaned irreversible Lightning outcome already does. The pending
53-event journal prefix of 52 events checks as structurally valid but
`reconciled: false`; it cannot authorize normal transitions. Retained `FREE`
labels belong to that historical checkpoint, not current spendability.

A `REORG.reconfirmed_exits` entry can reconcile the terminal funded exit only
when it identifies the original event and same transaction, cites evidence in
the envelope, and proves canonical inclusion with configured finality. A
still-canonical checkpoint cannot be arbitrarily moved. Later economic events
or surviving intervening observations require a fuller reconstruction and are
rejected by this narrow path.

The original journal stays byte-for-byte unchanged. Replay uses a separate
effective confirmation anchor recorded in `J.reconfirmed_exits`; subsequent
reorgs preserve or invalidate that anchor. Replay also copies nested event
payloads before reducing them, so changes to claim allocations cannot mutate
historical issuance records. The final 53-event state hash is
`a47198789818d3c09b3ca8b74ff52c985c480ed454e866be721613889a7f0bd7`.

Branch-local integrals use the new confirmed observation anchor. They do not
measure wall-clock exposure through the pending interval; timestamps remain
null and the paused interval is explicit. This evidence establishes one live
exit reorg, not live sweep rollback, replacement-transaction recovery,
unilateral exit, compound-right partial recovery or testnet4 clocks. The
existing sweep-reorg falsification remains a deterministic reference test.

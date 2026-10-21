# Observed cooperative exit with retained backing

The owned regtest fixture cooperatively offboarded one **18,632-sat** holder
claim. The client received a confirmed **15,732-sat** output in its own Bark
on-chain wallet. Its 2,900-sat charge comprises a 1,973-sat miner fee and
927 sats retained by the operator. The transaction spends existing server
wallet capital; the original claim's backing remains unspent.

This is additional fronting. It does not recover earlier fronting or make the
original backing reusable. A separate 330-sat connector is also encumbered.

## Pinned execution and evidence

The Bark/captaind source revision remains
`8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a`, with unchanged executable/container
pins from the earlier observed lifecycle. The same owned regtest genesis is
verified. `regtest/evidence/offboard-source-and-chain.json` pins the offboard
server, database, library, client action and CLI source files, the three new
canonical headers, and both newly captured signed transactions.

`offboard-observed.py` refuses a prior intent, selects only the recorded claim,
offboards to the existing client's wallet, captures the mempool transaction,
and mines three confirming blocks. No funding is added. `attest-offboard.py`
synchronizes the client's on-chain cache and captures confirmed ownership;
it does not repeat an exit or payment. All action records and snapshots are
retained separately from historical successful, failed and inbound paths.

The offboard's `wallet_commit=true`, the original VTXO's `offboarded_in` field,
the signed forfeit, the connector record, Core's active-chain transaction and
unspent outputs, and Bark's confirmed/trusted wallet balance agree. There was
no uncertain-action retry or collector parsing gap in this exit experiment.

## Exact transaction accounting

Original claim:
`e59ba9240fb4294d026d9d2d31b965fabcd23632d4a058cf77882ed56044324e:0`.

Its backing remains:
`09f458267cc9f50da7af5ad1a32f39b4d83db5eb5dd44aa8ac9bc53b981da272:0`.
Other holder claims still share this 38,677-sat root.

Offboard transaction:
`2b693c30887a8de3a4bc601460b5dde3f88fa2895aa0ed2363908a6133e8812b`.
Its sole input is the existing 35,554-sat wallet change from the inbound pool
funding transaction, output 0 of
`1579dc43b9c47805b95472f9a4c2ec802e562c0bea654af71a1d08b4ee92c153`.

| Disposition | Sats |
|---|---:|
| Client payout, output 0 | 15,732 |
| Server connector, output 1 | 330 |
| Server wallet change, output 2 | 17,519 |
| Miner fee | 1,973 |
| Total input | 35,554 |

The client payout confirms at height 4443 and is observed with three
confirmations at height 4445. After explicit on-chain synchronization, Bark
reports both the original 99,845-sat client output and the new 15,732-sat exit
output as confirmed, with total trusted spendable balance **115,577 sats**.
The remaining off-chain holder balance is **21,611 sats**. The Lightning channel
shares and all prior Lightning settlement records are unchanged.

The complete fixture balances:

```
2,200,000 initial sats
  = 2,011,056 operator economic assets
  +   115,577 client on-chain assets
  +    58,000 peer channel share
  +    15,367 cumulative miner fees
```

## Forfeit and connector encumbrances

The signed forfeit transaction spends precisely the old 18,632-sat claim and
the new 330-sat connector. Its 18,962-sat server recovery claim is:
`4f58df9ad33cde2e9c47a8d94bb10185129c25773d8da5a867b4ea63f13ac46d:0`.
This claim is a contingent right over existing assets, not another economic
18,962 sats. Its allocation includes the old backing slice and the connector
exactly once. The consumed holder claim retains historical provenance with
zero residual allocation, while the new server forfeit retains that allocation.

The original claim/forfeit expiry is **8756**. The connector's recorded expiry
is **8900**, reflecting an additional 144-block interval. Both the shared old
root and the connector remain committed at the observation horizon. Neither
`wallet_commit=true` nor payment of the client proves their recovery. Their
later recovery is right-censored. Partial recovery of the compound right at
different maturities requires a separate observed transition; the model does
not infer it from these records.

## Reducer change and tests

`EXIT.funding` explicitly describes a cooperative payout from fresh pool
capital. Its confirmed transaction accounts for every input/output and miner
fee. It identifies connector outputs, the payout output, and the exact
replacement forfeit claim. The legacy direct-backing exit remains available
for its separately constrained exclusive-backing case.

The newly committed fronting is **18,035 sats**: 15,732 paid out, 1,973 spent on
the miner fee, and 330 committed to the connector. The freely returned wallet
change is excluded. The holder's entire 2,900-sat fee is recorded separately;
only its miner component is an economic outflow. No recovery credit is added:

```
F = 158,343 sats
C = 101,354 sats
W =  56,989 sats
```

The 51-event `regtest/evidence/offboard-lifecycle.jsonl` extends the inbound
journal with a chain observation and confirmed exit. Its state hash is
`8dfce8a397e35d9330c05146c062abc1cd70ba445dace868cb3659e04f1b49aa`.
The normalizer verifies all remaining on-chain economic assets remain unspent,
client ownership and confirmations, unchanged channel ownership, exact forfeit
inputs, unchanged original backing, all holder claims, invariants and replay.

Regression tests reject payout substitution, connector maturity shortening,
forfeit allocation/parent corruption, missing forfeit evidence, unsupported
fee subsidy, invalid finality and mislabeling this path as unilateral. Each
rejection leaves the machine unchanged.

## Limits

The economic reducer applies the exit at its confirmed observation height.
The preparation and mempool snapshots preserve earlier evidence but are not
treated as exact reducer clocks. In particular, the three-block interval from
broadcast detection at 4442 to final observation at 4445 is not added as if its
inclusion/finality occurred at a measured instant. This reconstruction is not
an exact live capital-time trace; historical sat-seconds remain unknown.

This experiment validates cooperative exit, not unilateral exit, post-exit
recovery, live reorg handling or testnet4 timing. The previous frozen comparison
contains no exit workload and is not rerun or relabeled on the strength of this
observation. The report supplies additional implementation evidence and keeps
all unclosed obligations visible.

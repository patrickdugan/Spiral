# Pinned Bark/Core/CLN observation mapping

This is a source-inspected, read-only **offline snapshot adapter**, not a daemon
collector and not evidence that the upstream software was executed. The exact
inspected files, Git blobs where available, normalized-source hashes and URLs
are in [source-pins.json](capital/source-pins.json).

| Component | Source revision inspected | Execution identity |
|---|---|---|
| Bark/captaind | `683964f59fcb3dde1dcecd6eab23b2a9dd2eee6f` | None |
| Bitcoin Core v30.0 | `d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3` | None |
| Core Lightning v26.06.7 | `8684c68dffb04ab606e526b64d7d60390d1fe7ed` | None |

The adapter rejects different pins rather than treating moving `master`/`latest`
interfaces as equivalent. Pin validation checks the declared snapshot revision;
the collection process must independently bind those declarations to binaries.

## Actual upstream fields and event names

| Evidence | Pinned source and fields | Interpretation |
|---|---|---|
| Bark outgoing attempt | `server/src/database/ln/model.rs`, `LightningPaymentAttempt`: `id`, `payment_hash`, `amount_msat`, `final_amount_msat`, `status`, `user_fee`, `lightning_htlc_subscription_id`. DB fee column is `user_fee_sat`. | `amount_msat` is invoice value; `final_amount_msat` is CLN amount sent, excluding Ark's holder fee. A nonnull subscription ID identifies intra-Ark self-payment and is rejected by this outbound adapter. |
| Bark authoritative settlement | `server/schema.sql`, `public.htlc_settlement`: `id`, `payment_hash`, `preimage`, `created_at`. | Check SHA-256(preimage) against hash in memory. Retain only a verified-proof reference in published events. `LightningPaymentStatus::Succeeded` explicitly warns that status is not authoritative for releasing funds. |
| Bark initiation/revocation logs | `server-log/src/msgs/lightning.rs`: `LightningPaymentInitiated {payment_hash,amount,fee,min_expiry}`, `LightningPayHtlcsRevoked {payment_hash,htlc_vtxo_ids,new_vtxo_ids}`, `HtlcSettled {payment_hash}`. | Correlation signals. Revocation-request and failure status alone do not release a reservation. Logs intentionally exclude preimages. A `HtlcSettled` log alone does not supply amount, route fee, backing or recovery. |
| Bark receive logs | `LightningReceivePrepared`, `LightningReceiveClaimed`, `LightningReceiveCanceled`, `LightningReceiveKeptCommitted`. | `KeptCommitted` explicitly describes expired invoice/possibly live receive-HTLC obligations. This is not capital recovery. Receive settlement/backing joins remain instrumentation work. |
| Bark onchain watchman | `server-log/src/msgs/watchman.rs`: `ClaimBroadcast {txid,vtxo_ids,fee_rate,total_input_value,total_output_value,fee}`, `HtlcVtxoResolvedOnChain {vtxo_id,height,resolution}`. | Join with decoded transaction inputs, outputs and active-chain inclusion. Do not equate broadcast, DB `confirmed_at`, or a log line with spendable capital. |
| CLN aggregate payment | Pinned `doc/schemas/listpays.json`: `pays[].payment_hash`, `status`, `amount_msat`, `amount_sent_msat`, `number_of_parts`. | Unfiltered `listpays` aggregates MPP. Index/start filtering can undercount amounts; capture the complete payment result. Ambiguous repeated-hash entries fail closed. |
| CLN directional channel | Pinned `doc/schemas/listpeerchannels.json`: `channel_id`, `funding_txid`, `funding_outnum`, `state`, `to_us_msat`, `total_msat`, `spendable_msat`, `receivable_msat`, `htlcs[].{direction,id,amount_msat,state}`. | Funding outpoint is provenance, not another counted asset. Owned share and usable capacity are different quantities. A nonempty HTLC set requires prior commitment history. |
| Core chain | Pinned `src/rpc/blockchain.cpp`: `getblockhash 0`, `getblockchaininfo`, `getblockheader`: `hash`, `height`, `previousblockhash`, `confirmations`. | Actual genesis must match the run manifest. Hash-linked canonical observations, not a height-only clock. |
| Core transaction | Pinned `src/rpc/rawtransaction.cpp`: verbose `getrawtransaction`, with explicit block hash: `txid`, `vin[].txid/vout`, `vout[].n/value/scriptPubKey`, `blockhash`, `confirmations`, `in_active_chain`. | Resolve input values, output owner/script, fee and inclusion against the same active-chain snapshot. Adapter only admits one owned sweep output at index zero. |

At the pinned Bark source, `server/src/ln/cln/xpay.rs` tracks CLN updates and
periodically reconciles `listpays`. The source does not justify deriving holder
fee, gross forfeiture or a capital recovery time from a single payment status.

## Recovery paths supported by source, not measured clocks

`server/src/watchman/policy.rs` distinguishes policies. `decide_server_owned`
and `decide_action_expiry` wait for absolute expiry. The outgoing
`ServerHtlcSend` path may claim with a preimage after `confirmed_at + exit_delta`,
subject to transaction ancestry/progress and competing deadlines. The receive
path has its own HTLC-expiry/relative-delay conditions. Therefore neither
"all Ark capital returns at expiry" nor "settlement frees it next round" is a
general implementation fact.

The machine's ordinary sweep lane intentionally implements expiry plus observed
inclusion/finality/reuse. It does **not** implement the alternative onchain
ServerHtlcSend claim policy or prove next-round reuse. The watchman's separate
reaction/sweep intervals and progress grace period are configuration clocks,
not a constant inferred from the invoice outcome.

## Collection and instrumentation still needed

1. Run Core, captaind, watchmand, CLN, PostgreSQL and two Bark wallets on an owned
   regtest. Pin binaries or immutable container digests and record their source
   relationship. Upstream Compose currently names captaind/bark `latest`, while
   its CLN Dockerfile also clones unpinned hold/prometheus dependencies. Copying
   that file without resolving those dependencies is not an execution pin.
2. Capture read-only DB snapshots in a consistent transaction and record its
   transaction/snapshot identity. Export payment attempts and authoritative
   settlement presence plus a proof hash; do not dump preimages to a public PR.
3. Add or export a correlation record tying original VTXO IDs, change/replacement
   IDs, exact ancestor outpoints, pool allocation and payment hash. Log records
   do not expose the full economic backing graph. Populate `asset_ids`,
   `claim_ids` and actual causal read sets from that record.
4. Snapshot all relevant CLN channels and Core wallet outpoints before/after each
   transition. Store the collector's monotonic elapsed time, active block hash,
   serialized payload hashes and redacted effective configuration. Avoid mixing
   responses from different chain tips or DB snapshots.
5. Resolve all transaction ancestors, output scripts, ownership and fees.
   Check output availability with Core and the wallet's actual spending rules.
   Identify which recovered output finances the independent second operation.
   The observer must verify the `spends:<outpoint>` evidence, not merely label it.
6. Exercise successful payment, failed/revoked payment, timeout, receive/refresh,
   ordinary sweep, cooperative/unilateral exit and reorg. Preserve unsupported
   cases as unresolved observations rather than filling in forecast events.

The adapter methods are pure functions on captured JSON/DB records. They contain
no RPC transport, subprocess execution, database writes, transaction signing or
broadcast calls. This minimizes observation privileges but does not supply the
missing collection/instrumentation layer automatically.

## Explicit limits

Initial/channel funding in the current lane assumes zero opening fees and
explicit maturity/capacity evidence. Reuse converts one recovered output into a
new channel without an additional modeled opening fee. The synthetic channel
permits its full local share to be spent; an actual CLN channel's reserves must
be respected before admitting the same operation. Batched sweeps, input CPFP,
RBF replacement, mixed-attribution outputs, channel splices, intra-Ark self-pay,
negative service margin and live-holder expiry/write-off need richer event
allocations. Never map these to the supported simple shape by dropping inputs,
fees or liabilities. Deep reorgs crossing irreversible settlement halt accounting.

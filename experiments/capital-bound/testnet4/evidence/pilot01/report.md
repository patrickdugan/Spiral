# Capital Bound Moves campaign

Campaign `pilot01` used the `canary` profile on `testnet4`.

| Measure | Observed |
| --- | ---: |
| Initial funding, sats | 360549 |
| Confirmed miner fees, sats | 800 |
| Confirmed settlement virtual bytes | 282 |
| Offered invoices | 2 |
| Invoices settled by deadline | 1 |
| Value settled by deadline, sats | 1400 |
| Funded satoshi-blocks | 1438596 |
| Unavailable satoshi-blocks | 1438596 |
| Funded satoshi-seconds | 1580052906 |
| Unavailable satoshi-seconds | 1445284980 |
| Unavailable value at last observation, sats | 0 |
| Native inclusion receipts | 4 |
| Fresh Nova receipts | 0 |
| Recorded command failures | 0 |

The ledger uses the payer's canonical UTXO. Confirmed recipient outputs exit the payer's budget.
Block integrals use observed height advances above the previous high-water mark. Observer gaps
bound the timing resolution. Confirmation and unspent-change evidence comes from Bitcoin Core.
The current tip and any reorganization are recorded in the transaction observations.

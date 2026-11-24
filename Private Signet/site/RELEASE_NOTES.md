SatsHedgeZero's inverse BTC/USD DLC on a self-mined private Signet: first the prototype as it is, then the same contract settled by script under research consensus rules.

**Showcase:** https://patrickdugan.github.io/Spiral/shz-keyless/

## What is in it

- **The prototype, unchanged:** SatsHedgeZero's live 3-party clearing runs on a stock Core private Signet. The clearing transaction is 505 vB, all four outputs are unspent on both nodes, and both 1-sat shave probes were refused.
- **SHZ-K1, settled by script:**
  - each of 949 CET leaves checks the FROST oracle's per-digit BIP340 signatures with OP_CHECKSIGFROMSTACK, under the announced nonce;
  - TXCOMMIT binds the payouts to the spending transaction;
  - no party key can spend.
- **SHZ-K2, owners inside the output:**
  - every leaf rebuilds the output from its owner list, so a stale owner cannot spend;
  - a transfer leaf lets one owner, alone, move the position on-chain, and a second sale spends a coin that no longer exists;
  - SHZ's three-trade book settles netted in one keyless transaction: 1,475 / 1,250 / 825 sats at $125k, the prototype's clearing amounts;
  - the refund after CSV 144 ran on the Signet.
- **Trials:** 100 regtest trials (SHZ-K1, SHZ-K2, A/B and arm C) on patched Core with the rules on, the same binary with them off, and stock Core. All match their expected verdicts, and CI ran them on GitHub's runners.

## Scope

- These rules (TXCOMMIT, OP_CAT, restricted P2MR, research CSFS) exist only in a patched Bitcoin Core started with `-keylessresearch` on a custom-challenge Signet. They are not active on any public network.
- On stock rules every one of these spends is anyone-can-spend. The stock node in each run shows this by forking.

## Assets

| File | Contents |
|---|---|
| `shz-keyless-showcase-site.zip` | the static showcase page and its data |
| `shz-keyless-evidence.zip` | the regtest and Signet receipts behind every number, and RESULTS.md |
| `shz-keyless-code.zip` | the contract code, runners and offline tests |
| `SHA256SUMS` | checksums of the three archives |

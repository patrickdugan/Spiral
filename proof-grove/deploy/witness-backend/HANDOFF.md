# Handoff: host the Proof Grove Cashu Recovery backend on the Witness VPS

Written 2026-11-27 ~23:00 Taipei by Claude on the proving PC, for Claude on the PC that has the Witness VPS credentials.

## Goal

Serve the live Cashu Recovery app (UI + API) from the Witness VPS over HTTPS, so the "Check the holder-only exit"
form works for reviewers. The static copy at https://patrickdugan.github.io/Spiral/cashu-recovery/ already shows the
story, but on GitHub Pages it uses fixtures and the verify form cannot run.

## What is in this branch (`cashu/protected-redemption`)

- `proof-grove/` — the Python app (`python -m proofdesk serve`), standard library only for serving.
- Redesigned recovery page: `web/index.html`, `web/app.js`, `web/styles.css`, plus `proofdesk/stablecoin_adapter.py`
  (Liquity-style stablecoin on USDT/RGB via Utexo is a **roadmap panel only**; the adapter always answers `not_connected`).
- `deploy/witness-backend/data/` — the public regtest evidence the preview loads (≈90 KB, no secrets):

| File | sha256 |
|---|---|
| preview.json | ba048f6a596dc8a0cc18487256fea657e32f99cf8efb79b838b2923884f4ace7 |
| holder-receipt.json (pinned by preview.json) | 781de3e8278cd7ce627e4511dda61a3bb9ab7750833b0357dea00f3d3e6f46f9 |
| proof-grove-cashu-payout.zip | 7f5f47d67a8890be56b8455ed8fa94a472446bcb9c4870e7be991c246e406982 |
| http-verification.json | 98d8d738bbc1b909ddfe43519ae04eb17bb139d6fb1c90790d0784b8fd56f093 |
| cashu-v4-recovery-evidence-preview-verified.json | 16cfcc2ed0ece672159cb5a2aac152e9bbc517a8ce604a35af16f69678b37c26 |
| cashu-v4-issuance-and-holder-payout.zip | de062f2ae0bbe7ced84cae491aeeb4fe25919510e1b65e9df10f70722f3a42d9 |
| cashu-v4-funded-withheld-verdict-evidence.zip | e411a5a836e17d71d32ca8d4dcea2f4bfae1dc7686d34e0fef1e9f4f4f044106 |
| cashu-v4-refusal-verification.json | ecf5b59fd1eaa53335a24bd0420775016bfe62e57fd55f8bc976a6f50ef04655 |

## Run command (as on the proving PC)

```bash
cd Spiral/proof-grove
python3 -B -m proofdesk serve --port 8768 \
  --protected-preview deploy/witness-backend/data/preview.json \
  --protected-evidence-preview deploy/witness-backend/data/cashu-v4-recovery-evidence-preview-verified.json
# open http://127.0.0.1:8768/#protected-preview
```

Check it locally on the VPS first: `curl -s http://127.0.0.1:8768/api/status`, `/api/protected/preview?case=original`,
`/api/stablecoin/status`. On the proving PC the preview re-verified `verified: True`, 24,750 sats.

## Important constraint — decide deliberately

`proofdesk/__main__.py:75` refuses to load `--protected-preview` together with `--config`, `--hosted` or
`--bind 0.0.0.0`. The preview was built as a **local-only demo**. To publish it you must keep the app bound to
127.0.0.1 and put a TLS reverse proxy (e.g. Caddy) in front. That publicly exposes a read-only demo of archived
regtest evidence — no wallet, no keys, no mainnet funds — but it is a choice the user should confirm, not a default.
Do not patch out the guard.

Suggested shape: systemd unit running the command above as an unprivileged user with `Restart=on-failure`;
Caddy site `<subdomain> { reverse_proxy 127.0.0.1:8768 }` for automatic HTTPS; firewall open only 80/443.
Python 3.12+ is enough to serve. Ask the user for the domain/subdomain.

## Known gaps

- The live re-check path for the funded/proof-backed release was configured on the proving PC with
  `--protected-funded-preview outputs/cashu-v4-funded-preview-1.json`; that file is not present, so it is omitted here.
- The proof-backed BitVM3 release (SP1 → BitVM3, 24,750-sat regtest payout) is still being produced overnight on the
  proving PC. If it passes every check it will be pushed to branch `cashu/proof-backed-release-evidence`; the page
  marks it "in progress" until then. Only update the VPS from that branch after it exists.
- Uncommitted on the proving PC and intentionally NOT in this branch: someone's `--overissuance-control` work
  (tests/*, wallet/test-protected-extra-mint-batch.mjs, docs edit).

## State on the proving PC (for context only)

- Core proof of the exact 24,750-sat withdrawal: 37,309 shard STARKs, independently verified
  (`core_proof_verified`, program key `0x0030ae33…`, public values `8c7cb7de…`).
- Reduction: 3× Hyperstack RTX A6000 + laptop, all group roots verified twice; expected done ~02:45 Taipei, then
  M13 → M14 → funded regtest release → evidence → recipient check.
- Testnet4 holder-only CSV exit (same reserve script, no mint signature): txid
  `380aff2486d2b5654473fd33e1b971089604204e8e0c05995e4dd9bb2c0fc8d2`.

## Deployed (2026-11-27, from rev 1339774)

Live at **https://cashu-recovery.170-75-168-145.sslip.io/#protected-preview**.

- Code: `/opt/proof-grove-cashu-recovery/releases/<rev>/proof-grove` (root-owned, read-only), `current` symlink;
  evidence hashes recorded beside it in `evidence.sha256` and equal to the table above.
- Service: `proof-grove-cashu-recovery` (system user `pgcashu`, 127.0.0.1:8769, MemoryMax 192M, ProtectSystem=strict).
  Port 8768 was already taken by `proof-grove-regtest-api`.
- Caddy: site block appended to `/etc/caddy/Caddyfile` (backup `Caddyfile.bak-<UTC>` beside it). The local-demo guard
  in `server.py` is unchanged; Caddy sends `Host: 127.0.0.1:8769` and maps only this site's own `Origin` to
  `http://127.0.0.1:8769`. Any other Origin reaches proofdesk unchanged and gets `invalid_origin`.
- Redeploy a new rev: `git -c core.autocrlf=false archive --format=tar.gz -o pg-cashu-<rev>.tar.gz <rev> proof-grove`,
  copy it to `/tmp` on the box, then `sudo bash install.sh <rev>` (this file's sibling).

Checked after deploy: `/api/status`, `/api/protected/preview?case=original` (`verified: true`, 24,750 sats),
`/api/stablecoin/status` (`not_connected`) all 200 over HTTPS; in a browser the original payout verifies and the
substitute beneficiary is rejected; a POST with `Origin: https://evil.example` returns `invalid_origin`.

The bundled evidence manifest covers `issuance` and `refusal` only. The page also requests `accounting` and
`historical`, which answer 400 `recovery_accounting_not_configured` / `recovery_historical_not_configured`; adding
`evidence/nova-registry-verification.json` and the historical `verification/verification.json` entries to the manifest
would enable them.

# GitHub Pages demo

The public fixture demo is published at
<https://patrickdugan.github.io/Spiral/proof-grove/>. Its source lives in
`patrickdugan/Spiral` under `proof-grove/`.

GitHub Pages serves the interactive policy cases, the precomputed recovery
slider, exact public receipt downloads and the two recorded native regtest
reports. It does not run the Python service, M16 verifier, Core RPC, mint, wallet
keys or Ark signer. The local application retains those configured paths.

Build a static preview from the app directory:

```bash
python scripts/build-pages.py --output .runtime/pages-preview
python -m http.server 8899 --bind 127.0.0.1 --directory .runtime
```

Use a new or empty output directory. The exporter copies a fixed allowlist of
assets and public reports. It refuses to mix an existing directory into the
public bundle. It never packages `.runtime/`, local configuration or a wallet.
Each archive's exact UTF-8 bytes retain the CID computed by the Python exporter.
Relative asset paths allow hosting beneath the repository project path.

Spiral's shared `iob-pages.yml` workflow rebuilds both the In-and-Out Burger site
and Proof Grove when either source changes. It updates only their two directories
on `gh-pages`, preserves all other published content and explicitly requests a
Pages build after the push. Pages remains configured to publish `gh-pages` at
its root over HTTPS. No Vercel project is required.

The hosted browser check covers all eight cases, the slider's final height,
receipt-dialog and archive download, SHA-256/CID agreement, public result loading,
zero local API requests and desktop/phone layouts at 1440 and 390 px. See
`docs/hosted-browser-check.json` and `tests/hosted-browser.cjs`.

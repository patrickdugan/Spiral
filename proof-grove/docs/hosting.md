# Hosted app and authenticated backend

The hosted client is published at <https://patrickdugan.github.io/Spiral/proof-grove/>.
Its primary build connects to an authenticated HTTPS backend. Precomputed policy
examples live separately at `demo/`; an offline backend never substitutes them
for current chain or wallet state.

`web/backend-config.json` contains only the public API origin. The operator enters
an access token in the connection form. It stays in that tab's memory: it is not
placed in URLs, browser storage, Git, or the encrypted Cashu wallet. The client
refuses a backend whose status identifies it as a fixture/demo service.

The backend uses the existing native adapters:

- `GET /api/chainstate` reads the configured Bitcoin Core at request time.
- `POST /api/proofs/check` verifies uploaded M16 statement/final-proof bytes.
- `POST /api/proofs/recorded/check` checks only the server-owned, hash-pinned
  historical payment record. No browser-supplied file path is accepted.
- Core checks a checkpoint's active block/hash/chainwork and the payment block
  and proven tip. Cryptographic verification and payment admission remain
  separate; checking a historical proof never creates a new claim.
- Cashu and Bark reads use the configured providers. Missing or unavailable
  services are reported as such. Their reported states are not promoted to ZK
  evidence or guaranteed settlement.

Run the API behind an HTTPS reverse proxy:

```bash
python -m proofdesk serve --config /PRIVATE/testnet4.local.json --hosted --port 8767
```

The configuration names an environment variable containing a server-generated
32-byte URL-safe token, plus exact HTTPS origin and Host allowlists. The service
binds loopback by default. Unauthorized API calls receive 401. CORS preflight
never authorizes a real request. Mutation and private-exit-download permissions
are disabled by default; existing wallet signatures and regtest execution
restrictions still apply when an operator enables them. The CLI wallet uses
`PROOF_GROVE_DESK_TOKEN` for the same protected desk.

The approved VPS deployment is running on `170.75.168.145`. The app offers two
authenticated profiles: live testnet4 Core/native verification at
`https://proof-grove.170-75-168-145.sslip.io`, and persistent regtest Core/Bark/CDK
at `https://proof-grove-regtest.170-75-168-145.sslip.io`. The latter uses real
services and valueless test coins, not fixture responses. It does not accept
testnet4 proofs as funding. See [deployment details](../deploy/README.md) and the
[actual HTTPS/payment check](hosted-backend-check.json).

Retrieve the operator token on the owner's machine with
`ssh tradelayer-witness 'cat /opt/proof-grove/config/operator.env'`, then paste
only its value into the app's password field. Both profiles use this credential.
Disconnect before changing profiles; switching clears the previous credential
and rejects late responses from that connection. The mint and Bark RPC ports
are loopback-only. The encrypted CLI wallet runs beside these private providers.

Build into a new/empty output directory:

```bash
python scripts/build-pages.py --output .runtime/pages-preview
python -m http.server 8899 --bind 127.0.0.1 --directory .runtime
```

The exporter copies fixed allowlists for the connected client and its separate
fixture examples. It never packages local configuration, SQLite, keys or exit
bundles. Spiral's shared `iob-pages.yml` publishes both app directories on
`gh-pages` and explicitly requests the Pages build while preserving other content.

`tests/connected-hosting-browser.cjs` verifies the connection UI against an
explicitly mocked HTTPS backend; this is not native cryptographic evidence.
The independent gateway tests cover bearer authentication, origin enforcement,
checkpoint substitution and rotating Core cookies. Native proof checks are
recorded separately.

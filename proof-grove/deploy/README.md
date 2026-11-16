# VPS deployment

The authorized host is `170.75.168.145`, SSH alias `tradelayer-witness`, user
`ubuntu`. Its existing `rehearsal-bitcoind.service` runs a pruned, synced testnet4
node at `127.0.0.1:48332`. It must not be restarted or reconfigured by this
deployment. Read its rotating cookie from
`/home/ubuntu/rehearsal/btc-data/testnet4/.cookie`; do not copy the cookie into
the published website or a committed configuration.

The prepared deployment uses:

- `/opt/proof-grove/current`: a reviewed application release.
- `/opt/proof-grove/bin/m13-verify`: the SHA-256-pinned transcript-v2 verifier.
- `/opt/proof-grove/records`: the actual public testnet4 statement and wrap.
- `/opt/proof-grove/config/testnet4.local.json`: Core cookie path, checkpoint and
  verifier pins, exact allowed origin/hostname and fixed record file hashes.
- `/opt/proof-grove/config/operator.env`: a server-generated 32-byte URL-safe
  bearer credential, readable only by the service owner. No token goes in Git.
- `/opt/proof-grove/state`: writable SQLite and verifier scratch state.

`proof-grove.service` binds the API to `127.0.0.1:8767`. Caddy terminates HTTPS
and forwards only `/api/*`. The provisional hostname
`proof-grove.170-75-168-145.sslip.io` resolves to this server. Caddy needs public
ports 80/443 for certificate validation and HTTPS. The existing Core port remains
loopback-only. The hosted origin allowlist is exactly
`https://patrickdugan.github.io`; it is not a substitute for bearer authentication.

The API defaults to read-only access plus side-effect-free native proof checks.
It does not enable mint issuance, VTXO refresh, broadcasting or private recovery
bundle downloads merely because a token is valid. Existing wallet authorization
and network restrictions still apply. The encrypted CLI wallet can pass the
operator credential through `PROOF_GROVE_DESK_TOKEN` without saving it in the
vault or a URL.

The existing public testnet4 payment is historical and was already used by the
Burger demonstration. Its checkpoint and active-chain membership can be checked;
it must not become a fresh mint deposit or a second payout. The deployed record
check never reserves a payment. Its proving tip is older than the current node;
normal admission freshness rules remain unchanged.

Ark/Cashu requires a separate, explicitly identified backend and network. The
currently ported Bark backend supports mainnet, signet/testnet and regtest; it is
not a testnet4 Ark deployment. A separately labelled persistent regtest stack can
serve the existing tested Ark/Cashu flow after approval to install its container
runtime. Testnet4 deposits must never be credited as mainnet Ark funds. This
package does not silently invent a funded mint or an Ark operator.

Installing Caddy/Docker and adding system services are persistent server
changes. Automatic approval review currently requires explicit user approval
for that step. The source, unit, proxy configuration and verification checks can
be prepared before it. No package installation or service configuration has been
performed by the rejected command.

# VPS deployment

The authorized host is `170.75.168.145`, SSH alias `tradelayer-witness`, user
`ubuntu`. Its existing `rehearsal-bitcoind.service` runs a pruned, synced testnet4
node at `127.0.0.1:48332`. It must not be restarted or reconfigured by this
deployment. Read its rotating cookie from
`/home/ubuntu/rehearsal/btc-data/testnet4/.cookie`; do not copy the cookie into
the published website or a committed configuration.

The approved deployment is running and uses:

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

Ark/Cashu runs on a separate persistent regtest backend at
`https://proof-grove-regtest.170-75-168-145.sslip.io`. Bark 0.8.1 does not support
testnet4. This backend uses valueless regtest funds and never credits testnet4
payments. Its dedicated Core/Ark containers use digest-pinned images, ownership
labels, persistent volumes, bounded memory/CPU and rotating logs. Core, Bark,
CDK and the payment processor listen only on loopback or the private Docker
network. Only Caddy's authenticated HTTPS API is public.

Dedicated units are `proof-grove-bark`, `proof-grove-processor`,
`proof-grove-mint`, `proof-grove-regtest-api`, and `proof-grove-regtest-miner.timer`.
The sandbox miner generates a test block every 30 seconds and checks the network
before doing so. The regtest API allows owner-authenticated mutations; private
exit bundle downloads and exit broadcasting remain disabled. Fresh BIP39 seeds
come from Linux OS randomness. Credentials and databases stay under the private
`/opt/proof-grove/regtest` tree; the public fixture mnemonics are not used.

The owner explicitly approved Caddy, Docker and these services. Installation
uses `install-api.py --release GIT_ID --qa-directory OWNED_QA_DIRECTORY` after
staging the committed `app/` archive and pinned verifier/record files. It uses
the server's existing Node 24.22.1 and installs the locked Cashu SDK with
pnpm 11.25.0. `bootstrap-regtest.py` validates all binary hashes before starting
the isolated stack; rerunning retains databases and restarts only its own
regtest Core container. It never restarts the existing testnet4 node.

Run `python3 /opt/proof-grove/current/deploy/check-hosted.py` on the VPS to check
both public HTTPS origins and a fresh 25,000 sat regtest deposit through Cashu,
Ark receipt and refresh. The check retains its encrypted wallet and password in
a private `regtest/qa-*` directory and writes only a sanitized report to
`state/hosted-backend-check.json`. It does not stop the persistent providers.
See the committed [live check](../docs/hosted-backend-check.json).

Use `ssh tradelayer-witness 'cat /opt/proof-grove/config/operator.env'` privately
to retrieve the operator credential. Paste only its value into the hosted app.
Both profiles use that token; it is never bundled into Pages. Back up the private
regtest tree, volumes and encrypted owner vaults to retain test wallet recovery.
Proof checks do not remove Cashu custody or Ark expiry/liveness requirements.

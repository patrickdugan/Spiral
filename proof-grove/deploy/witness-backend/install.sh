#!/bin/bash
# Install the Proof Grove Cashu Recovery local-demo backend behind Caddy.
set -euo pipefail
REV=${1:?usage: install.sh <short-rev> (expects /tmp/pg-cashu-<rev>.tar.gz from git archive <rev> proof-grove)}
PORT=8769
DOMAIN=cashu-recovery.170-75-168-145.sslip.io
ROOT=/opt/proof-grove-cashu-recovery
TS=$(date -u +%Y%m%dT%H%M%SZ)

pkill -f 'proofdesk serve --port 8769' || true

id pgcashu >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin pgcashu

install -d -m 0755 -o root -g root "$ROOT" "$ROOT/releases"
rm -rf "$ROOT/releases/$REV"
install -d -m 0755 "$ROOT/releases/$REV"
tar -xzf /tmp/pg-cashu-$REV.tar.gz -C "$ROOT/releases/$REV"
chown -R root:root "$ROOT/releases/$REV"
chmod -R u=rwX,go=rX "$ROOT/releases/$REV"
ln -sfn "$ROOT/releases/$REV/proof-grove" "$ROOT/current"
(cd "$ROOT/current/deploy/witness-backend/data" && sha256sum *) > "$ROOT/releases/$REV/evidence.sha256"

cat > /etc/systemd/system/proof-grove-cashu-recovery.service <<UNIT
[Unit]
Description=Proof Grove Cashu Recovery read-only regtest demo (local-only preview, behind Caddy at $DOMAIN)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pgcashu
Group=pgcashu
WorkingDirectory=$ROOT/current
ExecStart=/usr/bin/python3 -B -m proofdesk serve --port $PORT --protected-preview deploy/witness-backend/data/preview.json --protected-evidence-preview deploy/witness-backend/data/cashu-v4-recovery-evidence-preview-verified.json
Restart=on-failure
RestartSec=5
MemoryMax=192M
TasksMax=64
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now proof-grove-cashu-recovery.service

if ! grep -q "^$DOMAIN " /etc/caddy/Caddyfile; then
  cp -p /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak-$TS"
  cat >> /etc/caddy/Caddyfile <<CADDY

# Proof Grove Cashu Recovery demo (archived regtest evidence, read-only; no wallet, keys or mainnet funds).
# proofdesk's local-demo guard accepts only Host 127.0.0.1:$PORT and that Origin, so the proxy maps
# exactly this site's origin to it; any other Origin passes through unchanged and is refused.
$DOMAIN {
    @own_origin header Origin https://$DOMAIN
    request_header @own_origin Origin http://127.0.0.1:$PORT
    reverse_proxy 127.0.0.1:$PORT {
        header_up Host 127.0.0.1:$PORT
        transport http {
            dial_timeout 3s
            response_header_timeout 120s
        }
    }
}
CADDY
fi
if ! PROOF_GROVE_API_DOMAIN=proof-grove.170-75-168-145.sslip.io caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  [ -f "/etc/caddy/Caddyfile.bak-$TS" ] && cp -p "/etc/caddy/Caddyfile.bak-$TS" /etc/caddy/Caddyfile
  echo "caddy validate failed; Caddyfile restored" >&2; exit 1
fi
systemctl reload caddy
systemctl is-active proof-grove-cashu-recovery caddy

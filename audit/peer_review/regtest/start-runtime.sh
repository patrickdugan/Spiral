#!/bin/sh
# Optional owned-regtest runtime: no system package installation or service unit.
set -eu
runtime=/var/tmp/spiral-capital-runtime
mkdir -p "$runtime/bin" "$runtime/logs"
if [ ! -x "$runtime/bin/docker" ]; then
  curl -fL --connect-timeout 20 --max-time 120 \
    https://download.docker.com/linux/static/stable/x86_64/docker-28.5.1.tgz \
    -o "$runtime/docker-28.5.1.tgz"
  printf '%s  %s\n' 5c0d19f31fece1accd0358bb8cff591fe25d7b6cba19f0fd412cbfdc07f75ff6 "$runtime/docker-28.5.1.tgz" | sha256sum -c -
  tar -xzf "$runtime/docker-28.5.1.tgz" -C "$runtime/bin" --strip-components=1
fi
export PATH="$runtime/bin:$PATH"
export DOCKER_HOST="unix://$runtime/docker.sock"
if docker info >/dev/null 2>&1; then
  docker info --format '{{.ServerVersion}} {{.Driver}}'
  exit 0
fi
if [ -f "$runtime/docker.pid" ] && kill -0 "$(cat "$runtime/docker.pid")" 2>/dev/null; then
  echo 'Existing task daemon is still starting; inspect its log instead of starting another.' >&2
  exit 1
fi
nohup dockerd --host="$DOCKER_HOST" --data-root="$runtime/data" \
  --exec-root="$runtime/exec" --pidfile="$runtime/docker.pid" \
  --storage-driver=overlay2 --iptables=false --ip6tables=false \
  --bridge=none --ip-forward=false --ip-masq=false \
  >"$runtime/logs/dockerd.log" 2>&1 </dev/null &
attempt=0
while [ "$attempt" -lt 30 ]; do
  if docker info >/dev/null 2>&1; then
    docker info --format '{{.ServerVersion}} {{.Driver}}'
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
tail -40 "$runtime/logs/dockerd.log"
exit 1

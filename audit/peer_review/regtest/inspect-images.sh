#!/bin/sh
set -eu
runtime=/var/tmp/spiral-capital-runtime
export PATH="$runtime/bin:$PATH" DOCKER_HOST="unix://$runtime/docker.sock"
mkdir -p "$runtime/evidence"
captain=secondark/captaind@sha256:9e1dff4d944ec3049bae08a45c6bb9d37ce66334a131a1faec42dfeac4d5f358
bark=secondark/bark@sha256:ebbcab48d5c45e83e3b9f4328213bf89151193b9dffca3785e3c35ff6b3fbc02
bitcoin=bitcoin/bitcoin@sha256:a1d05be6939b5c85132a761d2b795f5b8a2612ce53782263da4939778e461792
cln=elementsproject/lightningd@sha256:0421a5f0d1b2e1ad639edfa17d777816040e3850d91bae7f2d32186d9c1e6da4
docker image inspect "$captain" "$bark" "$bitcoin" "$cln" > "$runtime/evidence/images.json"
docker run --rm --network none --entrypoint /bin/sh "$captain" -c 'captaind --version; command -v watchmand; command -v postgres; cat /root/captaind/start.sh; cat /root/captaind/captaind.toml' > "$runtime/evidence/captaind-image.txt"
docker run --rm --network none --entrypoint /bin/sh "$bark" -c 'bark --version; cat /run.sh' > "$runtime/evidence/bark-image.txt"
docker run --rm --network none --entrypoint bitcoind "$bitcoin" --version > "$runtime/evidence/bitcoin-version.txt"
docker run --rm --network none --entrypoint lightningd "$cln" --version > "$runtime/evidence/cln-version.txt"
cat "$runtime/evidence/captaind-image.txt" "$runtime/evidence/bark-image.txt" "$runtime/evidence/cln-version.txt"

#!/usr/bin/env bash
# Local check in WSL: mirror the sources out of the Windows worktree, reuse the built
# Mathlib checkout by symlink, compile every module, print axioms, reject placeholders.
set -euo pipefail
export PATH="$HOME/.elan/bin:$PATH"
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/work/spiral-rent"
MATHLIB_PROJECT="$HOME/oai-verify/math/lean"
mkdir -p "$DST"
rsync -a --delete --exclude .lake "$SRC/" "$DST/"
cd "$DST"
sed -i 's/\r$//' lakefile.toml lean-toolchain SpiralRent.lean SpiralRent/*.lean
mkdir -p .lake/packages
CLOSURE="mathlib batteries aesop Qq proofwidgets importGraph LeanSearchClient plausible Cli"
for n in $CLOSURE; do
  ln -sfn "$MATHLIB_PROJECT/.lake/packages/$n" ".lake/packages/$n"
done
cp "$MATHLIB_PROJECT/lake-manifest.json" lake-manifest.json
CLOSURE="$CLOSURE" python3 - <<'PY'
import json, os
keep = set(os.environ["CLOSURE"].split())
m = json.load(open("lake-manifest.json"))
m["name"] = "spiral_rent"
m["packagesDir"] = ".lake/packages"
m["packages"] = [p for p in m["packages"] if p["name"] in keep]
for p in m["packages"]:
    if p["name"] == "mathlib":
        p["inherited"] = False
json.dump(m, open("lake-manifest.json", "w"), indent=1)
print("manifest packages:", [p["name"] for p in m["packages"]])
PY
if grep -REn '(^|[^[:alnum:]_])(sorry|admit)([^[:alnum:]_]|$)' SpiralRent/*.lean; then
  echo "placeholder found"; exit 1
fi
timeout 5400 lake build SpiralRent 2>&1 | grep -v '^✔' | grep -v 'linter' | tail -150
timeout 1800 lake env lean SpiralRent/Audit.lean 2>&1 | tail -40

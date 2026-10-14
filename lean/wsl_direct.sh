#!/bin/bash
# Direct-lean build of FeedbackChannel modules (in the order given), bypassing Lake, which
# sometimes spins without launching lean on this machine.
# Usage (from Git Bash):
#   MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /mnt/c/<worktree>/lean/wsl_direct.sh Mod1 Mod2 ...
# Module names are file stems under FeedbackChannel/; "root" builds FeedbackChannel.lean;
# "axioms" runs axioms_check.lean. Each worktree builds into its own WSL directory
# (~/work/fc-lean-<worktree name>, or $FC_LEAN_DIR), so parallel builds do not collide.
# Oleans of earlier modules persist there, so later runs need only the changed modules.
set -u
export PATH="$HOME/.elan/bin:$PATH"
SRC="$(cd "$(dirname "$0")" && pwd)"
WT_NAME="$(basename "$(dirname "$SRC")")"
DST="${FC_LEAN_DIR:-$HOME/work/fc-lean-$WT_NAME}"
mkdir -p "$DST"
rsync -a --delete --exclude '.lake' --exclude 'wsl_direct.sh' "$SRC/" "$DST/"
P="${MATHLIB_PKGS:-/root/oai-verify/math/lean/.lake/packages}"
LP=""
for pkg in Cli batteries Qq aesop proofwidgets importGraph LeanSearchClient plausible mathlib; do
  LP="$LP:$P/$pkg/.lake/build/lib/lean"
done
export LEAN_PATH="${LP#:}:$DST/.lake/build/lib/lean"
cd "$DST"
OUT=$DST/.lake/build/lib/lean
mkdir -p "$OUT/FeedbackChannel"
LOG=$DST/direct_build.log
: > "$LOG"
status=0
for mod in "$@"; do
  echo "== $mod $(date +%H:%M:%S) ==" >> "$LOG"
  case "$mod" in
    root) /usr/bin/time -f "%e s" lean FeedbackChannel.lean -o "$OUT/FeedbackChannel.olean" -i "$OUT/FeedbackChannel.ilean" >> "$LOG" 2>&1 ;;
    axioms) /usr/bin/time -f "%e s" lean axioms_check.lean >> "$LOG" 2>&1 ;;
    *) /usr/bin/time -f "%e s" lean "FeedbackChannel/$mod.lean" -o "$OUT/FeedbackChannel/$mod.olean" -i "$OUT/FeedbackChannel/$mod.ilean" >> "$LOG" 2>&1 ;;
  esac
  rc=$?
  echo "exit $rc for $mod" >> "$LOG"
  [ $rc -ne 0 ] && status=$rc
done
echo "ALL DONE $(date +%H:%M:%S)" >> "$LOG"
grep -v "deprecated\|unused\|Hint\|Omit\|linter\|^$\|\[apply\]\|ite_true" "$LOG" | cut -c1-240
exit $status

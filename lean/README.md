# FeedbackChannel: Lean formalizations

Lean 4 proofs of results in the feedback-channel notes under `paper/`. Each formalized claim is
listed in `CLAIMS.md` with the note it comes from, the Lean theorem, and how faithfully the Lean
statement matches the note's statement (the full claim, a special case, or a supporting lemma).

- Toolchain: `leanprover/lean4:v4.34.1` (`lean-toolchain`), Mathlib at
  `d13f23b723b8a846827a245b89c10fc7d3f11612` (`lakefile.toml`, `lake-manifest.json`).
- Build with Lake: `lake build`, then `lake env lean axioms_check.lean`, which prints the axioms
  every listed theorem depends on. The expected output is only `propext`, `Classical.choice` and
  `Quot.sound`: no `sorry`, no added axioms.
- On the author's machine Mathlib is prebuilt elsewhere, and `wsl_direct.sh` compiles modules
  directly against it, bypassing Lake.

Smoke test: `FeedbackChannel/Smoke.lean` states the shared-error judge identity of the
training-signal note (L4) and proves it by `ring`.

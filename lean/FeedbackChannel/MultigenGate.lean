import Mathlib.Tactic

/-!
# One generation, gate versus naive, under a fixed true gain (multigen note, Proposition 7)

Source: `paper/evaluation_feedback_multigen.md`, draft 0.5, §6; code
`src/spiral_ln/evaluation_feedback_multigen.py` (`one_step_gap_change`).

From state `(c, p_inc)` every candidate has true probability `p_inc + δ`; `M` is the best of the
`K` candidate counts, with an arbitrary finite law `w` on a finite set `S` of counts (in the note,
the law of the maximum of `K` i.i.d. `Bin(n, p_inc + δ)` counts). A rule with cap `a` accepts iff
`M > a` (naive: `a = c`; gate: `a = c + t(c)`); on acceptance the state becomes `(M, p_inc + δ)`,
otherwise it stays. The readout gap of a state is `count/n - p`.

**Proposition 7.** One generation changes the gap by `E[((M - c)/n - δ) 1_accept]`
(`gapChange_eq`), so
`Δρ_naive - Δρ_gate = E[((M - c)/n - δ) 1{c < M ≤ c + t(c)}]` (`naive_sub_gate`). Hence
(i) `δ ≤ 1/n` makes the difference `≥ 0` (`naive_sub_gate_nonneg`); (ii) `δ ≥ t(c)/n` makes it
`≤ 0` (`naive_sub_gate_nonpos`); both together make it zero; (iii) otherwise the sign depends on the
law of `M` on the window (`sign_undetermined`, stated for arbitrary finite laws).
-/

namespace FeedbackChannel.MultigenGate

open Finset

variable (n : ℕ) (c : ℕ) (pInc δ : ℝ) (S : Finset ℕ) (w : ℕ → ℝ)

/-- Readout gap of a state: reported score `count/n` minus true value `p`. -/
noncomputable def gap (count : ℕ) (p : ℝ) : ℝ := (count : ℝ) / n - p

/-- Expected gap after one generation from `(c, p_inc)` under the rule that accepts iff `M > a`. -/
noncomputable def nextGap (a : ℕ) : ℝ :=
  ∑ j ∈ S, w j * (if a < j then gap n j (pInc + δ) else gap n c pInc)

/-- One-generation change of the expected readout gap under the rule with cap `a`. -/
noncomputable def gapChange (a : ℕ) : ℝ := nextGap n c pInc δ S w a - gap n c pInc

/-- **Proposition 7, first sentence:** the one-generation gap change is
`E[((M - c)/n - δ) 1{M > a}]`. -/
theorem gapChange_eq (hw : ∑ j ∈ S, w j = 1) (a : ℕ) :
    gapChange n c pInc δ S w a =
      ∑ j ∈ S, w j * (if a < j then ((j : ℝ) - c) / n - δ else 0) := by
  unfold gapChange nextGap
  have key : ∀ j, w j * (if a < j then gap n j (pInc + δ) else gap n c pInc) =
      w j * gap n c pInc + w j * (if a < j then ((j : ℝ) - c) / n - δ else 0) := by
    intro j
    unfold gap
    split_ifs <;> ring
  rw [Finset.sum_congr rfl (fun j _ => key j), Finset.sum_add_distrib, ← Finset.sum_mul, hw,
    one_mul]
  ring

/-- **Proposition 7, the identity:**
`Δρ_naive - Δρ_gate = E[((M - c)/n - δ) 1{c < M ≤ c + t}]`. -/
theorem naive_sub_gate (hw : ∑ j ∈ S, w j = 1) (t : ℕ) :
    gapChange n c pInc δ S w c - gapChange n c pInc δ S w (c + t) =
      ∑ j ∈ S, w j * (if c < j ∧ j ≤ c + t then ((j : ℝ) - c) / n - δ else 0) := by
  rw [gapChange_eq n c pInc δ S w hw, gapChange_eq n c pInc δ S w hw, ← Finset.sum_sub_distrib]
  apply Finset.sum_congr rfl
  intro j _
  by_cases h1 : c < j <;> by_cases h2 : c + t < j
  · rw [ite_eq_left h1, ite_eq_left h2, ite_eq_right (by omega)]; ring
  · rw [ite_eq_left h1, ite_eq_right h2, ite_eq_left (by omega)]; ring
  · omega
  · rw [ite_eq_right h1, ite_eq_right h2, ite_eq_right (by omega)]; ring

/-- **Proposition 7 (i):** if `δ ≤ 1/n`, the integrand is non-negative on the window, so the gate
lowers the one-generation gap change: `Δρ_naive - Δρ_gate ≥ 0`. -/
theorem naive_sub_gate_nonneg (hw0 : ∀ j ∈ S, 0 ≤ w j) (hw : ∑ j ∈ S, w j = 1) (hn : 0 < n)
    (hδ : δ ≤ 1 / n) (t : ℕ) :
    0 ≤ gapChange n c pInc δ S w c - gapChange n c pInc δ S w (c + t) := by
  rw [naive_sub_gate n c pInc δ S w hw]
  apply Finset.sum_nonneg
  intro j hj
  apply mul_nonneg (hw0 j hj)
  split_ifs with h
  · have hn' : (0 : ℝ) < n := by exact_mod_cast hn
    have hjc : (1 : ℝ) ≤ (j : ℝ) - c := by
      have : c + 1 ≤ j := h.1
      have : ((c + 1 : ℕ) : ℝ) ≤ j := by exact_mod_cast this
      push_cast at this
      linarith
    have : 1 / (n : ℝ) ≤ ((j : ℝ) - c) / n := div_le_div_of_nonneg_right hjc hn'.le
    linarith
  · exact le_rfl

/-- **Proposition 7 (ii):** if `δ ≥ t/n`, the integrand is non-positive on the window, so the gate
raises the one-generation gap change: `Δρ_naive - Δρ_gate ≤ 0`. -/
theorem naive_sub_gate_nonpos (hw0 : ∀ j ∈ S, 0 ≤ w j) (hw : ∑ j ∈ S, w j = 1) (hn : 0 < n)
    (t : ℕ) (hδ : (t : ℝ) / n ≤ δ) :
    gapChange n c pInc δ S w c - gapChange n c pInc δ S w (c + t) ≤ 0 := by
  rw [naive_sub_gate n c pInc δ S w hw]
  apply Finset.sum_nonpos
  intro j hj
  apply mul_nonpos_of_nonneg_of_nonpos (hw0 j hj)
  split_ifs with h
  · have hn' : (0 : ℝ) < n := by exact_mod_cast hn
    have hjc : (j : ℝ) - c ≤ t := by
      have : j ≤ c + t := h.2
      have : (j : ℝ) ≤ ((c + t : ℕ) : ℝ) := by exact_mod_cast this
      push_cast at this
      linarith
    have : ((j : ℝ) - c) / n ≤ (t : ℝ) / n := div_le_div_of_nonneg_right hjc hn'.le
    linarith
  · exact le_rfl

/-- **Proposition 7, (i) and (ii) together:** if both `δ ≤ 1/n` and `δ ≥ t/n` (e.g. `t ≤ 1` and
`δ = 1/n`, the note's `n = 8, z = 1` cells), the one-step difference is exactly zero. -/
theorem naive_sub_gate_eq_zero (hw0 : ∀ j ∈ S, 0 ≤ w j) (hw : ∑ j ∈ S, w j = 1) (hn : 0 < n)
    (t : ℕ) (h1 : δ ≤ 1 / n) (h2 : (t : ℝ) / n ≤ δ) :
    gapChange n c pInc δ S w c - gapChange n c pInc δ S w (c + t) = 0 :=
  le_antisymm (naive_sub_gate_nonpos n c pInc δ S w hw0 hw hn t h2)
    (naive_sub_gate_nonneg n c pInc δ S w hw0 hw hn h1 t)

/-- **Proposition 7 (iii)**, for arbitrary finite laws of `M`: if `1/n < δ < t/n`, a law
concentrated at `c + 1` makes the difference negative and a law concentrated at `c + t` makes it
positive, so the sign is not determined by `δ` and `t` alone. -/
theorem sign_undetermined (hn : 0 < n) (t : ℕ) (h1 : 1 / (n : ℝ) < δ) (h2 : δ < (t : ℝ) / n) :
    gapChange n c pInc δ {c + 1} (fun _ => 1) c -
        gapChange n c pInc δ {c + 1} (fun _ => 1) (c + t) < 0 ∧
      0 < gapChange n c pInc δ {c + t} (fun _ => 1) c -
        gapChange n c pInc δ {c + t} (fun _ => 1) (c + t) := by
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  have ht : 1 ≤ t := by
    by_contra h
    have : t = 0 := by omega
    subst this
    simp at h2
    have : 0 < 1 / (n : ℝ) := by positivity
    linarith
  constructor
  · rw [naive_sub_gate n c pInc δ _ _ (by simp)]
    rw [Finset.sum_singleton, ite_eq_left ⟨by omega, by omega⟩]
    push_cast
    rw [show ((c : ℝ) + 1 - c) = 1 by ring]
    linarith
  · rw [naive_sub_gate n c pInc δ _ _ (by simp)]
    rw [Finset.sum_singleton, ite_eq_left ⟨by omega, le_rfl⟩]
    push_cast
    rw [show ((c : ℝ) + t - c) = t by ring]
    linarith

end FeedbackChannel.MultigenGate

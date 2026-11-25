import Mathlib.Tactic

/-!
# Restricted payout graph: the cut condition

Vaults `v` hold budgets `C v`; a vault can pay creditor `j` at most `u v j` (zero where the
payout edge is absent); creditor `j` is owed `d j`. A payout `x` is feasible when
`0 ≤ x v j ≤ u v j` and `Σ_j x v j ≤ C v`; it fully delivers when `Σ_v x v j = d j`.

* `cut_necessary`: full delivery implies, for every creditor set `S`,
  `Σ_{j∈S} d j ≤ Σ_v min (C v) (Σ_{j∈S} u v j)`.
* `cut_sufficient_single_vault`: with one vault, the cut condition is also sufficient.
* `cut_sufficient_unrestricted`: with every edge large enough (`d j ≤ u v j`), the condition
  for `S = univ` (total budget covers total demand) is sufficient, by a proportional payout.
* `deficit_of_cut`: a violated cut certifies that no feasible payout delivers fully.

General sufficiency is the max-flow/min-cut theorem for this three-layer network; it is not
formalised here and the experiment checks it numerically (`cbm/flow.py`).
-/

namespace Spiral.Rent

variable {V J : Type*} [Fintype V] [Fintype J] [DecidableEq J]

structure Payout (C : V → ℚ) (u : V → J → ℚ) (x : V → J → ℚ) : Prop where
  nonneg : ∀ v j, 0 ≤ x v j
  edge : ∀ v j, x v j ≤ u v j
  budget : ∀ v, ∑ j, x v j ≤ C v

def Delivers (d : J → ℚ) (x : V → J → ℚ) : Prop := ∀ j, ∑ v, x v j = d j

def CutHolds (C : V → ℚ) (u : V → J → ℚ) (d : J → ℚ) : Prop :=
  ∀ S : Finset J, ∑ j ∈ S, d j ≤ ∑ v, min (C v) (∑ j ∈ S, u v j)

theorem cut_necessary {C : V → ℚ} {u : V → J → ℚ} {d : J → ℚ} {x : V → J → ℚ}
    (hx : Payout C u x) (hd : Delivers d x) : CutHolds C u d := by
  intro S
  calc ∑ j ∈ S, d j = ∑ j ∈ S, ∑ v, x v j := Finset.sum_congr rfl (fun j _ => (hd j).symm)
    _ = ∑ v, ∑ j ∈ S, x v j := Finset.sum_comm
    _ ≤ ∑ v, min (C v) (∑ j ∈ S, u v j) := by
        apply Finset.sum_le_sum
        intro v _
        apply le_min
        · calc ∑ j ∈ S, x v j ≤ ∑ j, x v j :=
                Finset.sum_le_sum_of_subset_of_nonneg (Finset.subset_univ S)
                  (fun j _ _ => hx.nonneg v j)
            _ ≤ C v := hx.budget v
        · exact Finset.sum_le_sum (fun j _ => hx.edge v j)

theorem deficit_of_cut {C : V → ℚ} {u : V → J → ℚ} {d : J → ℚ} (S : Finset J)
    (hS : ∑ v, min (C v) (∑ j ∈ S, u v j) < ∑ j ∈ S, d j) :
    ¬ ∃ x, Payout C u x ∧ Delivers d x := by
  rintro ⟨x, hx, hd⟩
  exact absurd (cut_necessary hx hd S) (not_le.mpr hS)

/-- One vault: the cut condition is sufficient (pay every creditor in full). -/
theorem cut_sufficient_single_vault (C : ℚ) (u d : J → ℚ) (hd : ∀ j, 0 ≤ d j)
    (h : CutHolds (fun _ : Unit => C) (fun _ => u) d) :
    ∃ x : Unit → J → ℚ, Payout (fun _ => C) (fun _ => u) x ∧ Delivers d x := by
  refine ⟨fun _ j => d j, ⟨fun _ j => hd j, ?_, ?_⟩, ?_⟩
  · intro _ j
    have := h {j}
    simp only [Finset.sum_singleton, Finset.univ_unique, Finset.sum_const, Finset.card_singleton, one_smul] at this
    exact le_trans this (min_le_right _ _)
  · intro _
    have := h Finset.univ
    simp only [Finset.univ_unique, Finset.sum_const, Finset.card_singleton, one_smul] at this
    exact le_trans this (min_le_left _ _)
  · intro j
    simp

/-- Unrestricted payout edges: total budget covering total demand suffices. -/
theorem cut_sufficient_unrestricted (C : V → ℚ) (u : V → J → ℚ) (d : J → ℚ)
    (hC : ∀ v, 0 ≤ C v) (hd : ∀ j, 0 ≤ d j) (hu : ∀ v j, d j ≤ u v j)
    (hpos : 0 < ∑ v, C v) (htot : ∑ j, d j ≤ ∑ v, C v) :
    ∃ x, Payout C u x ∧ Delivers d x := by
  set T := ∑ v, C v with hT
  refine ⟨fun v j => C v / T * d j, ⟨?_, ?_, ?_⟩, ?_⟩
  · intro v j
    exact mul_nonneg (div_nonneg (hC v) hpos.le) (hd j)
  · intro v j
    have hfrac : C v / T ≤ 1 := by
      rw [div_le_one hpos]
      exact Finset.single_le_sum (fun w _ => hC w) (Finset.mem_univ v)
    calc C v / T * d j ≤ 1 * d j := mul_le_mul_of_nonneg_right hfrac (hd j)
      _ = d j := one_mul _
      _ ≤ u v j := hu v j
  · intro v
    rw [← Finset.mul_sum]
    calc C v / T * ∑ j, d j ≤ C v / T * T :=
          mul_le_mul_of_nonneg_left htot (div_nonneg (hC v) hpos.le)
      _ = C v := div_mul_cancel₀ (C v) hpos.ne'
  · intro j
    rw [← Finset.sum_mul, ← Finset.sum_div, ← hT, div_self hpos.ne', one_mul]

end Spiral.Rent

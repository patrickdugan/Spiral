import Mathlib.Tactic

/-!
# The value of extra payout capacity is capped by the substitute's cost

A clearing round pays creditors `j` from vaults `v` (budget `C v`, edge capacity `u v j`,
edge cost `c v j ≥ 0`); any undelivered demand is covered by a substitute (an LP advance,
or the creditor's wait for a unilateral exit) at cost `k ≥ 0` per unit. The cost of a
partial payout `x` is

    cost x = Σ_v Σ_j c v j * x v j + k * Σ_j (d j - Σ_v x v j).

`capacity_value_le_substitute`: any payout feasible when vault `v0` has `δ` more budget can
be turned into one feasible under the original budget whose cost is higher by at most
`k * δ`. Hence the marginal value of capacity (the dual price of the budget constraint in the
min-cost-flow LP) never exceeds the substitute's unit cost: free entry of the substitute caps
the scarcity rent of directional payout capacity.
-/

namespace Spiral.Rent

variable {V J : Type*} [Fintype V] [Fintype J] [DecidableEq V]

/-- Feasible partial payout: within edge capacities and budgets, never above demand. -/
structure Partial (C : V → ℚ) (u : V → J → ℚ) (d : J → ℚ) (x : V → J → ℚ) : Prop where
  nonneg : ∀ v j, 0 ≤ x v j
  edge : ∀ v j, x v j ≤ u v j
  budget : ∀ v, ∑ j, x v j ≤ C v
  under : ∀ j, ∑ v, x v j ≤ d j

def payCost (c : V → J → ℚ) (k : ℚ) (d : J → ℚ) (x : V → J → ℚ) : ℚ :=
  (∑ v, ∑ j, c v j * x v j) + k * ∑ j, (d j - ∑ v, x v j)

/-- Scale vault `v0`'s row by `t`. -/
def scaleRow (x : V → J → ℚ) (v0 : V) (t : ℚ) : V → J → ℚ :=
  fun v j => x v j + (if v = v0 then (t - 1) * x v0 j else 0)

private lemma col_sum_scale (x : V → J → ℚ) (v0 : V) (t : ℚ) (j : J) :
    ∑ v, scaleRow x v0 t v j = (∑ v, x v j) + (t - 1) * x v0 j := by
  simp [scaleRow, Finset.sum_add_distrib]

private lemma row_sum_scale (x : V → J → ℚ) (v0 : V) (t : ℚ) :
    ∑ j, scaleRow x v0 t v0 j = t * ∑ j, x v0 j := by
  have h : ∀ j, scaleRow x v0 t v0 j = t * x v0 j := by
    intro j
    show x v0 j + (if v0 = v0 then (t - 1) * x v0 j else 0) = t * x v0 j
    rw [if_pos rfl]
    ring
  rw [Finset.mul_sum]
  exact Finset.sum_congr rfl (fun j _ => h j)

private lemma cost_scale (c : V → J → ℚ) (k : ℚ) (d : J → ℚ) (x : V → J → ℚ) (v0 : V) (t : ℚ) :
    payCost c k d (scaleRow x v0 t) =
      payCost c k d x + (t - 1) * (∑ j, c v0 j * x v0 j) + k * ((1 - t) * ∑ j, x v0 j) := by
  unfold payCost
  have h1 : ∑ v, ∑ j, c v j * scaleRow x v0 t v j
      = (∑ v, ∑ j, c v j * x v j) + (t - 1) * ∑ j, c v0 j * x v0 j := by
    simp only [scaleRow, mul_add, Finset.sum_add_distrib]
    congr 1
    rw [Finset.sum_comm]
    simp only [mul_ite, mul_zero]
    rw [Finset.mul_sum]
    apply Finset.sum_congr rfl
    intro j _
    rw [Finset.sum_ite_eq']
    simp only [Finset.mem_univ, if_true]
    ring
  have h2 : ∑ j, (d j - ∑ v, scaleRow x v0 t v j)
      = (∑ j, (d j - ∑ v, x v j)) + (1 - t) * ∑ j, x v0 j := by
    simp only [col_sum_scale]
    rw [Finset.mul_sum, ← Finset.sum_add_distrib]
    apply Finset.sum_congr rfl
    intro j _
    ring
  rw [h1, h2]
  ring

theorem capacity_value_le_substitute
    (C : V → ℚ) (u c : V → J → ℚ) (d : J → ℚ) (k δ : ℚ) (v0 : V)
    (hc : ∀ v j, 0 ≤ c v j) (hk : 0 ≤ k) (hδ : 0 ≤ δ) (hC : 0 ≤ C v0)
    (x : V → J → ℚ) (hx : Partial (Function.update C v0 (C v0 + δ)) u d x) :
    ∃ x', Partial C u d x' ∧ payCost c k d x' ≤ payCost c k d x + k * δ := by
  set S := ∑ j, x v0 j with hS
  have hS0 : 0 ≤ S := Finset.sum_nonneg (fun j _ => hx.nonneg v0 j)
  have hSb : S ≤ C v0 + δ := by
    have := hx.budget v0
    simpa [Function.update_self] using this
  -- Scale factor: 1 if the row already fits, else C v0 / S.
  set t : ℚ := if S ≤ C v0 then 1 else C v0 / S with ht
  have ht0 : 0 ≤ t := by
    rw [ht]; split_ifs
    · norm_num
    · exact div_nonneg hC hS0
  have ht1 : t ≤ 1 := by
    rw [ht]; split_ifs with h
    · exact le_refl _
    · replace h := lt_of_not_ge h
      rw [div_le_one (lt_of_le_of_lt hC h)]
      exact h.le
  have htS : t * S ≤ C v0 := by
    rw [ht]; split_ifs with h
    · simpa using h
    · replace h := lt_of_not_ge h
      rw [div_mul_cancel₀ _ (ne_of_gt (lt_of_le_of_lt hC h))]
  have hloss : (1 - t) * S ≤ δ := by
    rw [ht]; split_ifs with h
    · simpa using hδ
    · replace h := lt_of_not_ge h
      have hSpos : 0 < S := lt_of_le_of_lt hC h
      rw [sub_mul, one_mul, div_mul_cancel₀ _ hSpos.ne']
      linarith
  refine ⟨scaleRow x v0 t, ⟨?_, ?_, ?_, ?_⟩, ?_⟩
  · intro v j
    unfold scaleRow
    split_ifs with hv
    · subst hv
      have := hx.nonneg v j
      nlinarith
    · simpa using hx.nonneg v j
  · intro v j
    unfold scaleRow
    split_ifs with hv
    · subst hv
      have h0 := hx.nonneg v j
      have h1 := hx.edge v j
      nlinarith
    · simpa using hx.edge v j
  · intro v
    by_cases hv : v = v0
    · subst hv
      rw [row_sum_scale]
      exact htS
    · have hrow : ∑ j, scaleRow x v0 t v j = ∑ j, x v j := by
        simp [scaleRow, hv]
      rw [hrow]
      have := hx.budget v
      simpa [Function.update_of_ne hv] using this
  · intro j
    rw [col_sum_scale]
    have h0 := hx.nonneg v0 j
    have h1 := hx.under j
    nlinarith
  · rw [cost_scale]
    have hcx : 0 ≤ ∑ j, c v0 j * x v0 j :=
      Finset.sum_nonneg (fun j _ => mul_nonneg (hc v0 j) (hx.nonneg v0 j))
    have : (t - 1) * (∑ j, c v0 j * x v0 j) ≤ 0 :=
      mul_nonpos_of_nonpos_of_nonneg (by linarith) hcx
    have : k * ((1 - t) * S) ≤ k * δ := mul_le_mul_of_nonneg_left hloss hk
    linarith

end Spiral.Rent

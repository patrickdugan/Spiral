import Mathlib.Tactic

/-!
# Fee feasibility (Where the Rent Moves, Proposition "fee ceiling")

All quantities are costs over one horizon in one numeraire (ℚ, e.g. BTC).

* `C0U` customers' all-in cost under the baseline settlement architecture,
* `C1U` customers' cost under the candidate, before the candidate's service fee,
* `C1P` the provider's incremental cost of the candidate service,
* `F`   the total fee customers pay the provider.

Aggregate participation is `C1U + F ≤ C0U`; non-negative provider economic profit is
`C1P ≤ F`. A fee satisfying both exists iff `C1P ≤ C0U - C1U`, and the provider's profit is
bounded by the net resource saving. Individual participation is the per-customer version;
it implies the aggregate one but not conversely (`aggregate_not_individual`).
-/

namespace Spiral.Rent

theorem fee_feasible_iff (C0U C1U C1P : ℚ) :
    (∃ F : ℚ, C1U + F ≤ C0U ∧ C1P ≤ F) ↔ C1P ≤ C0U - C1U := by
  constructor
  · rintro ⟨F, h1, h2⟩
    linarith
  · intro h
    exact ⟨C1P, by linarith, le_refl _⟩

theorem profit_le_surplus {C0U C1U C1P F : ℚ} (h : C1U + F ≤ C0U) :
    F - C1P ≤ C0U - C1U - C1P := by
  linarith

/-- The fee ceiling is the customer saving; the floor is the provider cost. -/
theorem fee_between {C0U C1U C1P F : ℚ} (hU : C1U + F ≤ C0U) (hP : C1P ≤ F) :
    C1P ≤ F ∧ F ≤ C0U - C1U :=
  ⟨hP, by linarith⟩

/-- Individual participation (each customer `i` pays at most its own saving) implies the
aggregate condition. -/
theorem individual_implies_aggregate {ι : Type*} (s : Finset ι)
    (save fee : ι → ℚ) (h : ∀ i ∈ s, fee i ≤ save i) :
    ∑ i ∈ s, fee i ≤ ∑ i ∈ s, save i :=
  Finset.sum_le_sum h

/-- The converse fails: a fee schedule can respect the aggregate saving while charging one
customer more than its own saving. -/
theorem aggregate_not_individual :
    ∃ save fee : Fin 2 → ℚ,
      (∑ i, fee i ≤ ∑ i, save i) ∧ ¬ (∀ i, fee i ≤ save i) := by
  refine ⟨![3, 0], ![1, 1], ?_, ?_⟩
  · simp [Fin.sum_univ_two]
    norm_num
  · intro h
    have := h 1
    simp at this
    norm_num at this

/-- Capital-carry form used in the paper: with a common simple annual rate `r`, saved
BTC-days `ΔA ≥ 0`, other customer resource savings `ΔO`, matched notional `V > 0`, the fee
ceiling in basis points is `1e4 (r ΔA / 365 + ΔO) / V`, and it is monotone in `r` and `ΔA`. -/
def ceilingBps (r ΔA ΔO V : ℚ) : ℚ := 10000 * (r * ΔA / 365 + ΔO) / V

theorem ceilingBps_mono_rate {r r' ΔA ΔO V : ℚ} (hV : 0 < V) (hA : 0 ≤ ΔA) (hr : r ≤ r') :
    ceilingBps r ΔA ΔO V ≤ ceilingBps r' ΔA ΔO V := by
  unfold ceilingBps
  apply div_le_div_of_nonneg_right _ hV.le
  have : r * ΔA ≤ r' * ΔA := mul_le_mul_of_nonneg_right hr hA
  nlinarith

end Spiral.Rent

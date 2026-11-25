import Mathlib.Tactic

/-!
# Matured-obligation netting

For matured, simultaneously enforceable obligations `g i j ≥ 0` (party `i` owes `j`), the
net position of `i` is `b i = Σ_j g j i - Σ_j g i j`. Net positions sum to zero, the net
settlement flow `N = Σ_i max(b i, 0)` equals half of `Σ_i |b i|`, and `N ≤ G = Σ g`.

The statement is about payment flow at maturity. Nothing here says anything about the
collateral backing unexpired contracts: `N = 0` with `G > 0` (`netting_zero_flow`) still
needs segregated margin before maturity.
-/

namespace Spiral.Rent

variable {n : ℕ}

def netPos (g : Fin n → Fin n → ℚ) (i : Fin n) : ℚ :=
  (∑ j, g j i) - ∑ j, g i j

def gross (g : Fin n → Fin n → ℚ) : ℚ := ∑ i, ∑ j, g i j

def netFlow (g : Fin n → Fin n → ℚ) : ℚ := ∑ i, max (netPos g i) 0

theorem sum_netPos (g : Fin n → Fin n → ℚ) : ∑ i, netPos g i = 0 := by
  unfold netPos
  rw [Finset.sum_sub_distrib, Finset.sum_comm]
  ring

theorem netFlow_le_gross (g : Fin n → Fin n → ℚ) (hg : ∀ i j, 0 ≤ g i j) :
    netFlow g ≤ gross g := by
  unfold netFlow gross
  calc ∑ i, max (netPos g i) 0 ≤ ∑ i, ∑ j, g j i := by
        apply Finset.sum_le_sum
        intro i _
        apply max_le
        · unfold netPos
          have : 0 ≤ ∑ j, g i j := Finset.sum_nonneg (fun j _ => hg i j)
          linarith
        · exact Finset.sum_nonneg (fun j _ => hg j i)
    _ = ∑ i, ∑ j, g i j := Finset.sum_comm

theorem netFlow_eq_half_abs (g : Fin n → Fin n → ℚ) :
    netFlow g = (∑ i, |netPos g i|) / 2 := by
  have h0 := sum_netPos g
  have habs : ∀ i, |netPos g i| = 2 * max (netPos g i) 0 - netPos g i := by
    intro i
    rcases le_total 0 (netPos g i) with h | h
    · rw [abs_of_nonneg h, max_eq_left h]; ring
    · rw [abs_of_nonpos h, max_eq_right h]; ring
  unfold netFlow
  rw [Finset.sum_congr rfl (fun i _ => habs i), Finset.sum_sub_distrib, ← Finset.mul_sum, h0]
  ring

/-- The note's counterexample: A owes B 5 and B owes A 5. Gross 10, net flow 0. -/
theorem netting_zero_flow :
    let g : Fin 2 → Fin 2 → ℚ := fun i j => if i ≠ j then 5 else 0
    gross g = 10 ∧ netFlow g = 0 := by
  intro g
  constructor
  · simp [gross, g, Fin.sum_univ_two]; norm_num
  · simp [netFlow, netPos, g, Fin.sum_univ_two]

end Spiral.Rent

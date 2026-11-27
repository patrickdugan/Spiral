import Mathlib.Tactic

/-!
# Portfolio margin: a gap buffer that covers a bounded move

A portfolio with net USD notional `n` in inverse (BTC-settled) contracts changes its BTC
mark-to-market by `n * (1/P1 - 1/P0)` when the price moves from `P0` to `P1`. If collateral
covers the current loss `L0` plus the buffer `|n| * g / ((1 - g) * P0)`, then after any move
with `|P1 - P0| ≤ g * P0` (`0 ≤ g < 1`) it still covers the loss. Hence portfolio margin
backs every claim at a liquidation taken within the period over which moves are bounded by
`g`; claims are impaired only on moves larger than `g`, which the experiment counts.
-/

namespace Spiral.Rent

theorem inverse_move_bound {P0 P1 g : ℚ} (hP0 : 0 < P0) (hg1 : g < 1)
    (hmove : |P1 - P0| ≤ g * P0) :
    |1 / P1 - 1 / P0| ≤ g / ((1 - g) * P0) := by
  have h1g : 0 < 1 - g := by linarith
  have hlow : (1 - g) * P0 ≤ P1 := by
    have := (abs_le.mp hmove).1
    nlinarith
  have hP1 : 0 < P1 := lt_of_lt_of_le (mul_pos h1g hP0) hlow
  have e : 1 / P1 - 1 / P0 = (P0 - P1) / (P0 * P1) := by
    field_simp
  rw [e, abs_div, abs_of_pos (mul_pos hP0 hP1), div_le_div_iff₀ (mul_pos hP0 hP1) (mul_pos h1g hP0)]
  have hm : |P0 - P1| ≤ g * P0 := by rwa [abs_sub_comm]
  have hg0 : 0 ≤ g := by
    by_contra h
    have h' : g < 0 := lt_of_not_ge h
    have := mul_neg_of_neg_of_pos h' hP0
    linarith [abs_nonneg (P1 - P0)]
  calc |P0 - P1| * ((1 - g) * P0) ≤ g * P0 * ((1 - g) * P0) :=
        mul_le_mul_of_nonneg_right hm (mul_pos h1g hP0).le
    _ ≤ g * (P0 * P1) := by nlinarith [mul_nonneg hg0 hP0.le]

theorem gap_buffer_covers {P0 P1 g n L0 col : ℚ} (hP0 : 0 < P0) (hg1 : g < 1)
    (hmove : |P1 - P0| ≤ g * P0) (hcol : L0 + |n| * (g / ((1 - g) * P0)) ≤ col) :
    L0 + n * (1 / P1 - 1 / P0) ≤ col := by
  have hb := inverse_move_bound hP0 hg1 hmove
  have : n * (1 / P1 - 1 / P0) ≤ |n| * (g / ((1 - g) * P0)) :=
    calc n * (1 / P1 - 1 / P0) ≤ |n * (1 / P1 - 1 / P0)| := le_abs_self _
      _ = |n| * |1 / P1 - 1 / P0| := abs_mul _ _
      _ ≤ |n| * (g / ((1 - g) * P0)) := mul_le_mul_of_nonneg_left hb (abs_nonneg n)
  linarith

end Spiral.Rent

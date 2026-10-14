import Mathlib.Tactic
import Mathlib.Analysis.Calculus.Deriv.Add
import Mathlib.Analysis.Calculus.Deriv.Mul
import Mathlib.LinearAlgebra.Matrix.Block
import Mathlib.LinearAlgebra.Matrix.Rank

/-!
# Four raters: the residuals' Jacobian minor (Proposition 6b)

Source: `paper/gold_calibration_second_grader.md` §8, Proposition 6(b): the residuals' `6 × 15`
Jacobian in the centred moments has rank 6 wherever `c₁₂c₁₃ ≠ 0`, model or not; on the columns
`(c₂₄, c₃₄, k₁₂₄, k₁₃₄, k₂₃₄, k₁₂₃₄)` the minor is lower triangular with determinant
`-c₁₂⁴c₁₃²`.

The fifteen coordinates are taken as free real variables
`z = (p₁, p₂, p₃, p₄, c₁₂, c₁₃, c₁₄, c₂₃, c₂₄, c₃₄, k₁₂₃, k₁₂₄, k₁₃₄, k₂₃₄, k₁₂₃₄)`
(indices `0..14`). Each residual is the note's equality written as left side minus right side, in
the order that makes the minor lower triangular. The Jacobian entries are computed by Lean as
partial derivatives (`deriv` along coordinate lines), not entered by hand.
-/

namespace FeedbackChannel.RatersJacobian

/-- The six residuals:
`c₁₃c₂₄ - c₁₄c₂₃`, `c₁₂c₃₄ - c₁₃c₂₄`, `k₁₂₃c₁₄ - k₁₂₄c₁₃`, `k₁₂₃c₁₄ - k₁₃₄c₁₂`,
`k₁₂₃c₂₄ - k₂₃₄c₁₂`, `(k₁₂₃₄ - c₁₂c₃₄)c₁₂ - k₁₂₃k₁₂₄`. -/
def resid (z : Fin 15 → ℝ) : Fin 6 → ℝ :=
  ![z 5 * z 8 - z 6 * z 7,
    z 4 * z 9 - z 5 * z 8,
    z 10 * z 6 - z 11 * z 5,
    z 10 * z 6 - z 12 * z 4,
    z 10 * z 8 - z 13 * z 4,
    (z 14 - z 4 * z 9) * z 4 - z 10 * z 11]

/-- The `6 × 15` Jacobian of the residuals: entry `(r, j)` is the partial derivative of residual
`r` in coordinate `j` at `z`. -/
noncomputable def jac (z : Fin 15 → ℝ) : Matrix (Fin 6) (Fin 15) ℝ :=
  Matrix.of fun r j => deriv (fun t => resid (Function.update z j t) r) (z j)

/-- The columns `c₂₄, c₃₄, k₁₂₄, k₁₃₄, k₂₃₄, k₁₂₃₄`. -/
def cols : Fin 6 → Fin 15 := ![8, 9, 11, 12, 13, 14]

/-- The `6 × 6` minor on those columns. -/
noncomputable def minor (z : Fin 15 → ℝ) : Matrix (Fin 6) (Fin 6) ℝ := (jac z).submatrix id cols

/-- The minor, entry by entry (computed, lower triangular). -/
theorem minor_eq (z : Fin 15 → ℝ) :
    minor z = !![z 5, 0, 0, 0, 0, 0;
      -z 5, z 4, 0, 0, 0, 0;
      0, 0, -z 5, 0, 0, 0;
      0, 0, 0, -z 4, 0, 0;
      z 10, 0, 0, 0, -z 4, 0;
      0, -z 4 ^ 2, -z 10, 0, 0, z 4] := by
  ext r c
  fin_cases r <;> fin_cases c <;>
    (simp [minor, jac, resid, cols, Function.update_apply]; try ring)

/-- **Proposition 6(b), determinant.** At every point (model or not) the minor has determinant
`-c₁₂⁴ c₁₃²`. -/
theorem minor_det (z : Fin 15 → ℝ) : (minor z).det = -(z 4) ^ 4 * (z 5) ^ 2 := by
  rw [minor_eq, Matrix.det_of_isLowerTriangular]
  · simp [Fin.prod_univ_six]
    ring
  · intro i j hij
    rw [OrderDual.toDual_lt_toDual] at hij
    fin_cases i <;> fin_cases j <;> simp_all

/-- **Proposition 6(b), rank.** Wherever `c₁₂ c₁₃ ≠ 0` the residuals' `6 × 15` Jacobian has
rank 6. -/
theorem jac_rank (z : Fin 15 → ℝ) (h : z 4 * z 5 ≠ 0) : (jac z).rank = 6 := by
  have h4 : z 4 ≠ 0 := left_ne_zero_of_mul h
  have h5 : z 5 ≠ 0 := right_ne_zero_of_mul h
  apply le_antisymm
  · simpa using Matrix.rank_le_card_height (jac z)
  · have hdet : (minor z).det ≠ 0 := by
      rw [minor_det]; simp [h4, h5]
    have hunit : IsUnit (minor z) :=
      (Matrix.isUnit_iff_isUnit_det _).2 (isUnit_iff_ne_zero.2 hdet)
    have h6 : (minor z).rank = 6 := by
      simpa using Matrix.rank_of_isUnit (minor z) hunit
    have hle : (minor z).rank ≤ (jac z).rank := Matrix.rank_submatrix_le (jac z) id cols
    omega

end FeedbackChannel.RatersJacobian

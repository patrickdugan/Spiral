import FeedbackChannel.SelectionContainment
import Mathlib.MeasureTheory.Integral.IntervalIntegral.FundThmCalculus

/-!
# The tie-free value of Theorem B

Source: `paper/selection_law_kl_containment.md`, draft 0.3, §2, proof step (ii): in the tie-free
(continuous) case the best-of-`K` law has density `K u^{K-1}` against the probability-integral
transform `u`, and its KL divergence is
`∫₀¹ K u^{K-1} ln(K u^{K-1}) du = ln K - (K - 1)/K = λ_K`.

`tieFree_integral` proves this integral identity (by the fundamental theorem of calculus with the
antiderivative `G` of `SelectionContainment`). It is the integral that the discrete proof of
Theorem B telescopes to; the measure-theoretic statement that an atomless score law attains it
(the density computation of step (ii)) is not formalized.
-/

namespace FeedbackChannel.SelectionTieFree

open Real MeasureTheory FeedbackChannel.SelectionContainment

theorem mul_log_h {K : ℕ} (hK : 1 ≤ K) {x : ℝ} (hx : 0 < x) :
    (K * x ^ (K - 1)) * log (K * x ^ (K - 1)) = K * x ^ (K - 1) * (log K + (K - 1) * log x) := by
  have hK0 : (0 : ℝ) < K := by exact_mod_cast hK
  rw [Real.log_mul (by positivity) (by positivity), Real.log_pow]
  push_cast [Nat.cast_sub hK]
  ring

/-- **Tie-free value** (Theorem B, step (ii)):
`∫₀¹ K u^{K-1} ln(K u^{K-1}) du = ln K - (K - 1)/K`. -/
theorem tieFree_integral {K : ℕ} (hK : 1 ≤ K) :
    ∫ u in (0 : ℝ)..1, (K * u ^ (K - 1)) * log (K * u ^ (K - 1)) = lam K := by
  rw [intervalIntegral.integral_eq_sub_of_hasDerivAt_of_le zero_le_one
    (continuous_G hK).continuousOn
    (fun x hx => (hasDerivAt_G hK hx.1).congr_deriv (mul_log_h hK hx.1).symm)
    (Continuous.intervalIntegrable (by fun_prop) 0 1)]
  rw [G_one, G_zero hK, sub_zero]

end FeedbackChannel.SelectionTieFree

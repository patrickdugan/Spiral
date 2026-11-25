import Mathlib.Tactic

/-!
# Contestable execution: no positive markup under symmetric price competition

`n ≥ 2` routers offer the same execution service at constant marginal cost `c`; a customer
buys from a lowest-price router and pays a switching cost `σ ≥ 0` to leave its incumbent.
A price profile is an equilibrium if no router gains by a unilateral deviation.

* `undercut_profitable`: with zero switching cost, a common price `p > c` is not an
  equilibrium: a router serving none (or a share) of demand gains by pricing at `p - ε`.
* `sustainable_markup`: an incumbent facing a rival at cost `c` cannot sustain a markup
  above `σ` without losing the customer.

These are the conditional statements of Section "Where the rent moves"; they assume
identical service, divisible prices and no capacity limits, which the paper relaxes.
-/

namespace Spiral.Rent

/-- Profit of a router that sells the whole demand `D` at price `p` with cost `c`. -/
def profit (p c D : ℚ) : ℚ := (p - c) * D

/-- With a common price `p > c` shared by `k ≥ 2` routers (each earns a `1/k` share), a
deviation to a slightly lower price captures the whole demand and strictly gains. -/
theorem undercut_profitable {p c D : ℚ} {k : ℕ} (hk : 2 ≤ k) (hD : 0 < D) (hp : c < p) :
    ∃ p' : ℚ, c < p' ∧ p' < p ∧ profit p c D / k < profit p' c D := by
  have hk' : (2 : ℚ) ≤ k := by exact_mod_cast hk
  have hkpos : (0 : ℚ) < k := by linarith
  refine ⟨p - (p - c) / 4, by linarith, by linarith, ?_⟩
  unfold profit
  rw [div_lt_iff₀ hkpos]
  have hm : 0 < (p - c) * D := mul_pos (by linarith) hD
  nlinarith

/-- A customer stays with an incumbent at price `p` only if `p ≤ c + σ` (a rival at cost
plus the switching cost is no cheaper); the sustainable markup is then at most `σ`. -/
theorem sustainable_markup {p c σ : ℚ} (hstay : p ≤ c + σ) : p - c ≤ σ := by linarith

end Spiral.Rent

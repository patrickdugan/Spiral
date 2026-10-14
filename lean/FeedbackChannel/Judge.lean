import Mathlib.Tactic

/-!
# Measuring the judge's shared error: bookkeeping and gold noise

Source: `paper/judge_shared_error_measurement.md`, §2 (Proposition 1) and §5 (Proposition 2 and its
Corollary, the gold-noise identity).

The gold-noise model is stated on the eight latent cells `(C, J, F)`: `C` the controller is right,
`J` the judge is right, `F` the gold label is flipped. `Pr[C] = a`; the judge is wrong with
probability `e0` when the controller is right and `e1` when it is wrong; `F` is independent of
`(C, J)` with `Pr[F] = η`. Measured against the gold, controller-right is `C ⊕ F` and judge-right
is `J ⊕ F`. Every measured quantity below is a sum over the eight cells, not a closed form.
-/

namespace FeedbackChannel.Judge

open Finset

/-! ## Proposition 1: the bookkeeping identity on a count table -/

/-- **Proposition 1.** For every table `(R₀, R₁, W₀, W₁)` with `m > 0` items,
`(R₀ + W₁)/m = â - ε̂ + 2(1 - â) ε̂₁` with `â = (R₀ + R₁)/m`, `ε̂ = (R₁ + W₁)/m` and
`ε̂₁ = W₁/W`, `W = W₀ + W₁` (Lean's `x / 0 = 0` makes the `W = 0` case the note's convention). -/
theorem prop1_bookkeeping (R0 R1 W0 W1 : ℕ) (hm : 0 < R0 + R1 + W0 + W1) :
    ((R0 : ℝ) + W1) / (R0 + R1 + W0 + W1) =
      ((R0 : ℝ) + R1) / (R0 + R1 + W0 + W1) - ((R1 : ℝ) + W1) / (R0 + R1 + W0 + W1) +
        2 * (1 - ((R0 : ℝ) + R1) / (R0 + R1 + W0 + W1)) * ((W1 : ℝ) / (W0 + W1)) := by
  have hm' : ((R0 : ℝ) + R1 + W0 + W1) ≠ 0 := by
    have : (0 : ℝ) < R0 + R1 + W0 + W1 := by exact_mod_cast hm
    exact this.ne'
  rcases Nat.eq_zero_or_pos (W0 + W1) with hW | hW
  · have h0 : W0 = 0 := by omega
    have h1 : W1 = 0 := by omega
    subst h0 h1
    simp only [Nat.cast_zero, add_zero, div_zero, mul_zero] at hm' ⊢
    field_simp
    ring
  · have hW' : ((W0 : ℝ) + W1) ≠ 0 := by
      have : (0 : ℝ) < W0 + W1 := by exact_mod_cast hW
      exact this.ne'
    field_simp
    ring

/-! ## Proposition 2: the gold-noise model on latent cells -/

/-- Probability of the latent cell `(c, j, f)`: controller right `c`, judge right `j`, gold
flipped `f`. -/
def cell (a e0 e1 η : ℝ) (c j f : Bool) : ℝ :=
  (if c then a * (if j then 1 - e0 else e0) else (1 - a) * (if j then 1 - e1 else e1)) *
    (if f then η else 1 - η)

/-- True controller accuracy `Pr[C]`. -/
def trueAcc (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool, if c = true then cell a e0 e1 η c j f else 0

/-- True judge error `Pr[¬J]`. -/
def trueErr (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool, if j = false then cell a e0 e1 η c j f else 0

/-- Measured controller accuracy `a' = Pr[C ⊕ F]`. -/
def measAcc (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool, if (c ^^ f) = true then cell a e0 e1 η c j f else 0

/-- Measured judge error `ε' = Pr[¬(J ⊕ F)]`. -/
def measErr (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool, if (j ^^ f) = false then cell a e0 e1 η c j f else 0

/-- Measured wrong–wrong rate `W₁'/m = Pr[¬(C ⊕ F) ∧ ¬(J ⊕ F)]`. -/
def measW1 (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool,
    if (c ^^ f) = false ∧ (j ^^ f) = false then cell a e0 e1 η c j f else 0

/-- True agreement rate `Pr[C = J]`. -/
def trueAgree (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool, if c = j then cell a e0 e1 η c j f else 0

/-- Measured agreement rate `Pr[C ⊕ F = J ⊕ F]`. -/
def measAgree (a e0 e1 η : ℝ) : ℝ :=
  ∑ c : Bool, ∑ j : Bool, ∑ f : Bool, if (c ^^ f) = (j ^^ f) then cell a e0 e1 η c j f else 0

/-- The model's parameters mean what the note says: `Pr[C] = a` and
`Pr[¬J] = ε = a e0 + (1 - a) e1`. -/
theorem model_params (a e0 e1 η : ℝ) :
    trueAcc a e0 e1 η = a ∧ trueErr a e0 e1 η = a * e0 + (1 - a) * e1 := by
  constructor <;> simp [trueAcc, trueErr, cell] <;> ring

/-- **Proposition 2.** `a' = η + a(1 - 2η)`, `ε' = η + ε(1 - 2η)` and
`W₁'/m = (1 - a) ε₁ + η (a - ε)`, with `ε = a ε₀ + (1 - a) ε₁`; and the agreement rate is
invariant under gold noise. -/
theorem prop2 (a e0 e1 η : ℝ) :
    measAcc a e0 e1 η = η + a * (1 - 2 * η) ∧
    measErr a e0 e1 η = η + (a * e0 + (1 - a) * e1) * (1 - 2 * η) ∧
    measW1 a e0 e1 η = (1 - a) * e1 + η * (a - (a * e0 + (1 - a) * e1)) ∧
    measAgree a e0 e1 η = trueAgree a e0 e1 η := by
  refine ⟨?_, ?_, ?_, ?_⟩ <;>
    simp [measAcc, measErr, measW1, measAgree, trueAgree, cell] <;> ring

/-- **Proposition 2, inversion.** For `η ≠ 1/2`: `a = (a' - η)/(1 - 2η)` and
`ε = (ε' - η)/(1 - 2η)`; for `a ≠ 1`: `ε₁ = (ε₁'(1 - a') - η (a - ε))/(1 - a)`, where
`ε₁'(1 - a') = W₁'/m`. -/
theorem prop2_inverse (a e0 e1 η : ℝ) (hη : η ≠ 1 / 2) (ha : a ≠ 1) :
    a = (measAcc a e0 e1 η - η) / (1 - 2 * η) ∧
    a * e0 + (1 - a) * e1 = (measErr a e0 e1 η - η) / (1 - 2 * η) ∧
    e1 = (measW1 a e0 e1 η - η * (a - (a * e0 + (1 - a) * e1))) / (1 - a) := by
  obtain ⟨hA, hE, hW, -⟩ := prop2 a e0 e1 η
  have h2 : (1 - 2 * η) ≠ 0 := by
    intro h; apply hη; linarith
  have h1 : (1 - a) ≠ 0 := sub_ne_zero.2 (Ne.symm ha)
  refine ⟨?_, ?_, ?_⟩
  · rw [hA, eq_div_iff h2]; ring
  · rw [hE, eq_div_iff h2]; ring
  · rw [hW, eq_div_iff h1]; ring

/-- **Corollary (gold-noise identity).** If the judge is independent of the controller in the
note's sense `ε₁ = ε` (`ε = a ε₀ + (1 - a) ε₁`), the measured excess
`(ε₁' - ε')(1 - a') = W₁'/m - ε'(1 - a')` equals `η (1 - η)(2a - 1)(1 - 2ε)` exactly. -/
theorem gold_noise_excess (a e0 e1 η : ℝ) (hind : e1 = a * e0 + (1 - a) * e1) :
    measW1 a e0 e1 η - measErr a e0 e1 η * (1 - measAcc a e0 e1 η) =
      η * (1 - η) * (2 * a - 1) * (1 - 2 * (a * e0 + (1 - a) * e1)) := by
  obtain ⟨hA, hE, hW, -⟩ := prop2 a e0 e1 η
  rw [hA, hE, hW]
  linear_combination (1 - a) * hind

/-- **Corollary, with the measured shared error `ε₁' = (W₁'/m)/(1 - a')`** (for `a' ≠ 1`):
`(ε₁' - ε')(1 - a') = η (1 - η)(2a - 1)(1 - 2ε)` for an independent judge. -/
theorem gold_noise_excess_rate (a e0 e1 η : ℝ) (hind : e1 = a * e0 + (1 - a) * e1)
    (ha' : measAcc a e0 e1 η ≠ 1) :
    (measW1 a e0 e1 η / (1 - measAcc a e0 e1 η) - measErr a e0 e1 η) *
        (1 - measAcc a e0 e1 η) =
      η * (1 - η) * (2 * a - 1) * (1 - 2 * (a * e0 + (1 - a) * e1)) := by
  have h : (1 - measAcc a e0 e1 η) ≠ 0 := sub_ne_zero.2 (Ne.symm ha')
  rw [sub_mul, div_mul_cancel₀ _ h]
  exact gold_noise_excess a e0 e1 η hind

/-- The excess is positive whenever `0 < η < 1`, `a > 1/2` and `ε < 1/2`. -/
theorem gold_noise_excess_pos {a ε η : ℝ} (hη0 : 0 < η) (hη1 : η < 1) (ha : 1 / 2 < a)
    (hε : ε < 1 / 2) : 0 < η * (1 - η) * (2 * a - 1) * (1 - 2 * ε) := by
  apply mul_pos (mul_pos (mul_pos hη0 (by linarith)) (by linarith)) (by linarith)

/-- **Fixture** (`η = 1/20`, `a = 4/5`, independent judge `ε₀ = ε₁ = 1/10`): `a' = 77/100`,
`ε' = 7/50`, `ε₁' = 11/46`, and the excess `ε₁' - ε' = 57/575`. For the maximally shared judge
(`ε₀ = 0`, `ε₁ = 1/2`, marginal `1/10`) the inversion returns `ε₁ = 1/2`. -/
theorem fixture :
    measAcc (4 / 5) (1 / 10) (1 / 10) (1 / 20) = 77 / 100 ∧
    measErr (4 / 5) (1 / 10) (1 / 10) (1 / 20) = 7 / 50 ∧
    measW1 (4 / 5) (1 / 10) (1 / 10) (1 / 20) / (1 - measAcc (4 / 5) (1 / 10) (1 / 10) (1 / 20))
      = 11 / 46 ∧
    measW1 (4 / 5) (1 / 10) (1 / 10) (1 / 20) / (1 - measAcc (4 / 5) (1 / 10) (1 / 10) (1 / 20))
      - measErr (4 / 5) (1 / 10) (1 / 10) (1 / 20) = 57 / 575 ∧
    (measW1 (4 / 5) 0 (1 / 2) (1 / 20) - 1 / 20 * (4 / 5 - (4 / 5 * 0 + (1 - 4 / 5) * (1 / 2)))) /
      (1 - 4 / 5) = 1 / 2 := by
  obtain ⟨hA, hE, hW, -⟩ := prop2 (4 / 5 : ℝ) (1 / 10) (1 / 10) (1 / 20)
  obtain ⟨-, -, hW', -⟩ := prop2 (4 / 5 : ℝ) 0 (1 / 2) (1 / 20)
  rw [hA, hE, hW, hW']
  norm_num

end FeedbackChannel.Judge

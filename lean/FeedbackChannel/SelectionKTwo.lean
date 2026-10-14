import Mathlib.Tactic
import Mathlib.Data.Nat.Choose.Central
import Mathlib.Data.Nat.Choose.Vandermonde
import Mathlib.Algebra.BigOperators.Intervals
import Mathlib.Algebra.BigOperators.NatAntidiagonal
import Mathlib.Analysis.Real.Pi.Wallis
import Mathlib.Analysis.Complex.ExponentialBounds

/-!
# The `K = 2` monotone-approach theorem (selection-KL note, D.5)

Source: `paper/selection_law_kl_containment.md`, draft 0.3, §4 D.5; code
`src/spiral_ln/evaluation_selection_kl.py` (`scaled_gap_squared`, `centered_max`).

Setting: `X₁, X₂` i.i.d. `Bin(n, ½)`, `Y_k = X_k - n/2`, `M_n(2) = E max(Y₁, Y₂) = n γ(n, 2, ½)`,
`a_n(2) = M_n(2)/√n`.

**Theorem (`K = 2`).** `a_n(2)² = n C(2n, n)² / (4·16ⁿ)`,
`a_{n+1}(2)²/a_n(2)² = (2n + 1)²/(4n(n + 1)) = 1 + 1/(4n(n + 1)) > 1`, and `a_n(2) ↑ 1/(2√π)`.
*Proof steps.* `M_n(2) = ½ E|S - n|` with `S ~ Bin(2n, ½)` (`M2_eq_half_meanAbsDev`); de Moivre's
identity `E|S - n| = n C(2n, n)/4ⁿ` (`meanAbsDev_eq`); hence the closed form (`aSq_eq`) and the step
ratio (`aSq_succ_div`, `step_ratio_eq`, `step_ratio_gt_one`), so `a_n(2)` increases strictly
(`a_strictMonoOn`). The limit uses Mathlib's Wallis product: `a_n(2)² = n/(4(2n + 1) W_n)`
(`aSq_eq_wallis`), `a_n(2)² → 1/(4π)` (`tendsto_aSq`), `a_n(2) → 1/(2√π)` (`tendsto_a`). For the
KL-normalized ratio `r(n, 2, ½) = 2 a_n(2)/√(2λ₂)`: strictly increasing (`r_strictMonoOn`), limit
`1/(√π √(2λ₂))` (`tendsto_r`), never attained (`r_lt_lim`). The identification of that limit with
`c₂ = E[M₂]/√(2λ₂)` uses the Gaussian value `E[M₂] = 1/√π`, which is not formalized.

Remark on the note: the telescoped product `a_n(2)² = (1/16) ∏_{j<n} (2j+1)²/((2j)(2j+2))` must
start at `j = 1` (the `j = 0` factor has a zero denominator); with `j = 1, …, n - 1` it is the
step ratio telescoped from `a_1(2)² = 1/16`.

All expectations are finite sums against the binomial masses `C(n, x)/2ⁿ`.
-/

namespace FeedbackChannel.SelectionKTwo

open Finset Filter Topology Real

/-- Mass of `Bin(n, ½)` at `x`. -/
noncomputable def binHalf (n x : ℕ) : ℝ := (n.choose x : ℝ) / 2 ^ n

/-- `M_n(2) = E[max(Y₁, Y₂)]` with `Y_k = X_k - n/2` and `X₁, X₂` i.i.d. `Bin(n, ½)`. -/
noncomputable def M2 (n : ℕ) : ℝ :=
  ∑ x ∈ range (n + 1), ∑ y ∈ range (n + 1),
    binHalf n x * binHalf n y * (max (x : ℝ) y - n / 2)

/-- `E|S - n|` for `S ~ Bin(2n, ½)`. -/
noncomputable def meanAbsDev (n : ℕ) : ℝ :=
  ∑ s ∈ range (2 * n + 1), binHalf (2 * n) s * |(s : ℝ) - n|

/-- `a_n(2)² = M_n(2)²/n`. -/
noncomputable def aSq (n : ℕ) : ℝ := M2 n ^ 2 / n

/-- `a_n(2) = M_n(2)/√n = √n · γ(n, 2, ½)`. -/
noncomputable def a (n : ℕ) : ℝ := M2 n / √(n : ℝ)

/-! ## De Moivre's mean absolute deviation -/

/-- Telescoping partial sums: `∑_{s ≤ j} (s - (m+1)) C(2m+2, s) = -(m+1) C(2m+1, j)`. -/
theorem partial_sum (m j : ℕ) :
    ∑ s ∈ range (j + 1), ((s : ℝ) - (m + 1)) * ((2 * m + 2).choose s : ℝ) =
      -((m : ℝ) + 1) * ((2 * m + 1).choose j : ℝ) := by
  induction j with
  | zero => simp
  | succ j ih =>
    rw [sum_range_succ, ih]
    have h1 : (2 * m + 2) * (2 * m + 1).choose j = (2 * m + 2).choose (j + 1) * (j + 1) :=
      Nat.add_one_mul_choose_eq (2 * m + 1) j
    have h2 : (2 * m + 2).choose (j + 1) = (2 * m + 1).choose j + (2 * m + 1).choose (j + 1) :=
      Nat.choose_succ_succ _ _
    have h1' : ((2 : ℝ) * m + 2) * ((2 * m + 1).choose j : ℝ) =
        ((2 * m + 2).choose (j + 1) : ℝ) * ((j : ℝ) + 1) := by exact_mod_cast h1
    have h2' : ((2 * m + 2).choose (j + 1) : ℝ) =
        ((2 * m + 1).choose j : ℝ) + ((2 * m + 1).choose (j + 1) : ℝ) := by exact_mod_cast h2
    push_cast
    linear_combination (-1 : ℝ) * h1' - ((m : ℝ) + 1) * h2'

/-- **De Moivre's identity** (integer form): `∑_s C(2n, s) |s - n| = n C(2n, n)`. -/
theorem sum_choose_abs (n : ℕ) :
    ∑ s ∈ range (2 * n + 1), ((2 * n).choose s : ℝ) * |(s : ℝ) - n| =
      n * ((2 * n).choose n : ℝ) := by
  rcases n with _ | m
  · simp
  · rw [show 2 * (m + 1) = 2 * m + 2 by ring]
    rw [← Finset.sum_range_add_sum_Ico _ (show m + 1 ≤ 2 * m + 2 + 1 by omega)]
    have hlow : ∑ s ∈ range (m + 1), ((2 * m + 2).choose s : ℝ) * |(s : ℝ) - ((m + 1 : ℕ) : ℝ)|
        = -∑ s ∈ range (m + 1), ((s : ℝ) - (m + 1)) * ((2 * m + 2).choose s : ℝ) := by
      rw [← Finset.sum_neg_distrib]
      apply Finset.sum_congr rfl
      intro s hs
      rw [mem_range] at hs
      have : (s : ℝ) < m + 1 := by exact_mod_cast hs
      rw [abs_of_neg (by push_cast; linarith)]
      push_cast
      ring
    have hup : ∑ s ∈ Ico (m + 1) (2 * m + 2 + 1),
          ((2 * m + 2).choose s : ℝ) * |(s : ℝ) - ((m + 1 : ℕ) : ℝ)|
        = ∑ s ∈ Ico (m + 1) (2 * m + 2 + 1), ((s : ℝ) - (m + 1)) * ((2 * m + 2).choose s : ℝ) := by
      apply Finset.sum_congr rfl
      intro s hs
      rw [mem_Ico] at hs
      have : (m : ℝ) + 1 ≤ s := by exact_mod_cast hs.1
      rw [abs_of_nonneg (by push_cast; linarith)]
      push_cast
      ring
    have htot := Finset.sum_range_add_sum_Ico
      (fun s => ((s : ℝ) - (m + 1)) * ((2 * m + 2).choose s : ℝ)) (show m + 1 ≤ 2 * m + 2 + 1 by omega)
    rw [partial_sum m (2 * m + 2), Nat.choose_eq_zero_of_lt (by omega : 2 * m + 1 < 2 * m + 2),
      partial_sum m m] at htot
    rw [hlow, hup, partial_sum m m]
    have hsym : (2 * m + 2).choose (m + 1) = (2 * m + 1).choose m + (2 * m + 1).choose m := by
      rw [show (2 * m + 2).choose (m + 1) = (2 * m + 1).choose m + (2 * m + 1).choose (m + 1) from
        Nat.choose_succ_succ _ _, Nat.choose_symm_half]
    have hsym' : ((2 * m + 2).choose (m + 1) : ℝ) =
        ((2 * m + 1).choose m : ℝ) + ((2 * m + 1).choose m : ℝ) := by exact_mod_cast hsym
    rw [hsym']
    push_cast at htot ⊢
    linarith

/-- **De Moivre's identity**: `E|S - n| = n C(2n, n)/4ⁿ` for `S ~ Bin(2n, ½)` (the denominator is
`4ⁿ`, as the note stresses). -/
theorem meanAbsDev_eq (n : ℕ) : meanAbsDev n = n * ((2 * n).choose n : ℝ) / 4 ^ n := by
  unfold meanAbsDev binHalf
  have h4 : (2 : ℝ) ^ (2 * n) = 4 ^ n := by rw [pow_mul]; norm_num
  rw [h4, ← sum_choose_abs n, Finset.sum_div]
  apply Finset.sum_congr rfl
  intro s _
  ring

/-! ## `M_n(2) = ½ E|S - n|` -/

theorem binHalf_sum_centered (n : ℕ) :
    ∑ x ∈ range (n + 1), binHalf n x * ((x : ℝ) - n / 2) = 0 := by
  set T := ∑ x ∈ range (n + 1), binHalf n x * ((x : ℝ) - n / 2) with hT
  have hrefl : T = -T := by
    have := Finset.sum_range_reflect (fun x => binHalf n x * ((x : ℝ) - n / 2)) (n + 1)
    rw [hT]
    conv_lhs => rw [← this]
    rw [← Finset.sum_neg_distrib]
    apply Finset.sum_congr rfl
    intro x hx
    rw [mem_range] at hx
    have hx' : x ≤ n := by omega
    rw [show n + 1 - 1 - x = n - x by omega]
    unfold binHalf
    rw [Nat.choose_symm hx', Nat.cast_sub hx']
    ring
  linarith

theorem binHalf_sum (n : ℕ) : ∑ x ∈ range (n + 1), binHalf n x = 1 := by
  unfold binHalf
  rw [← Finset.sum_div, ← Nat.cast_sum, Nat.sum_range_choose]
  push_cast
  exact div_self (by positivity)

/-- Vandermonde in the form used here: the sum of `X₁ + X₂` over two independent `Bin(n, ·)`
weights is the `Bin(2n, ·)` weight. -/
theorem double_sum_choose (n : ℕ) (g : ℕ → ℝ) :
    ∑ x ∈ range (n + 1), ∑ y ∈ range (n + 1), (n.choose x : ℝ) * (n.choose y : ℝ) * g (x + y) =
      ∑ s ∈ range (2 * n + 1), ((2 * n).choose s : ℝ) * g s := by
  have hV : ∀ s, ((2 * n).choose s : ℝ) * g s =
      ∑ k ∈ range (s + 1), (n.choose k : ℝ) * (n.choose (s - k) : ℝ) * g (k + (s - k)) := by
    intro s
    rw [show 2 * n = n + n by ring, Nat.add_choose_eq, Nat.cast_sum, Finset.sum_mul,
      Finset.Nat.sum_antidiagonal_eq_sum_range_succ_mk]
    apply Finset.sum_congr rfl
    intro k hk
    rw [mem_range] at hk
    push_cast
    rw [show k + (s - k) = s by omega]
  simp_rw [hV]
  rw [Finset.sum_range_diag_flip (2 * n + 1)
    (fun k j => (n.choose k : ℝ) * (n.choose j : ℝ) * g (k + j))]
  symm
  rw [← Finset.sum_subset (range_subset_range.mpr (by omega : n + 1 ≤ 2 * n + 1))]
  · apply Finset.sum_congr rfl
    intro k hk
    rw [mem_range] at hk
    symm
    apply Finset.sum_subset (range_subset_range.mpr (by omega))
    intro j _ hj
    rw [mem_range] at hj
    rw [Nat.choose_eq_zero_of_lt (by omega : n < j)]
    simp
  · intro k _ hk
    rw [mem_range] at hk
    apply Finset.sum_eq_zero
    intro j _
    rw [Nat.choose_eq_zero_of_lt (by omega : n < k)]
    simp

/-- **`M_n(2) = ½ E|S - n|`** with `S ~ Bin(2n, ½)`: `max(X₁, X₂) = (X₁ + X₂)/2 + |X₁ - X₂|/2` and
`X₁ - X₂ + n = X₁ + (n - X₂) ~ Bin(2n, ½)`. -/
theorem M2_eq_half_meanAbsDev (n : ℕ) : M2 n = meanAbsDev n / 2 := by
  have hmax : ∀ u v : ℝ, max u v = (u + v) / 2 + |u - v| / 2 := by
    intro u v
    rcases le_total u v with h | h
    · rw [max_eq_right h, abs_of_nonpos (by linarith)]; ring
    · rw [max_eq_left h, abs_of_nonneg (by linarith)]; ring
  -- split `M2` into the centred-sum part and the absolute-difference part
  have hsplit : M2 n =
      (∑ x ∈ range (n + 1), ∑ y ∈ range (n + 1),
          binHalf n x * binHalf n y * (((x : ℝ) - n / 2) + ((y : ℝ) - n / 2))) / 2 +
        (∑ x ∈ range (n + 1), ∑ y ∈ range (n + 1),
          binHalf n x * binHalf n y * |(x : ℝ) - y|) / 2 := by
    unfold M2
    rw [Finset.sum_div, Finset.sum_div, ← Finset.sum_add_distrib]
    apply Finset.sum_congr rfl
    intro x _
    rw [Finset.sum_div, Finset.sum_div, ← Finset.sum_add_distrib]
    apply Finset.sum_congr rfl
    intro y _
    rw [hmax]
    ring
  have hcentred : ∑ x ∈ range (n + 1), ∑ y ∈ range (n + 1),
      binHalf n x * binHalf n y * (((x : ℝ) - n / 2) + ((y : ℝ) - n / 2)) = 0 := by
    have : ∀ x y, binHalf n x * binHalf n y * (((x : ℝ) - n / 2) + ((y : ℝ) - n / 2)) =
        binHalf n y * (binHalf n x * ((x : ℝ) - n / 2)) +
          binHalf n x * (binHalf n y * ((y : ℝ) - n / 2)) := by
      intro x y; ring
    have h1 : ∀ x : ℕ, ∑ y ∈ range (n + 1), binHalf n y * (binHalf n x * ((x : ℝ) - n / 2)) =
        binHalf n x * ((x : ℝ) - n / 2) := by
      intro x; rw [← Finset.sum_mul, binHalf_sum, one_mul]
    have h2 : ∀ x : ℕ, ∑ y ∈ range (n + 1), binHalf n x * (binHalf n y * ((y : ℝ) - n / 2)) =
        0 := by
      intro x; rw [← Finset.mul_sum, binHalf_sum_centered, mul_zero]
    simp_rw [this, Finset.sum_add_distrib, h1, h2, binHalf_sum_centered]
    simp
  -- reflect `y ↦ n - y` and apply Vandermonde
  have habs : ∑ x ∈ range (n + 1), ∑ y ∈ range (n + 1), binHalf n x * binHalf n y * |(x : ℝ) - y|
      = meanAbsDev n := by
    have hrefl : ∀ x, ∑ y ∈ range (n + 1), binHalf n x * binHalf n y * |(x : ℝ) - y| =
        ∑ y ∈ range (n + 1), binHalf n x * binHalf n y * |((x + y : ℕ) : ℝ) - n| := by
      intro x
      rw [← Finset.sum_range_reflect _ (n + 1)]
      apply Finset.sum_congr rfl
      intro y hy
      rw [mem_range] at hy
      have hy' : y ≤ n := by omega
      rw [show n + 1 - 1 - y = n - y by omega]
      unfold binHalf
      rw [Nat.choose_symm hy', Nat.cast_sub hy']
      push_cast
      congr 1
      rw [show (x : ℝ) - (n - y) = x + y - n by ring]
    simp_rw [hrefl]
    unfold meanAbsDev binHalf
    have h4 : (2 : ℝ) ^ (2 * n) = 2 ^ n * 2 ^ n := by rw [two_mul, pow_add]
    rw [h4]
    have := double_sum_choose n (fun s => |(s : ℝ) - n| / (2 ^ n * 2 ^ n))
    convert this using 1
    · apply Finset.sum_congr rfl; intro x _
      apply Finset.sum_congr rfl; intro y _
      field_simp
    · apply Finset.sum_congr rfl; intro s _
      field_simp
  rw [hsplit, hcentred, habs]
  ring

/-! ## The closed form and the step ratio -/

/-- `M_n(2) = n C(2n, n)/(2·4ⁿ)`. -/
theorem M2_eq (n : ℕ) : M2 n = n * ((2 * n).choose n : ℝ) / (2 * 4 ^ n) := by
  rw [M2_eq_half_meanAbsDev, meanAbsDev_eq]
  field_simp

theorem M2_nonneg (n : ℕ) : 0 ≤ M2 n := by
  rw [M2_eq]; positivity

/-- **Theorem (`K = 2`), closed form:** `a_n(2)² = n C(2n, n)²/(4·16ⁿ)`. -/
theorem aSq_eq (n : ℕ) : aSq n = n * ((2 * n).choose n : ℝ) ^ 2 / (4 * 16 ^ n) := by
  unfold aSq
  rw [M2_eq]
  rcases Nat.eq_zero_or_pos n with rfl | hn
  · simp
  · have hn' : (n : ℝ) ≠ 0 := by positivity
    have h16 : (16 : ℝ) ^ n = 4 ^ n * 4 ^ n := by rw [← mul_pow]; norm_num
    rw [h16]
    field_simp
    ring

theorem aSq_pos {n : ℕ} (hn : 1 ≤ n) : 0 < aSq n := by
  rw [aSq_eq]
  have : 0 < (2 * n).choose n := Nat.choose_pos (by omega)
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  positivity

/-- **Theorem (`K = 2`), step ratio:**
`a_{n+1}(2)²/a_n(2)² = (2n + 1)²/(4n(n + 1))` for `n ≥ 1`. -/
theorem aSq_succ_div {n : ℕ} (hn : 1 ≤ n) :
    aSq (n + 1) / aSq n = (2 * n + 1) ^ 2 / (4 * n * (n + 1)) := by
  have hc := Nat.succ_mul_centralBinom_succ n
  rw [Nat.centralBinom_eq_two_mul_choose, Nat.centralBinom_eq_two_mul_choose] at hc
  have hc' : ((n : ℝ) + 1) * ((2 * (n + 1)).choose (n + 1) : ℝ) =
      2 * (2 * n + 1) * ((2 * n).choose n : ℝ) := by exact_mod_cast hc
  have hpos : 0 < (2 * n).choose n := Nat.choose_pos (by omega)
  have hpos' : (0 : ℝ) < ((2 * n).choose n : ℝ) := by exact_mod_cast hpos
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  have hC : ((2 * (n + 1)).choose (n + 1) : ℝ) =
      2 * (2 * n + 1) * ((2 * n).choose n : ℝ) / ((n : ℝ) + 1) := by
    rw [← hc']; field_simp
  rw [aSq_eq, aSq_eq, hC]
  push_cast
  rw [pow_succ]
  field_simp
  ring

/-- The step ratio exceeds one: `(2n + 1)²/(4n(n + 1)) = 1 + 1/(4n(n + 1)) > 1`. -/
theorem step_ratio_eq {n : ℕ} (hn : 1 ≤ n) :
    ((2 * n + 1 : ℝ)) ^ 2 / (4 * n * (n + 1)) = 1 + 1 / (4 * n * (n + 1)) := by
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  field_simp
  ring

theorem step_ratio_gt_one {n : ℕ} (hn : 1 ≤ n) :
    1 < ((2 * n + 1 : ℝ)) ^ 2 / (4 * n * (n + 1)) := by
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  rw [step_ratio_eq hn]
  have : 0 < 1 / (4 * (n : ℝ) * (n + 1)) := by positivity
  linarith

/-- `a_n(2)²` increases strictly in `n ≥ 1`. -/
theorem aSq_lt_succ {n : ℕ} (hn : 1 ≤ n) : aSq n < aSq (n + 1) := by
  have h := aSq_succ_div hn
  have hpos := aSq_pos hn
  have hgt := step_ratio_gt_one hn
  rw [← h, lt_div_iff₀ hpos] at hgt
  linarith

theorem a_eq_sqrt (n : ℕ) : a n = √(aSq n) := by
  unfold a aSq
  rw [Real.sqrt_div' _ (Nat.cast_nonneg n), Real.sqrt_sq (M2_nonneg n)]

/-- **Theorem (`K = 2`), monotone approach:** `a_n(2)` increases strictly in `n ≥ 1`. -/
theorem a_lt_succ {n : ℕ} (hn : 1 ≤ n) : a n < a (n + 1) := by
  rw [a_eq_sqrt, a_eq_sqrt]
  exact Real.sqrt_lt_sqrt (aSq_pos hn).le (aSq_lt_succ hn)

theorem a_strictMonoOn : StrictMonoOn a (Set.Ici 1) := by
  intro i hi j hj hij
  simp only [Set.mem_Ici] at hi hj
  induction j, hij using Nat.le_induction with
  | base => exact a_lt_succ hi
  | succ j hj' ih => exact (ih (by omega)).trans (a_lt_succ (by omega))

/-! ## The limit `a_n(2) → 1/(2√π)` (Wallis) -/

/-- `a_n(2)² = n/(4(2n + 1) W_n)` with `W_n` Mathlib's Wallis partial product. -/
theorem aSq_eq_wallis (n : ℕ) : aSq n = n / (4 * (2 * n + 1) * Real.Wallis.W n) := by
  rw [aSq_eq, Real.Wallis.W_eq_factorial_ratio]
  have hf := Nat.add_choose_mul_factorial_mul_factorial n n
  rw [show n + n = 2 * n by ring] at hf
  have hf' : ((2 * n).choose n : ℝ) * (n.factorial : ℝ) * (n.factorial : ℝ) =
      ((2 * n).factorial : ℝ) := by exact_mod_cast hf
  have hfac : (0 : ℝ) < (n.factorial : ℝ) := by exact_mod_cast Nat.factorial_pos n
  rw [← hf']
  have h16 : (2 : ℝ) ^ (4 * n) = 16 ^ n := by rw [pow_mul]; norm_num
  rw [h16]
  rcases Nat.eq_zero_or_pos n with rfl | hn
  · simp
  · have hC : (0 : ℝ) < ((2 * n).choose n : ℝ) := by exact_mod_cast Nat.choose_pos (by omega)
    field_simp

/-- **Theorem (`K = 2`), limit:** `a_n(2)² → 1/(4π)`. -/
theorem tendsto_aSq : Tendsto aSq atTop (𝓝 (1 / (4 * π))) := by
  have hW := Real.Wallis.tendsto_W_nhds_pi_div_two
  have hfrac : Tendsto (fun n : ℕ => (n : ℝ) / (2 * n + 1)) atTop (𝓝 (1 / 2)) := by
    have h : ∀ n : ℕ, (n : ℝ) / (2 * n + 1) = 1 / 2 - (1 / 2) / (2 * n + 1) := by
      intro n
      have : (0 : ℝ) < 2 * n + 1 := by positivity
      field_simp
      ring
    simp_rw [h]
    have : Tendsto (fun n : ℕ => (1 / 2 : ℝ) / (2 * n + 1)) atTop (𝓝 0) := by
      apply tendsto_const_nhds.div_atTop
      apply Tendsto.atTop_add _ tendsto_const_nhds
      exact tendsto_natCast_atTop_atTop.const_mul_atTop two_pos
    simpa using (tendsto_const_nhds (x := (1 / 2 : ℝ))).sub this
  have hlim := hfrac.div (hW.const_mul 4) (by positivity)
  have heq : (1 / 2 : ℝ) / (4 * (π / 2)) = 1 / (4 * π) := by
    field_simp
  rw [heq] at hlim
  refine hlim.congr fun n => ?_
  rw [Pi.div_apply, aSq_eq_wallis, div_div]
  ring

/-- **Theorem (`K = 2`), limit:** `a_n(2) → 1/(2√π)`, approached strictly from below
(`a_strictMonoOn`). -/
theorem tendsto_a : Tendsto a atTop (𝓝 (1 / (2 * √π))) := by
  have h := tendsto_aSq.sqrt
  have heq : √(1 / (4 * π)) = 1 / (2 * √π) := by
    rw [Real.sqrt_div' _ (by positivity), Real.sqrt_one, Real.sqrt_mul' _ pi_pos.le]
    norm_num
  rw [heq] at h
  exact h.congr fun n => (a_eq_sqrt n).symm

/-! ## The KL-normalized ratio `r(n, 2, ½)` -/

/-- `λ₂ = ln 2 - 1/2`. -/
noncomputable def lam2 : ℝ := log 2 - 1 / 2

theorem lam2_pos : 0 < lam2 := by
  unfold lam2
  have := Real.log_two_gt_d9
  norm_num at this ⊢
  linarith

/-- `r(n, 2, ½) = γ(n, 2, ½)/(σ_n √(2λ₂)) = 2 a_n(2)/√(2λ₂)` (note §4, D.5, with `σ_n = 1/(2√n)`). -/
noncomputable def r (n : ℕ) : ℝ := 2 * a n / √(2 * lam2)

/-- `r(n, 2, ½)` increases strictly in `n ≥ 1`. -/
theorem r_strictMonoOn : StrictMonoOn r (Set.Ici 1) := by
  intro i hi j hj hij
  unfold r
  have hpos : 0 < √(2 * lam2) := Real.sqrt_pos.mpr (by linarith [lam2_pos])
  rw [div_lt_div_iff_of_pos_right hpos]
  linarith [a_strictMonoOn hi hj hij]

/-- `r(n, 2, ½) → 1/(√π √(2λ₂))`, which is `c₂ = E[M₂]/√(2λ₂)` once `E[M₂] = 1/√π` (the Gaussian
value, not formalized here). -/
theorem tendsto_r : Tendsto r atTop (𝓝 (1 / (√π * √(2 * lam2)))) := by
  have h := (tendsto_a.const_mul 2).div_const (√(2 * lam2))
  have heq : 2 * (1 / (2 * √π)) / √(2 * lam2) = 1 / (√π * √(2 * lam2)) := by
    have : 0 < √π := Real.sqrt_pos.mpr pi_pos
    have : 0 < √(2 * lam2) := Real.sqrt_pos.mpr (by linarith [lam2_pos])
    field_simp
  rw [heq] at h
  exact h

/-- The supremum over `n` of `r(n, 2, ½)` is the limit and is not attained. -/
theorem r_lt_lim {n : ℕ} (hn : 1 ≤ n) : r n < 1 / (√π * √(2 * lam2)) := by
  have h1 := r_strictMonoOn (Set.mem_Ici.mpr hn) (Set.mem_Ici.mpr (by omega : 1 ≤ n + 1))
    (Nat.lt_succ_self n)
  have h2 : r (n + 1) ≤ 1 / (√π * √(2 * lam2)) := by
    apply ge_of_tendsto tendsto_r
    rw [Filter.eventually_atTop]
    exact ⟨n + 1, fun k hk => r_strictMonoOn.monotoneOn (Set.mem_Ici.mpr (by omega))
      (Set.mem_Ici.mpr (by omega)) hk⟩
  linarith

end FeedbackChannel.SelectionKTwo

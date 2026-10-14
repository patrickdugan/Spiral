import FeedbackChannel.MultigenRunningMax
import Mathlib.Probability.Moments.SubGaussian
import Mathlib.Probability.ProbabilityMassFunction.Integrals
import Mathlib.Analysis.Convex.SpecificFunctions.Basic

/-!
# The Hoeffding bound on the running-maximum gap (multigen note, Proposition 5, first bound)

Source: `paper/evaluation_feedback_multigen.md`, draft 0.5, §2, Proposition 5; code
`src/spiral_ln/evaluation_feedback_multigen.py` (`naive_gap_bounds`).

**Proposition 5 (first bound).** For every `n ≥ 1`, `K`, `p ∈ [0, 1]` and `G`, with `m = G K + 1`,
the naive readout gap satisfies `ρ_G ≤ √(ln m/(2n))`.

*Proof (as in the note).* `Y_i = X_i - np` is a sum of `n` centred Bernoullis; Hoeffding's lemma
(Mathlib's `ProbabilityTheory.hasSubgaussianMGF_of_mem_Icc`) and independence give
`E e^{λ Y_i} ≤ e^{λ² n/8}` (`binomial_mgf_le`); the maximal inequality
`E max_i Y_i ≤ λ⁻¹ ln ∑_i E e^{λ Y_i}` (Jensen, then `max ≤ ∑`; `maximal_inequality`) gives
`(ln m)/λ + λ n/8`, which `λ = √(8 ln m/n)` makes `√(n ln m/2)`; divide by `n`.

The draws are the `G K + 1` i.i.d. `Bin(n, p)` counts of `MultigenRunningMax` (product law over
`Draw G K`). The second (Bernstein) bound of Proposition 5 is not formalized.
-/

namespace FeedbackChannel.MultigenHoeffding

open Finset Real MeasureTheory ProbabilityTheory FeedbackChannel.MultigenRunningMax
open scoped NNReal

/-! ## Hoeffding's lemma for one Bernoulli, from Mathlib -/

/-- **Hoeffding's lemma** for `B ~ Bernoulli(p)`: `E e^{t(B - p)} ≤ e^{t²/8}`, obtained from
Mathlib's sub-Gaussian form of Hoeffding's lemma on the two-point law. -/
theorem bernoulli_hoeffding {p : ℝ} (hp0 : 0 ≤ p) (hp1 : p ≤ 1) (t : ℝ) :
    p * exp (t * (1 - p)) + (1 - p) * exp (t * (0 - p)) ≤ exp (t ^ 2 / 8) := by
  set q : ℝ≥0 := p.toNNReal with hqdef
  have hq : q ≤ 1 := Real.toNNReal_le_one.mpr hp1
  have hqp : (q : ℝ) = p := Real.coe_toNNReal p hp0
  set μ : Measure Bool := (PMF.bernoulli q hq).toMeasure with hμ
  let X : Bool → ℝ := fun b => if b then 1 else 0
  have hX : AEMeasurable X μ := (measurable_of_countable X).aemeasurable
  have hb : ∀ᵐ b ∂μ, X b ∈ Set.Icc (0 : ℝ) 1 :=
    Filter.Eventually.of_forall fun b => by cases b <;> simp [X]
  have hsg := hasSubgaussianMGF_of_mem_Icc hX hb
  have hle := hsg.mgf_le t
  have hint : ∀ f : Bool → ℝ, ∫ b, f b ∂μ = p * f true + (1 - p) * f false := by
    intro f
    rw [hμ, PMF.integral_eq_sum]
    simp only [Fintype.univ_bool, Finset.mem_singleton, Bool.true_eq_false, not_false_eq_true,
      Finset.sum_insert, Finset.sum_singleton, PMF.bernoulli_apply, Bool.cond_true, Bool.cond_false,
      smul_eq_mul]
    rw [ENNReal.coe_toReal, ENNReal.coe_toReal, NNReal.coe_sub hq, hqp, NNReal.coe_one]
  have hmean : ∫ b, X b ∂μ = p := by rw [hint]; simp [X]
  unfold mgf at hle
  rw [hint, hmean] at hle
  simp only [X, ite_true, Bool.false_eq_true, ite_false] at hle
  have hc : (((‖(1 : ℝ) - 0‖₊ / 2) ^ 2 : ℝ≥0) : ℝ) = 1 / 4 := by
    simp
    norm_num
  rw [hc] at hle
  calc p * exp (t * (1 - p)) + (1 - p) * exp (t * (0 - p)) ≤ exp (1 / 4 * t ^ 2 / 2) := hle
    _ = exp (t ^ 2 / 8) := by ring_nf

/-! ## The binomial mgf -/

/-- `E e^{t(X - np)} = (p e^{t(1-p)} + (1-p) e^{-tp})^n` for `X ~ Bin(n, p)`. -/
theorem binomial_mgf (n : ℕ) (p t : ℝ) :
    ∑ x : Fin (n + 1), binomial n p x * exp (t * ((x : ℝ) - n * p)) =
      (p * exp (t * (1 - p)) + (1 - p) * exp (t * (0 - p))) ^ n := by
  rw [add_pow, ← Fin.sum_univ_eq_sum_range]
  apply Finset.sum_congr rfl
  intro x _
  have hx : x.val ≤ n := Nat.lt_succ_iff.mp x.isLt
  unfold binomial
  rw [mul_pow, mul_pow, ← Real.exp_nat_mul, ← Real.exp_nat_mul, Nat.cast_sub hx]
  have : rexp (t * ((x : ℝ) - n * p)) =
      rexp (x * (t * (1 - p))) * rexp (((n : ℝ) - x) * (t * (0 - p))) := by
    rw [← Real.exp_add]; congr 1; ring
  rw [this]
  ring

/-- **Hoeffding for one count:** `E e^{t(X - np)} ≤ e^{n t²/8}` for `X ~ Bin(n, p)`. -/
theorem binomial_mgf_le (n : ℕ) {p : ℝ} (hp0 : 0 ≤ p) (hp1 : p ≤ 1) (t : ℝ) :
    ∑ x : Fin (n + 1), binomial n p x * exp (t * ((x : ℝ) - n * p)) ≤ exp (n * t ^ 2 / 8) := by
  rw [binomial_mgf]
  have h := bernoulli_hoeffding hp0 hp1 t
  have h0 : 0 ≤ p * exp (t * (1 - p)) + (1 - p) * exp (t * (0 - p)) := by
    have : 0 ≤ 1 - p := by linarith
    positivity
  calc (p * exp (t * (1 - p)) + (1 - p) * exp (t * (0 - p))) ^ n ≤ exp (t ^ 2 / 8) ^ n :=
        pow_le_pow_left₀ h0 h n
    _ = exp (n * t ^ 2 / 8) := by rw [← Real.exp_nat_mul]; ring_nf

/-! ## Marginals and the maximal inequality -/

section Max

variable {n : ℕ} (w : Fin (n + 1) → ℝ)

/-- One coordinate of i.i.d. draws has law `w`. -/
theorem expect_coord {ι : Type*} [Fintype ι] [DecidableEq ι] (hw : ∑ x, w x = 1) (i : ι)
    (f : Fin (n + 1) → ℝ) :
    MultigenRunningMax.expect w (fun D : ι → Fin (n + 1) => f (D i)) = ∑ x, w x * f x := by
  unfold MultigenRunningMax.expect
  have hprod : ∀ D : ι → Fin (n + 1), (∏ j, w (D j)) * f (D i) =
      ∏ j, (if j = i then w (D j) * f (D j) else w (D j)) := by
    intro D
    have : ∀ j, (if j = i then w (D j) * f (D j) else w (D j)) =
        w (D j) * (if j = i then f (D j) else 1) := by
      intro j; split_ifs <;> ring
    simp_rw [this, Finset.prod_mul_distrib, Finset.prod_ite_eq', ite_eq_left (mem_univ i)]
  simp_rw [hprod]
  have h := Finset.prod_univ_sum (fun _ : ι => (univ : Finset (Fin (n + 1))))
    (fun j x => if j = i then w x * f x else w x)
  rw [Fintype.piFinset_univ] at h
  rw [← h, Finset.prod_eq_single i]
  · simp
  · intro j _ hj
    simp [hj, hw]
  · intro h'; exact absurd (mem_univ i) h'

/-- **The maximal inequality** (Jensen, then `max ≤ ∑`): for every real `λ` and `m ≥ 1` i.i.d. draws,
`λ (E[max_i X_i] - c) ≤ ln m + ln E e^{λ (X - c)}`. -/
theorem maximal_inequality {ι : Type*} [Fintype ι] [DecidableEq ι] [Nonempty ι]
    (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (c lam : ℝ) :
    lam * (MultigenRunningMax.expect w (fun D : ι → Fin (n + 1) => (maxDraw D : ℝ)) - c) ≤
      log (Fintype.card ι) + log (∑ x, w x * exp (lam * ((x : ℝ) - c))) := by
  set E := MultigenRunningMax.expect w (fun D : ι → Fin (n + 1) => (maxDraw D : ℝ))
  have hmass := total_mass w hw (ι := ι)
  have hweights : ∀ D : ι → Fin (n + 1), 0 ≤ ∏ i, w (D i) :=
    fun D => Finset.prod_nonneg fun i _ => hw0 _
  -- Jensen for `exp`
  have hJ : exp (lam * (E - c)) ≤
      ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * exp (lam * ((maxDraw D : ℝ) - c)) := by
    have hE : lam * (E - c) = ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) *
        (lam * ((maxDraw D : ℝ) - c)) := by
      simp only [E, MultigenRunningMax.expect]
      rw [mul_sub, Finset.mul_sum]
      have : lam * c = ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * (lam * c) := by
        rw [← Finset.sum_mul, hmass, one_mul]
      rw [this, ← Finset.sum_sub_distrib]
      apply Finset.sum_congr rfl; intro D _; ring
    rw [hE]
    have := convexOn_exp.map_sum_le (t := univ) (w := fun D : ι → Fin (n + 1) => ∏ i, w (D i))
      (p := fun D => lam * ((maxDraw D : ℝ) - c)) (fun D _ => hweights D) hmass
      (fun D _ => Set.mem_univ _)
    simpa [smul_eq_mul] using this
  -- `exp(λ max) ≤ ∑_i exp(λ Y_i)`
  have hmax : ∀ D : ι → Fin (n + 1), exp (lam * ((maxDraw D : ℝ) - c)) ≤
      ∑ i, exp (lam * (((D i : ℕ) : ℝ) - c)) := by
    intro D
    obtain ⟨i, _, hi⟩ := Finset.exists_mem_eq_sup (univ : Finset ι) univ_nonempty
      (fun i => (D i).val)
    have : (maxDraw D : ℝ) = ((D i : ℕ) : ℝ) := by rw [maxDraw, hi]
    rw [this]
    exact Finset.single_le_sum (f := fun i => exp (lam * (((D i : ℕ) : ℝ) - c)))
      (fun j _ => (exp_pos _).le) (mem_univ i)
  have hsum : ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * exp (lam * ((maxDraw D : ℝ) - c)) ≤
      Fintype.card ι * ∑ x, w x * exp (lam * ((x : ℝ) - c)) := by
    calc ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * exp (lam * ((maxDraw D : ℝ) - c))
        ≤ ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * ∑ i, exp (lam * (((D i : ℕ) : ℝ) - c)) :=
          Finset.sum_le_sum fun D _ => mul_le_mul_of_nonneg_left (hmax D) (hweights D)
      _ = ∑ i : ι, MultigenRunningMax.expect w (fun D : ι → Fin (n + 1) => exp (lam * (((D i : ℕ) : ℝ) - c))) := by
          unfold MultigenRunningMax.expect
          simp_rw [Finset.mul_sum]
          rw [Finset.sum_comm]
      _ = ∑ _i : ι, ∑ x, w x * exp (lam * ((x : ℝ) - c)) := by
          apply Finset.sum_congr rfl
          intro i _
          exact expect_coord w hw i (fun x => exp (lam * ((x : ℝ) - c)))
      _ = Fintype.card ι * ∑ x, w x * exp (lam * ((x : ℝ) - c)) := by
          rw [Finset.sum_const, Finset.card_univ, nsmul_eq_mul]
  have hpos : 0 < ∑ x, w x * exp (lam * ((x : ℝ) - c)) := by
    obtain ⟨x, hx⟩ : ∃ x, 0 < w x := by
      by_contra h
      have : ∑ x, w x ≤ 0 := Finset.sum_nonpos fun x _ => not_lt.mp fun hx => h ⟨x, hx⟩
      linarith
    exact lt_of_lt_of_le (mul_pos hx (exp_pos _))
      (Finset.single_le_sum (f := fun x => w x * exp (lam * ((x : ℝ) - c)))
        (fun y _ => mul_nonneg (hw0 y) (exp_pos _).le) (mem_univ x))
  have hcard : (0 : ℝ) < Fintype.card ι := by exact_mod_cast Fintype.card_pos (α := ι)
  have := hJ.trans hsum
  rw [← Real.log_mul hcard.ne' hpos.ne']
  rw [← Real.log_exp (lam * (E - c))]
  exact Real.log_le_log (exp_pos _) this

/-- **Proposition 5 (Hoeffding), for the maximum of `m` i.i.d. `Bin(n, p)` draws:**
`E[max_i X_i]/n - p ≤ √(ln m/(2n))`. -/
theorem max_gap_le_hoeffding (hn : 1 ≤ n) {p : ℝ} (hp0 : 0 ≤ p) (hp1 : p ≤ 1)
    {ι : Type*} [Fintype ι] [DecidableEq ι] [Nonempty ι] :
    MultigenRunningMax.expect (binomial n p) (fun D : ι → Fin (n + 1) => (maxDraw D : ℝ)) / n - p ≤
      √(log (Fintype.card ι) / (2 * n)) := by
  set E := MultigenRunningMax.expect (binomial n p) (fun D : ι → Fin (n + 1) => (maxDraw D : ℝ))
  set L := log (Fintype.card ι)
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  have hL : 0 ≤ L := Real.log_nonneg (by exact_mod_cast Fintype.card_pos (α := ι))
  -- the bound for every `λ > 0`
  have hbound : ∀ lam : ℝ, 0 < lam → lam * (E - n * p) ≤ L + n * lam ^ 2 / 8 := by
    intro lam hlam
    have h1 := maximal_inequality (ι := ι) (binomial n p) (binomial_nonneg n hp0 hp1)
      (binomial_sum n p) (n * p) lam
    have h2 : log (∑ x : Fin (n + 1), binomial n p x * exp (lam * ((x : ℝ) - n * p))) ≤
        n * lam ^ 2 / 8 := by
      have hpos : 0 < ∑ x : Fin (n + 1), binomial n p x * exp (lam * ((x : ℝ) - n * p)) := by
        rw [binomial_mgf]
        have : 0 < p * exp (lam * (1 - p)) + (1 - p) * exp (lam * (0 - p)) := by
          rcases eq_or_lt_of_le hp0 with h | h
          · rw [← h]; simp
          · have : 0 ≤ 1 - p := by linarith
            have := exp_pos (lam * (1 - p))
            have := exp_pos (lam * (0 - p))
            positivity
        positivity
      calc log _ ≤ log (exp (n * lam ^ 2 / 8)) :=
            Real.log_le_log hpos (binomial_mgf_le n hp0 hp1 lam)
        _ = n * lam ^ 2 / 8 := Real.log_exp _
    linarith
  -- optimize over `λ`
  have hgap : E - n * p ≤ √(n * L / 2) := by
    rcases eq_or_lt_of_le hL with hL0 | hLpos
    · rw [← hL0, mul_zero, zero_div, Real.sqrt_zero]
      by_contra hcon
      have hpos : 0 < E - n * p := lt_of_not_ge hcon
      have := hbound (4 * (E - n * p) / n) (by positivity)
      rw [← hL0] at this
      field_simp at this
      nlinarith
    · set r := √(n * L / 8) with hr
      have hrpos : 0 < r := Real.sqrt_pos.mpr (by positivity)
      have hr2 : r ^ 2 = n * L / 8 := Real.sq_sqrt (by positivity)
      have := hbound (8 * r / n) (by positivity)
      have hsq : √(n * L / 2) = 2 * r := by
        rw [hr, show n * L / 2 = 2 ^ 2 * (n * L / 8) by ring, Real.sqrt_mul' _ (by positivity),
          Real.sqrt_sq (by norm_num)]
      rw [hsq]
      have h8 : 8 * r / n * (E - n * p) ≤ L + n * (8 * r / n) ^ 2 / 8 := this
      have hL' : L = 8 * r ^ 2 / n := by rw [hr2]; field_simp
      rw [hL'] at h8
      have : 8 * r / n * (E - n * p) ≤ 8 * r / n * (2 * r) := by
        have : L + n * (8 * r / n) ^ 2 / 8 = 8 * r / n * (2 * r) := by
          rw [hL']; field_simp; ring
        rw [hL'] at this
        linarith
      exact le_of_mul_le_mul_left this (by positivity)
  -- divide by `n`
  have hsqrt : √(L / (2 * n)) = √(n * L / 2) / n := by
    have h : √(n * L / 2) = √(L / (2 * n)) * n := by
      rw [show (n : ℝ) * L / 2 = (L / (2 * n)) * (n : ℝ) ^ 2 by field_simp,
        Real.sqrt_mul' _ (by positivity), Real.sqrt_sq hn'.le]
    rw [h]
    field_simp
  rw [hsqrt, div_sub' hn'.ne', div_le_div_iff_of_pos_right hn']
  linarith

end Max

/-- **Proposition 5 (Hoeffding bound), for the chain:** under naive reuse with `G` generations of
`K` candidates on `n ≥ 1` items and i.i.d. `Bin(n, p)` counts, the readout gap
`ρ_G = E[c_G]/n - p` satisfies `ρ_G ≤ √(ln(G K + 1)/(2n))`. -/
theorem prop5_hoeffding {n : ℕ} (hn : 1 ≤ n) {p : ℝ} (hp0 : 0 ≤ p) (hp1 : p ≤ 1) (G K : ℕ) :
    MultigenRunningMax.expect (binomial n p) (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) / n - p ≤
      √(log ((G * K + 1 : ℕ) : ℝ) / (2 * n)) := by
  have h := max_gap_le_hoeffding hn hp0 hp1 (ι := Draw G K)
  rw [card_draw] at h
  have : MultigenRunningMax.expect (binomial n p) (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) =
      MultigenRunningMax.expect (binomial n p) (fun D : Draw G K → Fin (n + 1) => (maxDraw D : ℝ)) := by
    unfold MultigenRunningMax.expect
    simp only [reported_eq_maxDraw]
  rw [this]
  exact h

end FeedbackChannel.MultigenHoeffding

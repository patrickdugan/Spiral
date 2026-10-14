import Mathlib.Tactic
import Mathlib.Analysis.SpecialFunctions.Log.NegMulLog
import Mathlib.Analysis.Calculus.Deriv.MeanValue

/-!
# Theorem B: best-of-`K` stays inside the KL ball of radius `ln K - (K - 1)/K`

Source: `paper/selection_law_kl_containment.md`, draft 0.3, §0 and §2; code
`src/spiral_ln/evaluation_selection_kl.py`.

Setting (§0): finite `Ω`, base law `p₀`, score `S : Ω → ℝ`; `q(s) = P₀(S = s)`, `F(s) = P₀(S ≤ s)`,
`F(s-) = P₀(S < s)`, `m_K(s) = F(s)^K - F(s-)^K` (law of the maximum of `K` scores);
`λ_K = ln K - (K - 1)/K`. By Theorem A (formalized in `SelectionTieRules`) the kept record of every
tie rule has law `π_K(ω) = p₀(ω) m_K(S ω)/q(S ω)`.

**Theorem B.** `KL(π_K ‖ p₀) ≤ λ_K` for every finite `p₀`, score and `K ≥ 1`, with equality iff
`K = 1`.

The note's proof jitters the scores to a tie-free continuous law, where the KL is exactly
`∫₀¹ K u^{K-1} ln(K u^{K-1}) du = λ_K`, and removes the jitter by Jensen. Here the Jensen step is
done atom by atom without measure theory: on an atom with `F(s-) = a < b = F(s)`,
`m_K(s)/q(s)` is the average of `h(u) = K u^{K-1}` over `[a, b]`, and the tangent-line form of
Jensen's inequality for `φ(y) = y ln y` gives
`(b^K - a^K) ln((b^K - a^K)/(b - a)) ≤ G(b) - G(a)` (`atom_le`), where
`G(x) = x^K (ln K + (K - 1) ln x) - (K - 1) x^K/K` is an antiderivative of `h ln h` on `(0, ∞)`
(`hasDerivAt_G`). Summing over atoms telescopes to `G(1) - G(0) = λ_K` (`telescope`), which is the
tie-free integral (`G_one`, `G_zero`; the integral itself is `SelectionTieFree.tieFree_integral`).
For `K ≥ 2` the step is strict on every atom of positive mass, because `h` is not constant there
(`atom_lt`), which is the note's strict-convexity argument.

* `atom_le`, `atom_lt`: the per-atom Jensen inequality and its strict form.
* `kl_scores_le`, `kl_scores_lt`: `KL(m_K ‖ q) ≤ λ_K` (`< λ_K` for `K ≥ 2`) for every finite
  score law `q`.
* `theoremB`, `theoremB_strict`, `theoremB_eq_iff`: the same for `KL(π_K ‖ p₀)` with
  `π_K(ω) = p₀(ω) m_K(S ω)/q(S ω)`; equality iff `K = 1`.
* `kl_record_eq_kl_scores`: `KL(π_K ‖ p₀) = KL(m_K ‖ q)` (the last sentence of Theorem A).

Not formalized: the supremum statement (uniform laws on `N` atoms approach `λ_K`) and the
measure-theoretic statement that every atomless score law attains `λ_K`.
-/

namespace FeedbackChannel.SelectionContainment

open Finset Real

/-- `λ_K = ln K - (K - 1)/K`. -/
noncomputable def lam (K : ℕ) : ℝ := log K - (K - 1) / K

/-- An antiderivative of `h ln h`, `h(x) = K x^{K-1}`, on `(0, ∞)`, continuous on `ℝ`:
`G(x) = x^K ln K + (K - 1) x^K ln x - (K - 1) x^K / K`. -/
noncomputable def G (K : ℕ) (x : ℝ) : ℝ :=
  x ^ K * log K + (K - 1) * (x ^ K * log x) - (K - 1) / K * x ^ K

theorem G_zero {K : ℕ} (hK : 1 ≤ K) : G K 0 = 0 := by
  simp [G, zero_pow (by omega : K ≠ 0)]

/-- `G(1) - G(0) = λ_K`: the tie-free value `∫₀¹ K u^{K-1} ln(K u^{K-1}) du`. -/
theorem G_one (K : ℕ) : G K 1 = lam K := by
  simp [G, lam]

theorem continuous_pow_mul_log {K : ℕ} (hK : 1 ≤ K) : Continuous fun x : ℝ => x ^ K * log x := by
  have : (fun x : ℝ => x ^ K * log x) = fun x => x ^ (K - 1) * (x * log x) := by
    funext x
    conv_lhs => rw [show K = (K - 1) + 1 by omega, pow_succ]
    ring
  rw [this]
  exact (continuous_pow _).mul continuous_mul_log

theorem continuous_G {K : ℕ} (hK : 1 ≤ K) : Continuous (G K) := by
  unfold G
  exact (((continuous_pow K).mul continuous_const).add
    (continuous_const.mul (continuous_pow_mul_log hK))).sub
    (continuous_const.mul (continuous_pow K))

/-- `G' = h ln h` with `h(x) = K x^{K-1}`, on `(0, ∞)`. -/
theorem hasDerivAt_G {K : ℕ} (hK : 1 ≤ K) {x : ℝ} (hx : 0 < x) :
    HasDerivAt (G K) (K * x ^ (K - 1) * (log K + (K - 1) * log x)) x := by
  have hp := hasDerivAt_pow K x
  have hl := Real.hasDerivAt_log hx.ne'
  have h := ((hp.mul_const (log K)).add ((hp.mul hl).const_mul ((K : ℝ) - 1))).sub
    (hp.const_mul (((K : ℝ) - 1) / K))
  refine h.congr_deriv ?_
  have hK' : (K : ℝ) ≠ 0 := by
    have : (1 : ℝ) ≤ K := by exact_mod_cast hK
    linarith
  have hxK : x ^ K = x ^ (K - 1) * x := by
    conv_lhs => rw [show K = (K - 1) + 1 by omega, pow_succ]
  rw [hxK]
  field_simp
  ring

/-- `φ(h) ≥ φ(y₀) + φ'(y₀)(h - y₀)` for `φ(y) = y ln y`, `h, y₀ > 0` (tangent line). -/
theorem tangent_mul_log {h y0 : ℝ} (hh : 0 < h) (hy : 0 < y0) :
    y0 * log y0 + (log y0 + 1) * (h - y0) ≤ h * log h := by
  have key := Real.one_sub_inv_le_log_of_pos (div_pos hh hy)
  rw [Real.log_div hh.ne' hy.ne', inv_div] at key
  have : h * (1 - y0 / h) = h - y0 := by field_simp
  nlinarith [mul_le_mul_of_nonneg_left key hh.le]

/-- The tangent-line inequality is strict for `h ≠ y₀` (`φ` strictly convex). -/
theorem tangent_mul_log_strict {h y0 : ℝ} (hh : 0 < h) (hy : 0 < y0) (hne : h ≠ y0) :
    y0 * log y0 + (log y0 + 1) * (h - y0) < h * log h := by
  have hne' : y0 / h ≠ 1 := by
    intro h'
    rw [div_eq_one_iff_eq hh.ne'] at h'
    exact hne h'.symm
  have key := Real.log_lt_sub_one_of_pos (div_pos hy hh) hne'
  rw [Real.log_div hy.ne' hh.ne'] at key
  have : h * (y0 / h - 1) = y0 - h := by field_simp
  nlinarith [mul_lt_mul_of_pos_left key hh]

/-- The comparison function of the tangent-line Jensen step on `[a, b]`:
`D(x) = G(x) - G(a) - (x - a) φ(y₀) - φ'(y₀) ((x^K - a^K) - (x - a) y₀)`. -/
noncomputable def Dfun (K : ℕ) (a y0 x : ℝ) : ℝ :=
  G K x - G K a - (x - a) * (y0 * log y0) - (log y0 + 1) * ((x ^ K - a ^ K) - (x - a) * y0)

/-- `D'(x) = φ(h(x)) - φ(y₀) - φ'(y₀)(h(x) - y₀)`, `h(x) = K x^{K-1}`. -/
noncomputable def Dder (K : ℕ) (y0 x : ℝ) : ℝ :=
  K * x ^ (K - 1) * (log K + (K - 1) * log x) - y0 * log y0 -
    (log y0 + 1) * (K * x ^ (K - 1) - y0)

theorem hasDerivAt_Dfun {K : ℕ} (hK : 1 ≤ K) (a y0 : ℝ) {x : ℝ} (hx : 0 < x) :
    HasDerivAt (Dfun K a y0) (Dder K y0 x) x := by
  have h1 := hasDerivAt_G hK hx
  have h2 := ((hasDerivAt_id x).sub_const a).mul_const (y0 * log y0)
  have h3 := (((hasDerivAt_pow K x).sub_const (a ^ K)).sub
    (((hasDerivAt_id x).sub_const a).mul_const y0)).const_mul (log y0 + 1)
  refine (((h1.sub_const (G K a)).sub h2).sub h3).congr_deriv ?_
  unfold Dder
  ring

theorem log_h {K : ℕ} (hK : 1 ≤ K) {x : ℝ} (hx : 0 < x) :
    log ((K : ℝ) * x ^ (K - 1)) = log K + (K - 1) * log x := by
  have hK0 : (0 : ℝ) < K := by exact_mod_cast hK
  rw [Real.log_mul (by positivity) (by positivity), Real.log_pow]
  push_cast [Nat.cast_sub hK]
  ring

theorem Dder_eq {K : ℕ} (hK : 1 ≤ K) (y0 : ℝ) {x : ℝ} (hx : 0 < x) :
    Dder K y0 x = (K * x ^ (K - 1)) * log (K * x ^ (K - 1)) -
      (y0 * log y0 + (log y0 + 1) * (K * x ^ (K - 1) - y0)) := by
  unfold Dder
  rw [log_h hK hx]
  ring

theorem Dder_nonneg {K : ℕ} (hK : 1 ≤ K) {y0 : ℝ} (hy0 : 0 < y0) {x : ℝ} (hx : 0 < x) :
    0 ≤ Dder K y0 x := by
  rw [Dder_eq hK y0 hx]
  have hK0 : (0 : ℝ) < K := by exact_mod_cast hK
  have hpos : 0 < (K : ℝ) * x ^ (K - 1) := by positivity
  linarith [tangent_mul_log hpos hy0]

theorem Dfun_monotoneOn {K : ℕ} (hK : 1 ≤ K) {a y0 : ℝ} (ha : 0 ≤ a) (hy0 : 0 < y0) (b : ℝ) :
    MonotoneOn (Dfun K a y0) (Set.Icc a b) := by
  apply monotoneOn_of_deriv_nonneg (convex_Icc a b)
  · apply Continuous.continuousOn
    unfold Dfun
    have := continuous_G hK
    fun_prop
  · intro x hx
    rw [interior_Icc] at hx
    exact (hasDerivAt_Dfun hK a y0 (by linarith [hx.1])).differentiableAt.differentiableWithinAt
  · intro x hx
    rw [interior_Icc] at hx
    have hx0 : 0 < x := by linarith [hx.1]
    rw [(hasDerivAt_Dfun hK a y0 hx0).deriv]
    exact Dder_nonneg hK hy0 hx0

theorem Dfun_self (K : ℕ) (a y0 : ℝ) : Dfun K a y0 a = 0 := by
  simp [Dfun]

theorem Dfun_at_b (K : ℕ) {a b : ℝ} (hab : a < b) :
    Dfun K a ((b ^ K - a ^ K) / (b - a)) b =
      G K b - G K a - (b ^ K - a ^ K) * log ((b ^ K - a ^ K) / (b - a)) := by
  have hq : (b - a) * ((b ^ K - a ^ K) / (b - a)) = b ^ K - a ^ K := by
    field_simp [(sub_pos.mpr hab).ne']
  unfold Dfun
  linear_combination hq

/-- **The Jensen step on one atom.** For `0 ≤ a ≤ b` and `K ≥ 1`:
`(b^K - a^K) ln((b^K - a^K)/(b - a)) ≤ G(b) - G(a)`, i.e. `q φ(m/q) ≤ ∫_a^b φ(K u^{K-1}) du` with
`q = b - a`, `m = b^K - a^K`, `φ(y) = y ln y`. -/
theorem atom_le {K : ℕ} (hK : 1 ≤ K) {a b : ℝ} (ha : 0 ≤ a) (hab : a ≤ b) :
    (b ^ K - a ^ K) * log ((b ^ K - a ^ K) / (b - a)) ≤ G K b - G K a := by
  rcases eq_or_lt_of_le hab with rfl | hlt
  · simp
  have hbK : a ^ K < b ^ K := pow_lt_pow_left₀ hlt ha (by omega)
  have hy0 : 0 < (b ^ K - a ^ K) / (b - a) := div_pos (by linarith) (by linarith)
  have h := Dfun_monotoneOn hK ha hy0 b ⟨le_rfl, hab⟩ ⟨hab, le_rfl⟩ hab
  rw [Dfun_self, Dfun_at_b K hlt] at h
  linarith

/-- **Strict Jensen step** for `K ≥ 2` on an atom of positive mass: `h(u) = K u^{K-1}` is not
constant on `(a, b)`. -/
theorem atom_lt {K : ℕ} (hK : 2 ≤ K) {a b : ℝ} (ha : 0 ≤ a) (hab : a < b) :
    (b ^ K - a ^ K) * log ((b ^ K - a ^ K) / (b - a)) < G K b - G K a := by
  have hK1 : 1 ≤ K := by omega
  have hbK : a ^ K < b ^ K := pow_lt_pow_left₀ hab ha (by omega)
  have hy0 : 0 < (b ^ K - a ^ K) / (b - a) := div_pos (by linarith) (by linarith)
  have hmono := Dfun_monotoneOn hK1 ha hy0 b
  have hDb := Dfun_at_b K hab
  by_contra hcon
  have hDb0 : Dfun K a ((b ^ K - a ^ K) / (b - a)) b ≤ 0 := by
    rw [hDb]; linarith [not_lt.mp hcon]
  -- `D` vanishes on `[a, b]`
  have hzero : ∀ x ∈ Set.Icc a b, Dfun K a ((b ^ K - a ^ K) / (b - a)) x = 0 := by
    intro x hx
    have h1 := hmono ⟨le_rfl, hab.le⟩ hx hx.1
    have h2 := hmono hx ⟨hab.le, le_rfl⟩ hx.2
    rw [Dfun_self] at h1
    linarith
  -- hence `h(x) = y₀` on `(a, b)`
  have heq : ∀ x ∈ Set.Ioo a b, (K : ℝ) * x ^ (K - 1) = (b ^ K - a ^ K) / (b - a) := by
    intro x hx
    have hx0 : 0 < x := by linarith [hx.1]
    have hloc : Dfun K a ((b ^ K - a ^ K) / (b - a)) =ᶠ[nhds x] fun _ => 0 := by
      filter_upwards [Ioo_mem_nhds hx.1 hx.2] with z hz
      exact hzero z ⟨hz.1.le, hz.2.le⟩
    have h0 : HasDerivAt (Dfun K a ((b ^ K - a ^ K) / (b - a))) 0 x :=
      (hasDerivAt_const x (0 : ℝ)).congr_of_eventuallyEq hloc
    have hd := (hasDerivAt_Dfun hK1 a ((b ^ K - a ^ K) / (b - a)) hx0).unique h0
    by_contra hne
    have hK0 : (0 : ℝ) < K := by exact_mod_cast hK1
    have hpos : 0 < (K : ℝ) * x ^ (K - 1) := by positivity
    have := tangent_mul_log_strict hpos hy0 hne
    rw [Dder_eq hK1 _ hx0] at hd
    linarith
  -- but `h` is strictly increasing for `K ≥ 2`
  have hx1 : (2 * a + b) / 3 ∈ Set.Ioo a b := ⟨by linarith, by linarith⟩
  have hx2 : (a + 2 * b) / 3 ∈ Set.Ioo a b := ⟨by linarith, by linarith⟩
  have hlt12 : (2 * a + b) / 3 < (a + 2 * b) / 3 := by linarith
  have hpow : ((2 * a + b) / 3) ^ (K - 1) < ((a + 2 * b) / 3) ^ (K - 1) :=
    pow_lt_pow_left₀ hlt12 (by linarith) (by omega)
  have hK0 : (0 : ℝ) < K := by exact_mod_cast hK1
  have e1 := heq _ hx1
  have e2 := heq _ hx2
  nlinarith

/-! ## Telescoping over the atoms -/

/-- `F(s) = ∑_{t ∈ T, t ≤ s} q(t)` for a law `q` on the finite set of atoms `T`. -/
noncomputable def Fle (T : Finset ℝ) (q : ℝ → ℝ) (s : ℝ) : ℝ := ∑ t ∈ T with t ≤ s, q t

/-- `F(s-) = ∑_{t ∈ T, t < s} q(t)`. -/
noncomputable def Flt (T : Finset ℝ) (q : ℝ → ℝ) (s : ℝ) : ℝ := ∑ t ∈ T with t < s, q t

theorem telescope (g : ℝ → ℝ) (q : ℝ → ℝ) (T : Finset ℝ) :
    ∑ s ∈ T, (g (Fle T q s) - g (Flt T q s)) = g (∑ t ∈ T, q t) - g 0 := by
  induction T using Finset.induction_on_max with
  | empty => simp
  | insert x T hx ih =>
    have hxT : x ∉ T := fun h => lt_irrefl x (hx x h)
    rw [Finset.sum_insert hxT]
    have h1 : ∀ s ∈ T, Fle (insert x T) q s = Fle T q s := by
      intro s hs
      unfold Fle
      rw [Finset.filter_insert, ite_eq_right (not_le.mpr (hx s hs))]
    have h2 : ∀ s ∈ T, Flt (insert x T) q s = Flt T q s := by
      intro s hs
      unfold Flt
      rw [Finset.filter_insert, ite_eq_right (not_lt.mpr (hx s hs).le)]
    rw [Finset.sum_congr rfl (fun s hs => by rw [h1 s hs, h2 s hs]), ih]
    have h3 : Fle (insert x T) q x = ∑ t ∈ insert x T, q t := by
      unfold Fle
      rw [Finset.filter_true_of_mem]
      intro y hy
      rcases Finset.mem_insert.mp hy with rfl | hy
      · exact le_rfl
      · exact (hx y hy).le
    have h4 : Flt (insert x T) q x = ∑ t ∈ T, q t := by
      unfold Flt
      rw [Finset.filter_insert, ite_eq_right (lt_irrefl x), Finset.filter_true_of_mem hx]
    rw [h3, h4, Finset.sum_insert hxT]
    ring

theorem Fle_eq_Flt_add {T : Finset ℝ} (q : ℝ → ℝ) {s : ℝ} (hs : s ∈ T) :
    Fle T q s = Flt T q s + q s := by
  unfold Fle Flt
  rw [Finset.sum_filter, Finset.sum_filter]
  have : ∀ t, (if t ≤ s then q t else 0) = (if t < s then q t else 0) + (if t = s then q t else 0) := by
    intro t
    rcases lt_trichotomy t s with h | rfl | h
    · rw [ite_eq_left h.le, ite_eq_left h, ite_eq_right h.ne]; ring
    · simp
    · rw [ite_eq_right (not_le.mpr h), ite_eq_right (not_lt.mpr h.le), ite_eq_right h.ne']; ring
  rw [Finset.sum_congr rfl (fun t _ => this t), Finset.sum_add_distrib, Finset.sum_ite_eq' T s q,
    ite_eq_left hs]

theorem Flt_nonneg {T : Finset ℝ} {q : ℝ → ℝ} (hq : ∀ t ∈ T, 0 ≤ q t) (s : ℝ) :
    0 ≤ Flt T q s :=
  Finset.sum_nonneg fun t ht => hq t (Finset.mem_filter.mp ht).1

/-- **Theorem B, score form:** for every finite score law `q` on atoms `T` and `K ≥ 1`,
`KL(m_K ‖ q) = ∑_s m_K(s) ln(m_K(s)/q(s)) ≤ ln K - (K - 1)/K`. -/
theorem kl_scores_le {K : ℕ} (hK : 1 ≤ K) (T : Finset ℝ) (q : ℝ → ℝ) (hq : ∀ s ∈ T, 0 ≤ q s)
    (hsum : ∑ s ∈ T, q s = 1) :
    ∑ s ∈ T, (Fle T q s ^ K - Flt T q s ^ K) * log ((Fle T q s ^ K - Flt T q s ^ K) / q s) ≤
      lam K := by
  calc ∑ s ∈ T, (Fle T q s ^ K - Flt T q s ^ K) * log ((Fle T q s ^ K - Flt T q s ^ K) / q s)
      ≤ ∑ s ∈ T, (G K (Fle T q s) - G K (Flt T q s)) := by
        apply Finset.sum_le_sum
        intro s hs
        have hle := Fle_eq_Flt_add q hs
        have h0 := Flt_nonneg hq s
        have := atom_le hK h0 (show Flt T q s ≤ Fle T q s by linarith [hq s hs])
        rwa [show Fle T q s - Flt T q s = q s by linarith] at this
    _ = G K 1 - G K 0 := by rw [telescope, hsum]
    _ = lam K := by rw [G_one, G_zero hK, sub_zero]

/-- **Theorem B, score form, strict:** for `K ≥ 2`, `KL(m_K ‖ q) < λ_K` on every finite law. -/
theorem kl_scores_lt {K : ℕ} (hK : 2 ≤ K) (T : Finset ℝ) (q : ℝ → ℝ) (hq : ∀ s ∈ T, 0 ≤ q s)
    (hsum : ∑ s ∈ T, q s = 1) :
    ∑ s ∈ T, (Fle T q s ^ K - Flt T q s ^ K) * log ((Fle T q s ^ K - Flt T q s ^ K) / q s) <
      lam K := by
  have hK1 : 1 ≤ K := by omega
  obtain ⟨s0, hs0, hq0⟩ : ∃ s ∈ T, 0 < q s := by
    by_contra h
    have : ∑ s ∈ T, q s ≤ 0 :=
      Finset.sum_nonpos fun s hs => not_lt.mp fun hlt => h ⟨s, hs, hlt⟩
    linarith
  calc ∑ s ∈ T, (Fle T q s ^ K - Flt T q s ^ K) * log ((Fle T q s ^ K - Flt T q s ^ K) / q s)
      < ∑ s ∈ T, (G K (Fle T q s) - G K (Flt T q s)) := by
        apply Finset.sum_lt_sum
        · intro s hs
          have hle := Fle_eq_Flt_add q hs
          have h0 := Flt_nonneg hq s
          have := atom_le hK1 h0 (show Flt T q s ≤ Fle T q s by linarith [hq s hs])
          rwa [show Fle T q s - Flt T q s = q s by linarith] at this
        · refine ⟨s0, hs0, ?_⟩
          have hle := Fle_eq_Flt_add q hs0
          have h0 := Flt_nonneg hq s0
          have := atom_lt hK h0 (show Flt T q s0 < Fle T q s0 by linarith)
          rwa [show Fle T q s0 - Flt T q s0 = q s0 by linarith] at this
    _ = G K 1 - G K 0 := by rw [telescope, hsum]
    _ = lam K := by rw [G_one, G_zero hK1, sub_zero]

/-! ## Records -/

section Records

variable {Ω : Type*} [Fintype Ω] (p0 : Ω → ℝ) (S : Ω → ℝ)

/-- `q(s) = P₀(S = s)`. -/
noncomputable def scoreMass (s : ℝ) : ℝ := ∑ ω with S ω = s, p0 ω

/-- `F(s) = P₀(S ≤ s)`. -/
noncomputable def cdf (s : ℝ) : ℝ := ∑ ω with S ω ≤ s, p0 ω

/-- `F(s-) = P₀(S < s)`. -/
noncomputable def cdfLt (s : ℝ) : ℝ := ∑ ω with S ω < s, p0 ω

/-- `m_K(s) = F(s)^K - F(s-)^K`, the law of the maximum of `K` i.i.d. scores. -/
noncomputable def maxLaw (K : ℕ) (s : ℝ) : ℝ := cdf p0 S s ^ K - cdfLt p0 S s ^ K

/-- The kept record's law given by Theorem A, `π_K(ω) = p₀(ω) m_K(S ω)/q(S ω)` (zero where
`p₀(ω) = 0`). -/
noncomputable def bestOfK (K : ℕ) (ω : Ω) : ℝ := p0 ω * maxLaw p0 S K (S ω) / scoreMass p0 S (S ω)

/-- Discrete KL divergence `∑ π log(π/p)` (with `0 log 0 = 0`; used here only for `π ≪ p`). -/
noncomputable def kl {α : Type*} [Fintype α] (μ ν : α → ℝ) : ℝ := ∑ x, μ x * log (μ x / ν x)

/-- The atoms of the score law. -/
noncomputable def atoms : Finset ℝ := univ.image S

theorem cdf_eq_Fle (s : ℝ) : cdf p0 S s = Fle (atoms S) (scoreMass p0 S) s := by
  unfold cdf Fle scoreMass atoms
  rw [← Finset.sum_fiberwise_of_maps_to (s := univ.filter fun ω => S ω ≤ s)
    (t := (univ.image S).filter fun t => t ≤ s) (g := S)]
  · apply Finset.sum_congr rfl
    intro t ht
    have hts : t ≤ s := (Finset.mem_filter.mp ht).2
    apply Finset.sum_congr
    · ext ω; simp only [Finset.mem_filter, Finset.mem_univ, true_and]
      constructor
      · exact fun h => h.2
      · intro h; exact ⟨h ▸ hts, h⟩
    · intro _ _; rfl
  · intro ω hω
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hω
    simp [hω]

theorem cdfLt_eq_Flt (s : ℝ) : cdfLt p0 S s = Flt (atoms S) (scoreMass p0 S) s := by
  unfold cdfLt Flt scoreMass atoms
  rw [← Finset.sum_fiberwise_of_maps_to (s := univ.filter fun ω => S ω < s)
    (t := (univ.image S).filter fun t => t < s) (g := S)]
  · apply Finset.sum_congr rfl
    intro t ht
    have hts : t < s := (Finset.mem_filter.mp ht).2
    apply Finset.sum_congr
    · ext ω; simp only [Finset.mem_filter, Finset.mem_univ, true_and]
      constructor
      · exact fun h => h.2
      · intro h; exact ⟨h ▸ hts, h⟩
    · intro _ _; rfl
  · intro ω hω
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hω
    simp [hω]

theorem sum_scoreMass : ∑ t ∈ atoms S, scoreMass p0 S t = ∑ ω, p0 ω := by
  unfold scoreMass atoms
  exact Finset.sum_fiberwise_of_maps_to (fun ω _ => Finset.mem_image_of_mem S (mem_univ ω)) p0

theorem sum_comp_score (g : ℝ → ℝ) :
    ∑ ω, p0 ω * g (S ω) = ∑ t ∈ atoms S, scoreMass p0 S t * g t := by
  unfold scoreMass atoms
  rw [← Finset.sum_fiberwise_of_maps_to (fun ω _ => Finset.mem_image_of_mem S (mem_univ ω))
    (fun ω => p0 ω * g (S ω))]
  apply Finset.sum_congr rfl
  intro t _
  rw [Finset.sum_mul]
  apply Finset.sum_congr rfl
  intro ω hω
  rw [(Finset.mem_filter.mp hω).2]

theorem scoreMass_nonneg (hp0 : ∀ ω, 0 ≤ p0 ω) (s : ℝ) : 0 ≤ scoreMass p0 S s :=
  Finset.sum_nonneg fun ω _ => hp0 ω

theorem p0_le_scoreMass (hp0 : ∀ ω, 0 ≤ p0 ω) (ω : Ω) : p0 ω ≤ scoreMass p0 S (S ω) := by
  unfold scoreMass
  exact Finset.single_le_sum (fun ω' _ => hp0 ω') (Finset.mem_filter.mpr ⟨mem_univ ω, rfl⟩)

theorem maxLaw_eq (K : ℕ) (t : ℝ) : maxLaw p0 S K t =
    Fle (atoms S) (scoreMass p0 S) t ^ K - Flt (atoms S) (scoreMass p0 S) t ^ K := by
  unfold maxLaw; rw [cdf_eq_Fle, cdfLt_eq_Flt]

/-- **Theorem A, KL sentence:** `KL(π_K ‖ p₀) = KL(m_K ‖ q)`: the likelihood ratio depends on the
record only through its score. -/
theorem kl_record_eq_kl_scores (K : ℕ) :
    kl (bestOfK p0 S K) p0 =
      ∑ t ∈ atoms S, maxLaw p0 S K t * log (maxLaw p0 S K t / scoreMass p0 S t) := by
  unfold kl
  have hrec : ∀ ω, bestOfK p0 S K ω * log (bestOfK p0 S K ω / p0 ω) =
      p0 ω * ((maxLaw p0 S K (S ω) / scoreMass p0 S (S ω)) *
        log (maxLaw p0 S K (S ω) / scoreMass p0 S (S ω))) := by
    intro ω
    unfold bestOfK
    by_cases h : p0 ω = 0
    · simp [h]
    · rw [show p0 ω * maxLaw p0 S K (S ω) / scoreMass p0 S (S ω) / p0 ω =
          maxLaw p0 S K (S ω) / scoreMass p0 S (S ω) by field_simp]
      ring
  rw [Finset.sum_congr rfl (fun ω _ => hrec ω), sum_comp_score p0 S
    (fun s => maxLaw p0 S K s / scoreMass p0 S s * log (maxLaw p0 S K s / scoreMass p0 S s))]
  apply Finset.sum_congr rfl
  intro t ht
  by_cases hq : scoreMass p0 S t = 0
  · -- an atom of mass zero has `m_K = 0`
    have hm : maxLaw p0 S K t = 0 := by
      unfold maxLaw
      rw [cdf_eq_Fle, cdfLt_eq_Flt, Fle_eq_Flt_add _ ht, hq, add_zero, sub_self]
    simp [hq, hm]
  · field_simp

/-- **Theorem B.** For every finite base law `p₀`, score `S` and `K ≥ 1`, the best-of-`K` record law
`π_K` of Theorem A satisfies `KL(π_K ‖ p₀) ≤ ln K - (K - 1)/K`. With `SelectionTieRules.keptLaw_eq`
this holds for every tie rule (`SelectionTieRules.theoremB_every_tie_rule`). -/
theorem theoremB (hp0 : ∀ ω, 0 ≤ p0 ω) (hsum : ∑ ω, p0 ω = 1) {K : ℕ} (hK : 1 ≤ K) :
    kl (bestOfK p0 S K) p0 ≤ lam K := by
  rw [kl_record_eq_kl_scores p0 S K]
  simp_rw [maxLaw_eq p0 S K]
  exact kl_scores_le hK (atoms S) (scoreMass p0 S) (fun s _ => scoreMass_nonneg p0 S hp0 s)
    (by rw [sum_scoreMass, hsum])

/-- **Theorem B, strictness:** for `K ≥ 2`, `KL(π_K ‖ p₀) < λ_K` on every finite `p₀`. -/
theorem theoremB_strict (hp0 : ∀ ω, 0 ≤ p0 ω) (hsum : ∑ ω, p0 ω = 1) {K : ℕ} (hK : 2 ≤ K) :
    kl (bestOfK p0 S K) p0 < lam K := by
  rw [kl_record_eq_kl_scores p0 S K]
  simp_rw [maxLaw_eq p0 S K]
  exact kl_scores_lt hK (atoms S) (scoreMass p0 S) (fun s _ => scoreMass_nonneg p0 S hp0 s)
    (by rw [sum_scoreMass, hsum])

/-- **Theorem B, equality case:** for `K ≥ 1`, `KL(π_K ‖ p₀) = λ_K` iff `K = 1`. -/
theorem theoremB_eq_iff (hp0 : ∀ ω, 0 ≤ p0 ω) (hsum : ∑ ω, p0 ω = 1) {K : ℕ} (hK : 1 ≤ K) :
    kl (bestOfK p0 S K) p0 = lam K ↔ K = 1 := by
  constructor
  · intro h
    by_contra hne
    have := theoremB_strict p0 S hp0 hsum (show 2 ≤ K by omega)
    linarith
  · rintro rfl
    rw [kl_record_eq_kl_scores p0 S 1]
    have : lam 1 = 0 := by simp [lam]
    rw [this]
    apply Finset.sum_eq_zero
    intro t ht
    rw [maxLaw_eq, pow_one, pow_one, Fle_eq_Flt_add _ ht, add_sub_cancel_left]
    by_cases hq : scoreMass p0 S t = 0
    · simp [hq]
    · rw [div_self hq, Real.log_one, mul_zero]

end Records

end FeedbackChannel.SelectionContainment

import Mathlib.Tactic
import Mathlib.Analysis.Real.Sqrt

/-!
# Gold calibration with independent raters: Walsh identities, Dawid–Skene moments

Source: `paper/gold_calibration_second_grader.md`, §1–3 (symmetric model, Propositions 1–3),
§7 (asymmetric three-rater model, Proposition 4) and §8 (four raters: Proposition 5, the six
equalities, the copying grader). The Jacobian minor of §8 (Proposition 6b) is in
`FeedbackChannel.RatersJacobian`.

**Model** (two-class Dawid–Skene on `n` raters). The true label `Y ∈ {0, 1}` has
`Pr[Y = 1] = π`. Given `Y`, the raters report independently; rater `i` has false-negative rate
`α i = Pr[X_i = 0 | Y = 1]` and false-positive rate `β i = Pr[X_i = 1 | Y = 0]`. Reports are
`Bool`s (`true` = 1). `prob π α β x` is the probability of the report vector `x`, obtained by
summing the latent label out. The symmetric model of §1 is `α = β = e` (rater `i` flips the label
with probability `e i`). Every moment below is a sum over the `2 ^ n` report vectors.
-/

namespace FeedbackChannel.Raters

open Finset

/-- Mass a rater puts on report `b` when it reports `true` with probability `q`. -/
def bern (q : ℝ) (b : Bool) : ℝ := if b then q else 1 - q

/-- Indicator of a positive report. -/
def ind (b : Bool) : ℝ := if b then 1 else 0

/-- `(-1) ^ x` for a report `x ∈ {0, 1}`. -/
def sgn (b : Bool) : ℝ := if b then -1 else 1

@[simp] lemma bern_true (q : ℝ) : bern q true = q := rfl
@[simp] lemma bern_false (q : ℝ) : bern q false = 1 - q := rfl
@[simp] lemma ind_true : ind true = 1 := rfl
@[simp] lemma ind_false : ind false = 0 := rfl
@[simp] lemma sgn_true : sgn true = -1 := rfl
@[simp] lemma sgn_false : sgn false = 1 := rfl

variable {n : ℕ}

/-- Probability of the report vector `x` in the two-class model. -/
def prob (π : ℝ) (α β : Fin n → ℝ) (x : Fin n → Bool) : ℝ :=
  π * ∏ i, bern (1 - α i) (x i) + (1 - π) * ∏ i, bern (β i) (x i)

theorem sum_prod_bool (f : Fin n → Bool → ℝ) :
    ∑ x : Fin n → Bool, ∏ i, f i (x i) = ∏ i, (f i true + f i false) :=
  calc ∑ x : Fin n → Bool, ∏ i, f i (x i) = ∏ i, ∑ b, f i b := (Fintype.prod_sum f).symm
    _ = ∏ i, (f i true + f i false) := Finset.prod_congr rfl fun _ _ => Fintype.sum_bool _

/-- Conditional independence multiplies: the expectation of a product of per-rater functions over
a set `S` of raters is the prior mixture of the products of per-rater conditional expectations. -/
theorem expect_prod_on (π : ℝ) (α β : Fin n → ℝ) (S : Finset (Fin n)) (h : Fin n → Bool → ℝ) :
    ∑ x, prob π α β x * ∏ i ∈ S, h i (x i) =
      π * ∏ i ∈ S, ((1 - α i) * h i true + α i * h i false) +
      (1 - π) * ∏ i ∈ S, (β i * h i true + (1 - β i) * h i false) := by
  have key : ∀ q : Fin n → ℝ, ∑ x : Fin n → Bool, (∏ i, bern (q i) (x i)) * ∏ i ∈ S, h i (x i) =
      ∏ i ∈ S, (q i * h i true + (1 - q i) * h i false) := by
    intro q
    have hx : ∀ x : Fin n → Bool, (∏ i, bern (q i) (x i)) * ∏ i ∈ S, h i (x i) =
        ∏ i, (bern (q i) (x i) * if i ∈ S then h i (x i) else 1) := by
      intro x
      rw [← Fintype.prod_ite_mem S (fun i => h i (x i)), ← Finset.prod_mul_distrib]
    rw [Finset.sum_congr rfl fun x _ => hx x,
      sum_prod_bool (fun i b => bern (q i) b * if i ∈ S then h i b else 1),
      ← Fintype.prod_ite_mem S (fun i => q i * h i true + (1 - q i) * h i false)]
    refine Finset.prod_congr rfl fun i _ => ?_
    by_cases hi : i ∈ S <;> simp [hi]
  have e1 := key (fun i => 1 - α i)
  have e2 := key β
  simp only [sub_sub_cancel] at e1
  simp only [prob, add_mul, Finset.sum_add_distrib, mul_assoc, ← Finset.mul_sum, e1, e2]

/-- The report distribution sums to one. -/
theorem mass_one (π : ℝ) (α β : Fin n → ℝ) : ∑ x, prob π α β x = 1 := by
  have h := expect_prod_on π α β ∅ (fun _ _ => 1)
  simp only [prod_empty, mul_one] at h
  rw [h]; ring

/-- **Label switching (§7).** `(π, α, β)` and `(1 - π, 1 - β, 1 - α)` give the same table. -/
theorem label_switch (π : ℝ) (α β : Fin n → ℝ) (x : Fin n → Bool) :
    prob (1 - π) (fun i => 1 - β i) (fun i => 1 - α i) x = prob π α β x := by
  simp only [prob, sub_sub_cancel]; ring

/-! ## Symmetric model (§1–§3) -/

/-- Walsh coefficient `p̂_S = E ∏_{i ∈ S} (-1)^{X_i}` in the symmetric model with error rates `e`. -/
def walsh (π : ℝ) (e : Fin n → ℝ) (S : Finset (Fin n)) : ℝ :=
  ∑ x, prob π e e x * ∏ i ∈ S, sgn (x i)

/-- **Proposition 1** (for any number of raters). `p̂_S = τ^{[|S| odd]} ∏_{i∈S} d_i` with
`τ = 1 - 2π`, `d_i = 1 - 2 e_i`. -/
theorem prop1_walsh (π : ℝ) (e : Fin n → ℝ) (S : Finset (Fin n)) :
    walsh π e S = (if Odd S.card then 1 - 2 * π else 1) * ∏ i ∈ S, (1 - 2 * e i) := by
  rw [walsh, expect_prod_on π e e S (fun _ b => sgn b)]
  have h1 : ∀ i, (1 - e i) * sgn true + e i * sgn false = -1 * (1 - 2 * e i) := by
    intro i; rw [sgn_true, sgn_false]; ring
  have h2 : ∀ i, e i * sgn true + (1 - e i) * sgn false = 1 - 2 * e i := by
    intro i; rw [sgn_true, sgn_false]; ring
  simp only [h1, h2, prod_mul_distrib, prod_const]
  rcases Nat.even_or_odd S.card with h | h
  · rw [h.neg_one_pow, if_neg (Nat.not_odd_iff_even.2 h)]; ring
  · rw [h.neg_one_pow, if_pos h]; ring

/-- Agreement rate `A_ij = Pr[X_i = X_j]`. -/
def agree (π : ℝ) (e : Fin n → ℝ) (i j : Fin n) : ℝ :=
  ∑ x, prob π e e x * (if x i = x j then 1 else 0)

/-- Pair polarity `κ_ij = 2 A_ij - 1`. -/
def kappa (π : ℝ) (e : Fin n → ℝ) (i j : Fin n) : ℝ := 2 * agree π e i j - 1

/-- **Proposition 1, pair polarity.** `κ_ij = (1 - 2 e_i)(1 - 2 e_j)` for `i ≠ j`. -/
theorem kappa_eq (π : ℝ) (e : Fin n → ℝ) {i j : Fin n} (hij : i ≠ j) :
    kappa π e i j = (1 - 2 * e i) * (1 - 2 * e j) := by
  have hw : walsh π e {i, j} = (1 - 2 * e i) * (1 - 2 * e j) := by
    rw [prop1_walsh, card_pair_eq_two_iff.2 hij, prod_pair hij,
      if_neg (Nat.not_odd_iff_even.2 even_two), one_mul]
  have hx : ∀ x : Fin n → Bool, prob π e e x * ∏ k ∈ ({i, j} : Finset (Fin n)), sgn (x k) =
      2 * (prob π e e x * (if x i = x j then 1 else 0)) - prob π e e x := by
    intro x
    rw [prod_pair hij]
    cases x i <;> cases x j <;> simp <;> ring
  rw [← hw, walsh, Finset.sum_congr rfl fun x _ => hx x, sum_sub_distrib, ← Finset.mul_sum,
    mass_one, kappa, agree]

/-- The agreement rate itself: `A_ij = 1 - e_i - e_j + 2 e_i e_j`. -/
theorem agree_eq (π : ℝ) (e : Fin n → ℝ) {i j : Fin n} (hij : i ≠ j) :
    agree π e i j = 1 - e i - e j + 2 * e i * e j := by
  have h := kappa_eq π e hij
  rw [kappa] at h
  linarith

/-- **Proposition 2** (the three-rater identity, for any three distinct raters among `n`).
If `κ_jk ≠ 0` then `(1 - 2 e_i)^2 = κ_ij κ_ik / κ_jk`; with `i` the gold grader `G₁`, `j` the
second grader `G₂` and `k` the controller `C`, this is `(1 - 2η₁)² = κ₁₂ κ₁C / κ₂C`. -/
theorem prop2_three_rater (π : ℝ) (e : Fin n → ℝ) {i j k : Fin n} (hij : i ≠ j) (hik : i ≠ k)
    (hjk : j ≠ k) (h : kappa π e j k ≠ 0) :
    (1 - 2 * e i) ^ 2 = kappa π e i j * kappa π e i k / kappa π e j k := by
  rw [kappa_eq π e hij, kappa_eq π e hik]
  rw [kappa_eq π e hjk] at h ⊢
  rw [eq_div_iff h]; ring

/-- **Proposition 2, gold grader.** Three raters: gold grader `G₁` (index 0, error `η₁ = e 0`),
second grader `G₂` (index 1) and controller `C` (index 2). If `κ₂C ≠ 0` then
`(1 - 2η₁)² = κ₁₂ κ₁C / κ₂C`. -/
theorem prop2_gold (π : ℝ) (e : Fin 3 → ℝ) (h : kappa π e 1 2 ≠ 0) :
    (1 - 2 * e 0) ^ 2 = kappa π e 0 1 * kappa π e 0 2 / kappa π e 1 2 :=
  prop2_three_rater π e (by decide) (by decide) (by decide) h

/-- **Proposition 3** (three raters). `M₁κ₂₃ = M₂κ₁₃ = M₃κ₁₂ = P`, with the marginal biases
`M_i = p̂_{i}` and the parity bias `P = p̂_{123}`. -/
theorem prop3_constraints (π : ℝ) (e : Fin 3 → ℝ) :
    walsh π e {0} * kappa π e 1 2 = walsh π e univ ∧
    walsh π e {1} * kappa π e 0 2 = walsh π e univ ∧
    walsh π e {2} * kappa π e 0 1 = walsh π e univ := by
  have hodd1 : Odd (1 : ℕ) := odd_one
  have hodd3 : Odd (3 : ℕ) := ⟨1, rfl⟩
  simp only [prop1_walsh, card_singleton, prod_singleton, card_univ, Fintype.card_fin,
    Fin.prod_univ_three, if_pos hodd1, if_pos hodd3]
  rw [kappa_eq π e (by decide : (1 : Fin 3) ≠ 2), kappa_eq π e (by decide : (0 : Fin 3) ≠ 2),
    kappa_eq π e (by decide : (0 : Fin 3) ≠ 1)]
  refine ⟨by ring, by ring, by ring⟩

/-! ## Central moments in the asymmetric model (§7–§8) -/

/-- Mean report `p_i = Pr[X_i = 1]`. -/
def mean (π : ℝ) (α β : Fin n → ℝ) (i : Fin n) : ℝ := ∑ x, prob π α β x * ind (x i)

theorem mean_eq (π : ℝ) (α β : Fin n → ℝ) (i : Fin n) :
    mean π α β i = π * (1 - α i) + (1 - π) * β i := by
  have h := expect_prod_on π α β {i} (fun _ b => ind b)
  simp only [prod_singleton, ind_true, ind_false, mul_one, mul_zero, add_zero] at h
  rw [mean, h]

/-- Central moment `k_S = E ∏_{i ∈ S} (X_i - p_i)`. -/
def cmom (π : ℝ) (α β : Fin n → ℝ) (S : Finset (Fin n)) : ℝ :=
  ∑ x, prob π α β x * ∏ i ∈ S, (ind (x i) - mean π α β i)

/-- `μ_k = E (Y - π)^k = π (1 - π)^k + (1 - π)(-π)^k`. -/
def mu (π : ℝ) (k : ℕ) : ℝ := π * (1 - π) ^ k + (1 - π) * (-π) ^ k

theorem mu_two (π : ℝ) : mu π 2 = π * (1 - π) := by unfold mu; ring
theorem mu_three (π : ℝ) : mu π 3 = π * (1 - π) * (1 - 2 * π) := by unfold mu; ring
theorem mu_four (π : ℝ) : mu π 4 = π * (1 - π) * (1 - 3 * (π * (1 - π))) := by unfold mu; ring

/-- `δ_i = 1 - α_i - β_i`, rater `i`'s hit rate minus its false-alarm rate. -/
def del (α β : Fin n → ℝ) (i : Fin n) : ℝ := 1 - α i - β i

/-- **Proposition 5** (for any number of raters and any set `S` of them).
`k_S = μ_{|S|} ∏_{i∈S} δ_i` with `δ_i = 1 - α_i - β_i`; `μ₂ = u`, `μ₃ = u(1 - 2π)`,
`μ₄ = u(1 - 3u)`, `u = π(1 - π)` are `mu_two`, `mu_three`, `mu_four`. -/
theorem prop5 (π : ℝ) (α β : Fin n → ℝ) (S : Finset (Fin n)) :
    cmom π α β S = mu π S.card * ∏ i ∈ S, del α β i := by
  rw [cmom, expect_prod_on π α β S (fun i b => ind b - mean π α β i)]
  have h1 : ∀ i, (1 - α i) * (ind true - mean π α β i) + α i * (ind false - mean π α β i) =
      (1 - π) * del α β i := by
    intro i; rw [mean_eq, ind_true, ind_false, del]; ring
  have h2 : ∀ i, β i * (ind true - mean π α β i) + (1 - β i) * (ind false - mean π α β i) =
      -π * del α β i := by
    intro i; rw [mean_eq, ind_true, ind_false, del]; ring
  simp only [h1, h2, prod_mul_distrib, prod_const, mu]
  ring

theorem cmom_pair (π : ℝ) (α β : Fin n → ℝ) {i j : Fin n} (hij : i ≠ j) :
    cmom π α β {i, j} = π * (1 - π) * del α β i * del α β j := by
  rw [prop5, card_pair_eq_two_iff.2 hij, prod_pair hij, mu_two]; ring

theorem cmom_triple (π : ℝ) (α β : Fin n → ℝ) {i j k : Fin n} (hij : i ≠ j) (hik : i ≠ k)
    (hjk : j ≠ k) :
    cmom π α β {i, j, k} =
      π * (1 - π) * (1 - 2 * π) * del α β i * del α β j * del α β k := by
  have hi : i ∉ ({j, k} : Finset (Fin n)) := by simp [hij, hik]
  rw [prop5, card_insert_of_notMem hi, card_pair_eq_two_iff.2 hjk, prod_insert hi,
    prod_pair hjk, mu_three]; ring

/-! ### Four raters (§8): the six equalities -/

/-- `c_ij = k_{ij}` for four raters (indices `0..3` are raters `1..4`, rater 4 the controller). -/
def c4 (π : ℝ) (α β : Fin 4 → ℝ) (i j : Fin 4) : ℝ := cmom π α β {i, j}

/-- `k_{ijl}` for four raters. -/
def k4 (π : ℝ) (α β : Fin 4 → ℝ) (i j l : Fin 4) : ℝ := cmom π α β {i, j, l}

/-- `k_{1234}`. -/
def k1234 (π : ℝ) (α β : Fin 4 → ℝ) : ℝ := cmom π α β univ

theorem k1234_eq (π : ℝ) (α β : Fin 4 → ℝ) :
    k1234 π α β = π * (1 - π) * (1 - 3 * (π * (1 - π))) *
      (del α β 0 * del α β 1 * del α β 2 * del α β 3) := by
  rw [k1234, prop5, card_univ, Fintype.card_fin, Fin.prod_univ_four, mu_four]

/-- **The six equalities (§8)**, which hold identically on the four-rater model:
tetrads `c₁₂c₃₄ = c₁₃c₂₄ = c₁₄c₂₃`; ratios `k₁₂₃c₁₄ = k₁₂₄c₁₃`, `k₁₂₃c₁₄ = k₁₃₄c₁₂`,
`k₁₂₃c₂₄ = k₂₃₄c₁₂`; and `(k₁₂₃₄ - c₁₂c₃₄)c₁₂ = k₁₂₃k₁₂₄`. -/
theorem six_equalities (π : ℝ) (α β : Fin 4 → ℝ) :
    c4 π α β 0 1 * c4 π α β 2 3 = c4 π α β 0 2 * c4 π α β 1 3 ∧
    c4 π α β 0 2 * c4 π α β 1 3 = c4 π α β 0 3 * c4 π α β 1 2 ∧
    k4 π α β 0 1 2 * c4 π α β 0 3 = k4 π α β 0 1 3 * c4 π α β 0 2 ∧
    k4 π α β 0 1 2 * c4 π α β 0 3 = k4 π α β 0 2 3 * c4 π α β 0 1 ∧
    k4 π α β 0 1 2 * c4 π α β 1 3 = k4 π α β 1 2 3 * c4 π α β 0 1 ∧
    (k1234 π α β - c4 π α β 0 1 * c4 π α β 2 3) * c4 π α β 0 1 =
      k4 π α β 0 1 2 * k4 π α β 0 1 3 := by
  have e01 := cmom_pair π α β (by decide : (0 : Fin 4) ≠ 1)
  have e02 := cmom_pair π α β (by decide : (0 : Fin 4) ≠ 2)
  have e03 := cmom_pair π α β (by decide : (0 : Fin 4) ≠ 3)
  have e12 := cmom_pair π α β (by decide : (1 : Fin 4) ≠ 2)
  have e13 := cmom_pair π α β (by decide : (1 : Fin 4) ≠ 3)
  have e23 := cmom_pair π α β (by decide : (2 : Fin 4) ≠ 3)
  have t012 := cmom_triple π α β (by decide : (0 : Fin 4) ≠ 1) (by decide : (0 : Fin 4) ≠ 2)
    (by decide : (1 : Fin 4) ≠ 2)
  have t013 := cmom_triple π α β (by decide : (0 : Fin 4) ≠ 1) (by decide : (0 : Fin 4) ≠ 3)
    (by decide : (1 : Fin 4) ≠ 3)
  have t023 := cmom_triple π α β (by decide : (0 : Fin 4) ≠ 2) (by decide : (0 : Fin 4) ≠ 3)
    (by decide : (2 : Fin 4) ≠ 3)
  have t123 := cmom_triple π α β (by decide : (1 : Fin 4) ≠ 2) (by decide : (1 : Fin 4) ≠ 3)
    (by decide : (2 : Fin 4) ≠ 3)
  have q := k1234_eq π α β
  simp only [c4, k4, e01, e02, e03, e12, e13, e23, t012, t013, t023, t123, q]
  refine ⟨by ring, by ring, by ring, by ring, by ring, by ring⟩

/-! ## Asymmetric three-rater model (§7, Proposition 4) -/

/-- Raw moment `Pr[X_i = 1 for every i ∈ T]`. -/
def pm (π : ℝ) (α β : Fin n → ℝ) (T : Finset (Fin n)) : ℝ :=
  ∑ x, prob π α β x * ∏ i ∈ T, ind (x i)

theorem pm_eq (π : ℝ) (α β : Fin n → ℝ) (T : Finset (Fin n)) :
    pm π α β T = π * ∏ i ∈ T, (1 - α i) + (1 - π) * ∏ i ∈ T, β i := by
  rw [pm, expect_prod_on π α β T (fun _ b => ind b)]
  simp only [ind_true, ind_false, mul_one, mul_zero, add_zero]

/-- `p_i` for three raters. -/
def p3 (π : ℝ) (α β : Fin 3 → ℝ) (i : Fin 3) : ℝ := pm π α β {i}

/-- `c_ij = p_ij - p_i p_j` for three raters (raw form, as §7 defines it). -/
def cov3 (π : ℝ) (α β : Fin 3 → ℝ) (i j : Fin 3) : ℝ :=
  pm π α β {i, j} - pm π α β {i} * pm π α β {j}

/-- `k₃ = p₁₂₃ - Σ_i p_i p_jk + 2 p₁p₂p₃` (raw form, as §7 defines it). -/
def k3 (π : ℝ) (α β : Fin 3 → ℝ) : ℝ :=
  pm π α β univ -
    (pm π α β {0} * pm π α β {1, 2} + pm π α β {1} * pm π α β {0, 2} +
      pm π α β {2} * pm π α β {0, 1}) +
    2 * pm π α β {0} * pm π α β {1} * pm π α β {2}

theorem p3_eq (π : ℝ) (α β : Fin 3 → ℝ) (i : Fin 3) :
    p3 π α β i = π * (1 - α i) + (1 - π) * β i := by
  rw [p3, pm_eq, prod_singleton, prod_singleton]

/-- **Proposition 4, covariances.** `c_ij = u δ_i δ_j`. -/
theorem prop4_cov (π : ℝ) (α β : Fin 3 → ℝ) {i j : Fin 3} (hij : i ≠ j) :
    cov3 π α β i j = π * (1 - π) * del α β i * del α β j := by
  simp only [cov3, pm_eq, prod_pair hij, prod_singleton, del]
  ring

/-- **Proposition 4, third moment.** `k₃ = u (1 - 2π) δ₁δ₂δ₃`. -/
theorem prop4_k3 (π : ℝ) (α β : Fin 3 → ℝ) :
    k3 π α β = π * (1 - π) * (1 - 2 * π) *
      (del α β 0 * del α β 1 * del α β 2) := by
  simp only [k3, pm_eq, prod_singleton, Fin.prod_univ_three, del,
    prod_pair (by decide : (1 : Fin 3) ≠ 2), prod_pair (by decide : (0 : Fin 3) ≠ 2),
    prod_pair (by decide : (0 : Fin 3) ≠ 1)]
  ring

/-- **Proposition 4, the square.** `R² := k₃² + 4c₁₂c₁₃c₂₃ = u²δ₁²δ₂²δ₃²`. -/
theorem prop4_R2 (π : ℝ) (α β : Fin 3 → ℝ) :
    k3 π α β ^ 2 + 4 * cov3 π α β 0 1 * cov3 π α β 0 2 * cov3 π α β 1 2 =
      (π * (1 - π) * (del α β 0 * del α β 1 * del α β 2)) ^ 2 := by
  rw [prop4_k3, prop4_cov π α β (by decide : (0 : Fin 3) ≠ 1),
    prop4_cov π α β (by decide : (0 : Fin 3) ≠ 2), prop4_cov π α β (by decide : (1 : Fin 3) ≠ 2)]
  ring

/-- Algebraic core of the per-rater solution. -/
theorem solve_rater {π si ti di dj dk R k c p : ℝ} (hπ0 : 0 < π) (hπ1 : π < 1)
    (hdj : dj ≠ 0) (hdk : dk ≠ 0) (hdi : di = si - ti)
    (hR : R = π * (1 - π) * (di * dj * dk))
    (hk : k = π * (1 - π) * (1 - 2 * π) * (di * dj * dk))
    (hc : c = π * (1 - π) * dj * dk) (hp : p = π * si + (1 - π) * ti) :
    si = p + (R + k) / (2 * c) ∧ ti = p - (R - k) / (2 * c) := by
  have hπ : π ≠ 0 := hπ0.ne'
  have hπ' : 1 - π ≠ 0 := by linarith
  subst hR hk hc hp hdi
  constructor <;> field_simp <;> ring

/-- **Proposition 4, the solution.** Under `0 < π < 1` and `δ₁δ₂δ₃ > 0`, with
`R = √(k₃² + 4c₁₂c₁₃c₂₃)` computed from the table:
`π = (R - k₃)/(2R)`, and for `{i, j, k} = {1, 2, 3}`, `s_i = 1 - α_i = p_i + (R + k₃)/(2c_jk)` and
`t_i = β_i = p_i - (R - k₃)/(2c_jk)`. -/
theorem prop4_solution (π : ℝ) (α β : Fin 3 → ℝ) (hπ0 : 0 < π) (hπ1 : π < 1)
    (hδ : 0 < del α β 0 * del α β 1 * del α β 2) (R : ℝ)
    (hR : R = Real.sqrt (k3 π α β ^ 2 + 4 * cov3 π α β 0 1 * cov3 π α β 0 2 * cov3 π α β 1 2)) :
    π = (R - k3 π α β) / (2 * R) ∧
    1 - α 0 = p3 π α β 0 + (R + k3 π α β) / (2 * cov3 π α β 1 2) ∧
    β 0 = p3 π α β 0 - (R - k3 π α β) / (2 * cov3 π α β 1 2) ∧
    1 - α 1 = p3 π α β 1 + (R + k3 π α β) / (2 * cov3 π α β 0 2) ∧
    β 1 = p3 π α β 1 - (R - k3 π α β) / (2 * cov3 π α β 0 2) ∧
    1 - α 2 = p3 π α β 2 + (R + k3 π α β) / (2 * cov3 π α β 0 1) ∧
    β 2 = p3 π α β 2 - (R - k3 π α β) / (2 * cov3 π α β 0 1) := by
  have hu : 0 < π * (1 - π) := mul_pos hπ0 (by linarith)
  have hR' : R = π * (1 - π) * (del α β 0 * del α β 1 * del α β 2) := by
    rw [hR, prop4_R2, Real.sqrt_sq (mul_pos hu hδ).le]
  have hd0 : del α β 0 ≠ 0 := fun h => by rw [h] at hδ; simp at hδ
  have hd1 : del α β 1 ≠ 0 := fun h => by rw [h] at hδ; simp at hδ
  have hd2 : del α β 2 ≠ 0 := fun h => by rw [h] at hδ; simp at hδ
  have hk := prop4_k3 π α β
  have c01 := prop4_cov π α β (by decide : (0 : Fin 3) ≠ 1)
  have c02 := prop4_cov π α β (by decide : (0 : Fin 3) ≠ 2)
  have c12 := prop4_cov π α β (by decide : (1 : Fin 3) ≠ 2)
  obtain ⟨s0, t0⟩ := solve_rater (si := 1 - α 0) (ti := β 0) (di := del α β 0)
    (dj := del α β 1) (dk := del α β 2) (R := R) (k := k3 π α β) (c := cov3 π α β 1 2)
    (p := p3 π α β 0) hπ0 hπ1 hd1 hd2 rfl hR' hk c12 (p3_eq π α β 0)
  obtain ⟨s1, t1⟩ := solve_rater (si := 1 - α 1) (ti := β 1) (di := del α β 1)
    (dj := del α β 0) (dk := del α β 2) (R := R) (k := k3 π α β) (c := cov3 π α β 0 2)
    (p := p3 π α β 1) hπ0 hπ1 hd0 hd2 rfl (by rw [hR']; ring) (by rw [hk]; ring)
    c02 (p3_eq π α β 1)
  obtain ⟨s2, t2⟩ := solve_rater (si := 1 - α 2) (ti := β 2) (di := del α β 2)
    (dj := del α β 0) (dk := del α β 1) (R := R) (k := k3 π α β) (c := cov3 π α β 0 1)
    (p := p3 π α β 2) hπ0 hπ1 hd0 hd1 rfl (by rw [hR']; ring) (by rw [hk]; ring)
    c01 (p3_eq π α β 2)
  refine ⟨?_, s0, t0, s1, t1, s2, t2⟩
  have hπ : π ≠ 0 := hπ0.ne'
  have hπ' : 1 - π ≠ 0 := by linarith
  rw [hR', hk]
  field_simp
  ring

/-! ## The copying grader (§8) -/

/-- Indicator that two reports agree. -/
def same (a b : Bool) : ℝ := if a = b then 1 else 0

@[simp] lemma same_tt : same true true = 1 := rfl
@[simp] lemma same_tf : same true false = 0 := rfl
@[simp] lemma same_ft : same false true = 0 := rfl
@[simp] lemma same_ff : same false false = 1 := rfl

/-- Four raters in which rater 2 (index 1) copies rater 1 (index 0) with probability `ρ` and grades
independently (rates `α 1`, `β 1`) otherwise; raters 3 and 4 independent given `Y`. -/
def probCopy (π ρ : ℝ) (α β : Fin 4 → ℝ) (x0 x1 x2 x3 : Bool) : ℝ :=
  π * (bern (1 - α 0) x0 * (ρ * same x1 x0 + (1 - ρ) * bern (1 - α 1) x1) *
      bern (1 - α 2) x2 * bern (1 - α 3) x3) +
  (1 - π) * (bern (β 0) x0 * (ρ * same x1 x0 + (1 - ρ) * bern (β 1) x1) *
      bern (β 2) x2 * bern (β 3) x3)

/-- Expectation under the copying model. -/
def ECopy (π ρ : ℝ) (α β : Fin 4 → ℝ) (F : Bool → Bool → Bool → Bool → ℝ) : ℝ :=
  ∑ x0 : Bool, ∑ x1 : Bool, ∑ x2 : Bool, ∑ x3 : Bool, probCopy π ρ α β x0 x1 x2 x3 * F x0 x1 x2 x3

/-- Report of rater `i`. -/
def rep (i : Fin 4) (x0 x1 x2 x3 : Bool) : Bool := ![x0, x1, x2, x3] i

@[simp] lemma rep_0 (x0 x1 x2 x3 : Bool) : rep 0 x0 x1 x2 x3 = x0 := rfl
@[simp] lemma rep_1 (x0 x1 x2 x3 : Bool) : rep 1 x0 x1 x2 x3 = x1 := rfl
@[simp] lemma rep_2 (x0 x1 x2 x3 : Bool) : rep 2 x0 x1 x2 x3 = x2 := rfl
@[simp] lemma rep_3 (x0 x1 x2 x3 : Bool) : rep 3 x0 x1 x2 x3 = x3 := rfl

/-- Mean report of rater `i` under the copying model. -/
def meanCopy (π ρ : ℝ) (α β : Fin 4 → ℝ) (i : Fin 4) : ℝ :=
  ECopy π ρ α β fun x0 x1 x2 x3 => ind (rep i x0 x1 x2 x3)

/-- Covariance `c_ij` under the copying model. -/
def covCopy (π ρ : ℝ) (α β : Fin 4 → ℝ) (i j : Fin 4) : ℝ :=
  ECopy π ρ α β fun x0 x1 x2 x3 =>
    (ind (rep i x0 x1 x2 x3) - meanCopy π ρ α β i) * (ind (rep j x0 x1 x2 x3) - meanCopy π ρ α β j)

section Copy

variable (π ρ : ℝ) (α β : Fin 4 → ℝ)

theorem meanCopy_0 : meanCopy π ρ α β 0 = π * (1 - α 0) + (1 - π) * β 0 := by
  simp only [meanCopy, ECopy, probCopy, Fintype.sum_bool, rep_0, bern_true, bern_false, ind_true,
    ind_false, same_tt, same_tf, same_ft, same_ff]
  ring

theorem meanCopy_1 : meanCopy π ρ α β 1 =
    π * (ρ * (1 - α 0) + (1 - ρ) * (1 - α 1)) + (1 - π) * (ρ * β 0 + (1 - ρ) * β 1) := by
  simp only [meanCopy, ECopy, probCopy, Fintype.sum_bool, rep_1, bern_true, bern_false, ind_true,
    ind_false, same_tt, same_tf, same_ft, same_ff]
  ring

theorem meanCopy_2 : meanCopy π ρ α β 2 = π * (1 - α 2) + (1 - π) * β 2 := by
  simp only [meanCopy, ECopy, probCopy, Fintype.sum_bool, rep_2, bern_true, bern_false, ind_true,
    ind_false, same_tt, same_tf, same_ft, same_ff]
  ring

theorem meanCopy_3 : meanCopy π ρ α β 3 = π * (1 - α 3) + (1 - π) * β 3 := by
  simp only [meanCopy, ECopy, probCopy, Fintype.sum_bool, rep_3, bern_true, bern_false, ind_true,
    ind_false, same_tt, same_tf, same_ft, same_ff]
  ring

/-- `V₁ = π α₁(1 - α₁) + (1 - π) β₁(1 - β₁)`, the conditional variance of rater 1. -/
def V1 : ℝ := π * α 0 * (1 - α 0) + (1 - π) * β 0 * (1 - β 0)

/-- `δ̃₂ = ρ δ₁ + (1 - ρ) δ₂`. -/
def dTilde : ℝ := ρ * del α β 0 + (1 - ρ) * del α β 1

/-- **Copying grader, covariances.** `c₁₂ = u δ₁ δ̃₂ + ρ V₁`; the other five covariances keep
product form, with `δ̃₂` for rater 2. -/
theorem massCopy : ECopy π ρ α β (fun _ _ _ _ => 1) = 1 := by
  simp only [ECopy, probCopy, Fintype.sum_bool, bern_true, bern_false, same_tt, same_tf, same_ft,
    same_ff]
  ring

/-- `c_ij = E[X_i X_j] - p_i p_j` (the distribution sums to one). -/
theorem covCopy_raw (i j : Fin 4) :
    covCopy π ρ α β i j =
      ECopy π ρ α β (fun x0 x1 x2 x3 => ind (rep i x0 x1 x2 x3) * ind (rep j x0 x1 x2 x3)) -
        meanCopy π ρ α β i * meanCopy π ρ α β j := by
  have hm := massCopy π ρ α β
  have hi : meanCopy π ρ α β i = ECopy π ρ α β fun x0 x1 x2 x3 => ind (rep i x0 x1 x2 x3) := rfl
  have hj : meanCopy π ρ α β j = ECopy π ρ α β fun x0 x1 x2 x3 => ind (rep j x0 x1 x2 x3) := rfl
  simp only [covCopy, ECopy, Fintype.sum_bool] at hm hi hj ⊢
  linear_combination (meanCopy π ρ α β j) * hi + (meanCopy π ρ α β i) * hj +
    (meanCopy π ρ α β i * meanCopy π ρ α β j) * hm

/-- **Copying grader, covariances.** `c₁₂ = u δ₁ δ̃₂ + ρ V₁`; the other five covariances keep
product form, with `δ̃₂` for rater 2. -/
theorem covCopy_eq :
    covCopy π ρ α β 0 1 = π * (1 - π) * del α β 0 * dTilde ρ α β + ρ * V1 π α β ∧
    covCopy π ρ α β 0 2 = π * (1 - π) * del α β 0 * del α β 2 ∧
    covCopy π ρ α β 0 3 = π * (1 - π) * del α β 0 * del α β 3 ∧
    covCopy π ρ α β 1 2 = π * (1 - π) * dTilde ρ α β * del α β 2 ∧
    covCopy π ρ α β 1 3 = π * (1 - π) * dTilde ρ α β * del α β 3 ∧
    covCopy π ρ α β 2 3 = π * (1 - π) * del α β 2 * del α β 3 := by
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_⟩ <;>
  ( rw [covCopy_raw]
    simp only [meanCopy_0, meanCopy_1, meanCopy_2, meanCopy_3, ECopy, probCopy,
      Fintype.sum_bool, rep_0, rep_1, rep_2, rep_3, bern_true, bern_false, ind_true, ind_false,
      same_tt, same_tf, same_ft, same_ff, V1, dTilde, del, mul_zero, mul_one, add_zero, zero_add]
    ring )

/-- **Copying grader, residual (§8).** `c₁₂c₃₄ - c₁₃c₂₄ = ρ V₁ c₃₄` and `c₁₃c₂₄ = c₁₄c₂₃`. -/
theorem copy_grader_residual :
    covCopy π ρ α β 0 1 * covCopy π ρ α β 2 3 - covCopy π ρ α β 0 2 * covCopy π ρ α β 1 3 =
      ρ * V1 π α β * covCopy π ρ α β 2 3 ∧
    covCopy π ρ α β 0 2 * covCopy π ρ α β 1 3 = covCopy π ρ α β 0 3 * covCopy π ρ α β 1 2 := by
  obtain ⟨h01, h02, h03, h12, h13, h23⟩ := covCopy_eq π ρ α β
  rw [h01, h02, h03, h12, h13, h23]
  constructor <;> ring

/-- **Copying grader, detection.** The residual is non-zero whenever `ρ ≠ 0`, `V₁ ≠ 0`,
`0 < π < 1` and `δ₃δ₄ ≠ 0`; in particular at the balanced prior `π = 1/2`. -/
theorem copy_grader_detected (hρ : ρ ≠ 0) (hV : V1 π α β ≠ 0) (hπ0 : 0 < π) (hπ1 : π < 1)
    (hd : del α β 2 * del α β 3 ≠ 0) :
    covCopy π ρ α β 0 1 * covCopy π ρ α β 2 3 - covCopy π ρ α β 0 2 * covCopy π ρ α β 1 3 ≠ 0 := by
  rw [(copy_grader_residual π ρ α β).1, (covCopy_eq π ρ α β).2.2.2.2.2]
  have hπ : π ≠ 0 := hπ0.ne'
  have hπ' : 1 - π ≠ 0 := by linarith
  have hd2 : del α β 2 ≠ 0 := left_ne_zero_of_mul hd
  have hd3 : del α β 3 ≠ 0 := right_ne_zero_of_mul hd
  exact mul_ne_zero (mul_ne_zero hρ hV) (mul_ne_zero (mul_ne_zero (mul_ne_zero hπ hπ') hd2) hd3)

end Copy

/-! ## Asymmetric gold-noise inversion (§7) -/

section AsymInversion

variable (π a1 a0 f1 f0 e0 e1 : ℝ)

/-- Latent cell `(y, c, j, f)`: class `y` (`Pr[Y = 1] = π`); controller right `c`, with accuracy
`a1` on class 1 and `a0` on class 0; judge right `j`, wrong at rate `e0` when the controller is
right and `e1` when it is wrong (depending on correctness only); gold flipped `f`, at rate `f1` on
class 1 and `f0` on class 0, independent of `(c, j)` given `y`. -/
def acell (y c j f : Bool) : ℝ :=
  (if y then π else 1 - π) *
    (if c then (if y then a1 else a0) * (if j then 1 - e0 else e0)
      else (1 - (if y then a1 else a0)) * (if j then 1 - e1 else e1)) *
    (if f then (if y then f1 else f0) else 1 - (if y then f1 else f0))

/-- Measured controller accuracy `a' = Pr[C ⊕ F]`. -/
def asymAcc : ℝ :=
  ∑ y : Bool, ∑ c : Bool, ∑ j : Bool, ∑ f : Bool,
    if (c ^^ f) = true then acell π a1 a0 f1 f0 e0 e1 y c j f else 0

/-- Measured judge error `ε' = Pr[¬(J ⊕ F)]`. -/
def asymErr : ℝ :=
  ∑ y : Bool, ∑ c : Bool, ∑ j : Bool, ∑ f : Bool,
    if (j ^^ f) = false then acell π a1 a0 f1 f0 e0 e1 y c j f else 0

/-- Measured wrong–wrong rate `w = Pr[¬(C ⊕ F) ∧ ¬(J ⊕ F)]`. -/
def asymW : ℝ :=
  ∑ y : Bool, ∑ c : Bool, ∑ j : Bool, ∑ f : Bool,
    if (c ^^ f) = false ∧ (j ^^ f) = false then acell π a1 a0 f1 f0 e0 e1 y c j f else 0

/-- True and measured agreement rates `Pr[C = J]`, `Pr[C ⊕ F = J ⊕ F]`. -/
def asymAgree : ℝ :=
  ∑ y : Bool, ∑ c : Bool, ∑ j : Bool, ∑ f : Bool,
    if c = j then acell π a1 a0 f1 f0 e0 e1 y c j f else 0

def asymAgreeMeas : ℝ :=
  ∑ y : Bool, ∑ c : Bool, ∑ j : Bool, ∑ f : Bool,
    if (c ^^ f) = (j ^^ f) then acell π a1 a0 f1 f0 e0 e1 y c j f else 0

/-- **§7, measured quantities.** The note's expressions for `a'`, `ε'` and `w`, derived from the
sixteen latent cells; and the agreement rate is invariant whatever the law of `F`. -/
theorem asym_measured :
    asymAcc π a1 a0 f1 f0 e0 e1 =
      π * (a1 * (1 - f1) + (1 - a1) * f1) + (1 - π) * (a0 * (1 - f0) + (1 - a0) * f0) ∧
    asymErr π a1 a0 f1 f0 e0 e1 =
      π * (f1 + (1 - 2 * f1) * (a1 * e0 + (1 - a1) * e1)) +
        (1 - π) * (f0 + (1 - 2 * f0) * (a0 * e0 + (1 - a0) * e1)) ∧
    asymW π a1 a0 f1 f0 e0 e1 =
      π * ((1 - a1) * (1 - f1) * e1 + a1 * f1 * (1 - e0)) +
        (1 - π) * ((1 - a0) * (1 - f0) * e1 + a0 * f0 * (1 - e0)) ∧
    asymAgreeMeas π a1 a0 f1 f0 e0 e1 = asymAgree π a1 a0 f1 f0 e0 e1 := by
  refine ⟨?_, ?_, ?_, ?_⟩ <;>
    simp [asymAcc, asymErr, asymW, asymAgree, asymAgreeMeas, acell] <;> ring

/-- `F = Σ π_y f_y`. -/
def asymF : ℝ := π * f1 + (1 - π) * f0
/-- `E_a = Σ π_y (1 - 2f_y) a_y`. -/
def asymEa : ℝ := π * (1 - 2 * f1) * a1 + (1 - π) * (1 - 2 * f0) * a0
/-- `E_b = Σ π_y (1 - 2f_y)(1 - a_y)`. -/
def asymEb : ℝ := π * (1 - 2 * f1) * (1 - a1) + (1 - π) * (1 - 2 * f0) * (1 - a0)
/-- `G_a = Σ π_y a_y f_y`. -/
def asymGa : ℝ := π * a1 * f1 + (1 - π) * a0 * f0
/-- `G_b = Σ π_y (1 - a_y)(1 - f_y)`. -/
def asymGb : ℝ := π * (1 - a1) * (1 - f1) + (1 - π) * (1 - a0) * (1 - f0)

/-- **§7, asymmetric inversion.** With `Δ = E_a G_b + E_b G_a ≠ 0`:
`ε₁ = (E_a(w - G_a) + G_a(ε' - F))/Δ` and `ε₀ = (G_b(ε' - F) - E_b(w - G_a))/Δ`. -/
theorem asym_inversion
    (hΔ : asymEa π a1 a0 f1 f0 * asymGb π a1 a0 f1 f0 + asymEb π a1 a0 f1 f0 * asymGa π a1 a0 f1 f0
      ≠ 0) :
    e1 = (asymEa π a1 a0 f1 f0 * (asymW π a1 a0 f1 f0 e0 e1 - asymGa π a1 a0 f1 f0) +
        asymGa π a1 a0 f1 f0 * (asymErr π a1 a0 f1 f0 e0 e1 - asymF π f1 f0)) /
      (asymEa π a1 a0 f1 f0 * asymGb π a1 a0 f1 f0 + asymEb π a1 a0 f1 f0 * asymGa π a1 a0 f1 f0) ∧
    e0 = (asymGb π a1 a0 f1 f0 * (asymErr π a1 a0 f1 f0 e0 e1 - asymF π f1 f0) -
        asymEb π a1 a0 f1 f0 * (asymW π a1 a0 f1 f0 e0 e1 - asymGa π a1 a0 f1 f0)) /
      (asymEa π a1 a0 f1 f0 * asymGb π a1 a0 f1 f0 + asymEb π a1 a0 f1 f0 * asymGa π a1 a0 f1 f0) := by
  obtain ⟨-, hE, hW, -⟩ := asym_measured π a1 a0 f1 f0 e0 e1
  constructor <;> rw [eq_div_iff hΔ, hE, hW] <;> simp only [asymEa, asymEb, asymGa, asymGb, asymF] <;>
    ring

/-- **§7, symmetric case.** With `a₁ = a₀ = a` and `f₁ = f₀ = η`, `Δ = a(1 - a)(1 - 2η)`. -/
theorem asym_delta_symm (π a η : ℝ) :
    asymEa π a a η η * asymGb π a a η η + asymEb π a a η η * asymGa π a a η η =
      a * (1 - a) * (1 - 2 * η) := by
  simp only [asymEa, asymEb, asymGa, asymGb]; ring

end AsymInversion

end FeedbackChannel.Raters

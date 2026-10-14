import Mathlib.Tactic
import Mathlib.Analysis.SpecificLimits.Basic
import Mathlib.Data.Fintype.Option
import Mathlib.Algebra.BigOperators.Ring.Finset

/-!
# Naive reuse is a running maximum (multigen note, Proposition 1; signal note L5)

Source: `paper/evaluation_feedback_multigen.md`, draft 0.5, §1–§2; code
`src/spiral_ln/evaluation_feedback_multigen.py` (`transition_kernel`, `naive_closed_form`,
`ceiling_mass_closed_form`).

**The chain (§1).** The state is the incumbent's realized count `c` on a reused set of `n` items.
Each generation draws `K` candidates; `M` is the best candidate count. The policy accepts iff
`M > c + t(c)` for a threshold rule `t : ℕ → ℕ`; on acceptance the state becomes `M`. The naive rule
is `t ≡ 0`.

**Proposition 1.** With `t ≡ 0`, `c_G = max(c_0, M_1, …, M_G)`, the maximum of the `G K + 1` draws
(the initial incumbent is one draw). Consequences: (i) `ρ_G` is non-decreasing in `G`; (ii) the
increments `a_{m+1} - a_m` of `a_m = E[max of m draws]` are non-increasing; (iii)
`P(c_G = n) = 1 - (1 - p^n)^{G K + 1}`, so for `0 < p` the gap `ρ_G` increases to `1 - p`.

What is formalized here:
* `chain_naive`, `naive_reported_eq_max`: the deterministic statement about the update rule.
* `prob_reported_le`, `expect_reported`: the distributional consequence for `G K + 1` i.i.d. draws
  from an arbitrary law `w` on `{0, …, n}` (in particular `Bin(n, p)`): the reported count has CDF
  `F(j)^{G K + 1}` and mean `∑_{j<n} (1 - F(j)^{G K + 1})`, which is the mean of the maximum of
  `G K + 1` i.i.d. draws (`expect_max`).
* Consequences (i)–(iii): `aSeq_mono`, `aSeq_increment_antitone`, `expect_reported_mono`,
  `expect_reported_increment_antitone`, `prob_reported_eq_top`, `binomial_prob_reported_eq_top`,
  `tendsto_gap`.
* Proposition 4 (gate dominance under the null, coupling form): `chain_le_chain_naive`.

Probabilities are finite sums over draw configurations `D : ι → Fin (n + 1)` weighted by
`∏ i, w (D i)`, i.e. expectations under the product law of i.i.d. draws.
-/

namespace FeedbackChannel.MultigenRunningMax

open Finset Filter Topology

/-! ## The update rule -/

/-- One generation of the threshold policy: from incumbent count `c`, with `M` the best candidate
count of the generation, accept iff `M > c + t c`; the next state is `M` on acceptance and `c`
otherwise. -/
def step (t : ℕ → ℕ) (c M : ℕ) : ℕ := if c + t c < M then M else c

/-- The incumbent count after `g` generations from initial count `c0`, where `best g` is the best
candidate count of the `(g + 1)`-th generation. -/
def chain (t : ℕ → ℕ) (c0 : ℕ) (best : ℕ → ℕ) : ℕ → ℕ
  | 0 => c0
  | g + 1 => step t (chain t c0 best g) (best g)

/-- The naive rule `t ≡ 0`: accept whenever the best candidate beats the incumbent. -/
def naive : ℕ → ℕ := fun _ => 0

theorem step_naive (c M : ℕ) : step naive c M = max c M := by
  unfold step naive
  split_ifs with h
  · exact (max_eq_right (by omega)).symm
  · exact (max_eq_left (by omega)).symm

/-- **Proposition 1, deterministic form.** Under the naive rule the incumbent after `G` generations
is the running maximum `max(c_0, M_1, …, M_G)`. -/
theorem chain_naive (c0 : ℕ) (best : ℕ → ℕ) (G : ℕ) :
    chain naive c0 best G = max c0 ((range G).sup best) := by
  induction G with
  | zero => simp [chain]
  | succ G ih =>
    rw [chain, ih, step_naive, range_add_one, sup_insert]
    rw [max_assoc, max_comm ((range G).sup best) (best G)]

/-- **Proposition 4 (null, coupling form).** On the same draws, the chain under any threshold rule
stays below the naive chain: `c^t_G ≤ c^0_G` pointwise. -/
theorem chain_le_chain_naive (t : ℕ → ℕ) (c0 : ℕ) (best : ℕ → ℕ) (G : ℕ) :
    chain t c0 best G ≤ chain naive c0 best G := by
  induction G with
  | zero => simp [chain]
  | succ G ih =>
    rw [chain, chain, step_naive]
    unfold step
    split_ifs
    · exact le_max_right _ _
    · exact le_trans ih (le_max_left _ _)

/-! ## `K` candidates per generation: the `G K + 1` draws -/

/-- Index set of the draws of `G` generations of `K` candidates: `none` is the initial incumbent
(scored on the reused set like every candidate), `some (g, k)` is candidate `k` of generation `g`. -/
abbrev Draw (G K : ℕ) := Option (Fin G × Fin K)

theorem card_draw (G K : ℕ) : Fintype.card (Draw G K) = G * K + 1 := by
  simp

/-- The best candidate count of generation `g` (zero for `g ≥ G`, never used). -/
def bestOf {G K : ℕ} (D : Draw G K → ℕ) (g : ℕ) : ℕ :=
  if h : g < G then univ.sup fun k : Fin K => D (some (⟨g, h⟩, k)) else 0

/-- **Proposition 1.** With `t ≡ 0` and `K` candidates per generation, the reported count after `G`
generations is the maximum of all `G K + 1` draws (initial incumbent and every candidate). -/
theorem naive_reported_eq_max {G K : ℕ} (D : Draw G K → ℕ) :
    chain naive (D none) (bestOf D) G = univ.sup D := by
  rw [chain_naive]
  apply le_antisymm
  · apply max_le
    · exact le_sup (f := D) (mem_univ none)
    · apply Finset.sup_le
      intro g hg
      rw [mem_range] at hg
      simp only [bestOf, dite_eq_left hg]
      apply Finset.sup_le
      intro k _
      exact le_sup (f := D) (mem_univ _)
  · apply Finset.sup_le
    rintro (_ | ⟨g, k⟩) _
    · exact le_max_left _ _
    · apply le_max_of_le_right
      calc D (some (g, k)) ≤ bestOf D g := by
            simp only [bestOf, dite_eq_left g.isLt]
            exact le_sup (f := fun k : Fin K => D (some (⟨g.val, g.isLt⟩, k))) (mem_univ k)
        _ ≤ (range G).sup (bestOf D) := le_sup (mem_range.mpr g.isLt)

/-! ## The law of the reported count -/

section Law

variable {n : ℕ} (w : Fin (n + 1) → ℝ)

/-- CDF `F(j) = P(X ≤ j)` of one draw with law `w` on counts `{0, …, n}`. -/
def cdf (j : ℕ) : ℝ := ∑ x : Fin (n + 1), if x.val ≤ j then w x else 0

/-- Probability of an event of i.i.d. draws `D : ι → Fin (n + 1)`, each with law `w`. -/
def prob {ι : Type*} [Fintype ι] [DecidableEq ι] (E : (ι → Fin (n + 1)) → Prop)
    [DecidablePred E] : ℝ :=
  ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * if E D then 1 else 0

/-- Expectation of `f` under i.i.d. draws `D : ι → Fin (n + 1)`, each with law `w`. -/
def expect {ι : Type*} [Fintype ι] [DecidableEq ι] (f : (ι → Fin (n + 1)) → ℝ) : ℝ :=
  ∑ D : ι → Fin (n + 1), (∏ i, w (D i)) * f D

/-- The maximum count among the draws. -/
def maxDraw {ι : Type*} [Fintype ι] (D : ι → Fin (n + 1)) : ℕ := univ.sup fun i => (D i).val

theorem maxDraw_le {ι : Type*} [Fintype ι] (D : ι → Fin (n + 1)) : maxDraw D ≤ n :=
  Finset.sup_le fun i _ => Nat.lt_succ_iff.mp (D i).isLt

theorem maxDraw_le_iff {ι : Type*} [Fintype ι] (D : ι → Fin (n + 1)) (j : ℕ) :
    maxDraw D ≤ j ↔ ∀ i, (D i).val ≤ j := by
  simp [maxDraw, Finset.sup_le_iff]

theorem total_mass {ι : Type*} [Fintype ι] [DecidableEq ι] (hw : ∑ x, w x = 1) :
    ∑ D : ι → Fin (n + 1), ∏ i, w (D i) = 1 := by
  have h := Finset.prod_univ_sum (fun _ : ι => (univ : Finset (Fin (n + 1)))) (fun _ x => w x)
  rw [Fintype.piFinset_univ] at h
  rw [← h]
  simp [hw]

/-- The maximum of i.i.d. draws: `P(max ≤ j) = F(j)^{|ι|}`. -/
theorem prob_all_le {ι : Type*} [Fintype ι] [DecidableEq ι] (j : ℕ) :
    prob w (fun D : ι → Fin (n + 1) => ∀ i, (D i).val ≤ j) = cdf w j ^ Fintype.card ι := by
  unfold prob cdf
  rw [← Finset.card_univ, ← Finset.prod_const, Finset.prod_univ_sum, Fintype.piFinset_univ]
  apply Finset.sum_congr rfl
  intro D _
  by_cases h : ∀ i, (D i).val ≤ j
  · rw [ite_eq_left h, mul_one]
    exact Finset.prod_congr rfl fun i _ => (ite_eq_left (h i)).symm
  · rw [ite_eq_right h, mul_zero]
    obtain ⟨i, hi⟩ := not_forall.mp h
    exact (Finset.prod_eq_zero (mem_univ i) (ite_eq_right hi)).symm

theorem prob_not {ι : Type*} [Fintype ι] [DecidableEq ι] (hw : ∑ x, w x = 1)
    (E : (ι → Fin (n + 1)) → Prop) [DecidablePred E] :
    prob w (fun D => ¬ E D) = 1 - prob w E := by
  unfold prob
  have ht := total_mass w hw (ι := ι)
  rw [eq_sub_iff_add_eq, ← Finset.sum_add_distrib]
  conv_rhs => rw [← ht]
  apply Finset.sum_congr rfl
  intro D _
  by_cases h : E D <;> simp [h]

theorem tail_sum (x n : ℕ) (hx : x ≤ n) :
    (∑ j ∈ range n, if x ≤ j then (0 : ℝ) else 1) = x := by
  rw [← Finset.sum_range_add_sum_Ico _ hx]
  have h1 : (∑ j ∈ range x, if x ≤ j then (0 : ℝ) else 1) = ∑ j ∈ range x, (1 : ℝ) :=
    Finset.sum_congr rfl fun j hj => ite_eq_right (by rw [mem_range] at hj; omega)
  have h2 : (∑ j ∈ Ico x n, if x ≤ j then (0 : ℝ) else 1) = ∑ j ∈ Ico x n, (0 : ℝ) :=
    Finset.sum_congr rfl fun j hj => ite_eq_left (mem_Ico.mp hj).1
  rw [h1, h2]
  simp

/-- `a_m`: the tail-sum form of the mean of the maximum of `m` i.i.d. draws. -/
def aSeq (m : ℕ) : ℝ := ∑ j ∈ range n, (1 - cdf w j ^ m)

/-- The mean of the maximum of i.i.d. draws indexed by `ι` is `a_{|ι|}`. -/
theorem expect_max {ι : Type*} [Fintype ι] [DecidableEq ι] (hw : ∑ x, w x = 1) :
    expect w (fun D : ι → Fin (n + 1) => (maxDraw D : ℝ)) = aSeq w (Fintype.card ι) := by
  unfold expect aSeq
  have key : ∀ D : ι → Fin (n + 1), (maxDraw D : ℝ) =
      ∑ j ∈ range n, if (∀ i, (D i).val ≤ j) then (0 : ℝ) else 1 := by
    intro D
    rw [← tail_sum (maxDraw D) n (maxDraw_le D)]
    apply Finset.sum_congr rfl
    intro j _
    simp only [maxDraw_le_iff]
  simp_rw [key, Finset.mul_sum]
  rw [Finset.sum_comm]
  apply Finset.sum_congr rfl
  intro j _
  rw [← prob_all_le w j (ι := ι), ← prob_not w hw]
  unfold prob
  apply Finset.sum_congr rfl
  intro D _
  by_cases h : ∀ i, (D i).val ≤ j <;> simp [h]

/-- The reported count under naive reuse, as a function of the `G K + 1` draws. -/
def reported {G K : ℕ} (D : Draw G K → Fin (n + 1)) : ℕ :=
  chain naive (D none).val (bestOf fun i => (D i).val) G

theorem reported_eq_maxDraw {G K : ℕ} (D : Draw G K → Fin (n + 1)) :
    reported D = maxDraw D :=
  naive_reported_eq_max (fun i => (D i).val)

/-- **Proposition 1, law.** Under naive reuse with i.i.d. draws of law `w`, the reported count after
`G` generations of `K` candidates has CDF `F(j)^{G K + 1}`: it is distributed as the maximum of
`G K + 1` i.i.d. draws. -/
theorem prob_reported_le (G K j : ℕ) :
    prob w (fun D : Draw G K → Fin (n + 1) => reported D ≤ j) = cdf w j ^ (G * K + 1) := by
  rw [← card_draw G K, ← prob_all_le w j]
  unfold prob
  apply Finset.sum_congr rfl
  intro D _
  simp only [reported_eq_maxDraw, maxDraw_le_iff]

/-- **Proposition 1, mean.** `E[c_G] = a_{G K + 1}`, the mean of the maximum of `G K + 1` i.i.d.
draws (`expect_max` with `ι = Fin (G K + 1)`); so `ρ_G = E[c_G]/n - p` is the one-generation
selection gap with `K` replaced by `G K + 1`. -/
theorem expect_reported (hw : ∑ x, w x = 1) (G K : ℕ) :
    expect w (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) = aSeq w (G * K + 1) := by
  rw [← card_draw G K, ← expect_max w hw]
  unfold expect
  apply Finset.sum_congr rfl
  intro D _
  simp only [reported_eq_maxDraw]

theorem expect_reported_eq_expect_max (hw : ∑ x, w x = 1) (G K : ℕ) :
    expect w (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) =
      expect w (fun D : Fin (G * K + 1) → Fin (n + 1) => (maxDraw D : ℝ)) := by
  rw [expect_reported w hw, expect_max w hw, Fintype.card_fin]

/-! ### Consequences (i)–(ii) -/

variable {w}

theorem cdf_nonneg (hw0 : ∀ x, 0 ≤ w x) (j : ℕ) : 0 ≤ cdf w j :=
  Finset.sum_nonneg fun x _ => by split_ifs <;> simp [hw0 x]

theorem cdf_le_one (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (j : ℕ) : cdf w j ≤ 1 := by
  rw [← hw]
  exact Finset.sum_le_sum fun x _ => by split_ifs <;> simp [hw0 x]

/-- (ii) The increment of `a_m` is `∑_j F(j)^m (1 - F(j)) = E[(X - M_m)^+]` in tail-sum form. -/
theorem aSeq_succ_sub (m : ℕ) :
    aSeq w (m + 1) - aSeq w m = ∑ j ∈ range n, cdf w j ^ m * (1 - cdf w j) := by
  unfold aSeq
  rw [← Finset.sum_sub_distrib]
  apply Finset.sum_congr rfl
  intro j _
  ring

/-- (i) `a_m` is non-decreasing in the number of draws. -/
theorem aSeq_mono (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (m : ℕ) :
    aSeq w m ≤ aSeq w (m + 1) := by
  have := aSeq_succ_sub (w := w) m
  have h : 0 ≤ ∑ j ∈ range n, cdf w j ^ m * (1 - cdf w j) :=
    Finset.sum_nonneg fun j _ =>
      mul_nonneg (pow_nonneg (cdf_nonneg hw0 j) _) (by linarith [cdf_le_one hw0 hw j])
  linarith

/-- (ii) The increments of `a_m` are non-increasing. -/
theorem aSeq_increment_antitone (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (m : ℕ) :
    aSeq w (m + 2) - aSeq w (m + 1) ≤ aSeq w (m + 1) - aSeq w m := by
  rw [aSeq_succ_sub, aSeq_succ_sub]
  apply Finset.sum_le_sum
  intro j _
  have h0 := cdf_nonneg hw0 j
  have h1 := cdf_le_one hw0 hw j
  apply mul_le_mul_of_nonneg_right _ (by linarith)
  exact pow_le_pow_of_le_one h0 h1 (Nat.le_succ m)

theorem aSeq_mono' (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) {m m' : ℕ} (h : m ≤ m') :
    aSeq w m ≤ aSeq w m' := by
  induction h with
  | refl => exact le_rfl
  | step _ ih => exact ih.trans (aSeq_mono hw0 hw _)

/-- Concavity of `a` transfers to blocks of `K` draws. -/
theorem aSeq_block_antitone (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (m K : ℕ) :
    aSeq w (m + 2 * K) - aSeq w (m + K) ≤ aSeq w (m + K) - aSeq w m := by
  have tele : ∀ a : ℕ, aSeq w (a + K) - aSeq w a =
      ∑ r ∈ range K, (aSeq w (a + (r + 1)) - aSeq w (a + r)) := by
    intro a
    rw [Finset.sum_range_sub (fun r => aSeq w (a + r))]
    simp
  have anti : ∀ a b : ℕ, a ≤ b →
      aSeq w (b + 1) - aSeq w b ≤ aSeq w (a + 1) - aSeq w a := by
    intro a b hab
    induction hab with
    | refl => exact le_rfl
    | step _ ih =>
      exact (aSeq_increment_antitone hw0 hw _).trans ih
  rw [show m + 2 * K = (m + K) + K by ring, tele (m + K), tele m]
  apply Finset.sum_le_sum
  intro r _
  have := anti (m + r) (m + K + r) (by omega)
  simpa [add_assoc, add_comm, add_left_comm] using this

/-- (i) for the chain: `E[c_G]` (hence `ρ_G = E[c_G]/n - p`) is non-decreasing in `G`. -/
theorem expect_reported_mono (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (G K : ℕ) :
    expect w (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) ≤
      expect w (fun D : Draw (G + 1) K → Fin (n + 1) => (reported D : ℝ)) := by
  rw [expect_reported w hw, expect_reported w hw]
  exact aSeq_mono' hw0 hw (by nlinarith)

/-- (ii) for the chain: the per-generation increments of `E[c_G]` are non-increasing in `G`. -/
theorem expect_reported_increment_antitone (hw0 : ∀ x, 0 ≤ w x) (hw : ∑ x, w x = 1) (G K : ℕ) :
    expect w (fun D : Draw (G + 2) K → Fin (n + 1) => (reported D : ℝ)) -
        expect w (fun D : Draw (G + 1) K → Fin (n + 1) => (reported D : ℝ)) ≤
      expect w (fun D : Draw (G + 1) K → Fin (n + 1) => (reported D : ℝ)) -
        expect w (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) := by
  rw [expect_reported w hw, expect_reported w hw, expect_reported w hw]
  have := aSeq_block_antitone hw0 hw (G * K + 1) K
  rw [show (G + 2) * K + 1 = G * K + 1 + 2 * K by ring,
    show (G + 1) * K + 1 = G * K + 1 + K by ring]
  exact this

/-! ### Consequence (iii): the ceiling and the limit -/

variable (w) in
/-- (iii) `P(c_G = n) = 1 - F(n-1)^{G K + 1}`. -/
theorem prob_reported_eq_top (hw : ∑ x, w x = 1) (hn : 1 ≤ n) (G K : ℕ) :
    prob w (fun D : Draw G K → Fin (n + 1) => reported D = n) =
      1 - cdf w (n - 1) ^ (G * K + 1) := by
  rw [← prob_reported_le w G K (n - 1), ← prob_not w hw]
  unfold prob
  apply Finset.sum_congr rfl
  intro D _
  have := maxDraw_le D
  rw [← reported_eq_maxDraw] at this
  by_cases h : reported D = n
  · rw [ite_eq_left h, ite_eq_left (by omega)]
  · rw [ite_eq_right h, ite_eq_right (by omega)]

/-- The binomial law `Bin(n, p)` on `{0, …, n}`. -/
noncomputable def binomial (n : ℕ) (p : ℝ) (x : Fin (n + 1)) : ℝ :=
  (n.choose x.val : ℝ) * p ^ x.val * (1 - p) ^ (n - x.val)

theorem binomial_nonneg (n : ℕ) {p : ℝ} (hp0 : 0 ≤ p) (hp1 : p ≤ 1) (x : Fin (n + 1)) :
    0 ≤ binomial n p x := by
  unfold binomial
  have : 0 ≤ 1 - p := by linarith
  positivity

theorem binomial_sum (n : ℕ) (p : ℝ) : ∑ x, binomial n p x = 1 := by
  unfold binomial
  rw [Fin.sum_univ_eq_sum_range (fun x => (n.choose x : ℝ) * p ^ x * (1 - p) ^ (n - x)) (n + 1)]
  have h := add_pow p (1 - p) n
  rw [show p + (1 - p) = 1 by ring, one_pow] at h
  exact (Finset.sum_congr rfl (fun x _ => by ring)).trans h.symm

theorem binomial_cdf_pred (n : ℕ) (hn : 1 ≤ n) (p : ℝ) :
    cdf (binomial n p) (n - 1) = 1 - p ^ n := by
  unfold cdf
  rw [← binomial_sum n p, Fin.sum_univ_castSucc, Fin.sum_univ_castSucc (fun x => binomial n p x)]
  have h1 : ∀ x : Fin n, (if (Fin.castSucc x).val ≤ n - 1 then binomial n p (Fin.castSucc x)
      else 0) = binomial n p (Fin.castSucc x) := fun x => ite_eq_left (by simp; omega)
  have h2 : (if (Fin.last n).val ≤ n - 1 then binomial n p (Fin.last n) else 0) = 0 :=
    ite_eq_right (by simp; omega)
  simp only [h1, h2]
  simp [binomial]

/-- (iii) for the binomial null: `P(c_G = n) = 1 - (1 - p^n)^{G K + 1}`. -/
theorem binomial_prob_reported_eq_top (hn : 1 ≤ n) (p : ℝ) (G K : ℕ) :
    prob (binomial n p) (fun D : Draw G K → Fin (n + 1) => reported D = n) =
      1 - (1 - p ^ n) ^ (G * K + 1) := by
  rw [prob_reported_eq_top _ (binomial_sum n p) hn, binomial_cdf_pred n hn]

/-- (iii) For fixed `n ≥ 1`, `K ≥ 1` and `0 < p ≤ 1`, the naive readout gap
`ρ_G = E[c_G]/n - p` tends to `1 - p` as `G → ∞` (and is non-decreasing, `expect_reported_mono`):
bounded by the lattice, never stationary. -/
theorem tendsto_gap (hn : 1 ≤ n) {p : ℝ} (hp0 : 0 < p) (hp1 : p ≤ 1) {K : ℕ} (hK : 1 ≤ K) :
    Tendsto (fun G : ℕ =>
        expect (binomial n p) (fun D : Draw G K → Fin (n + 1) => (reported D : ℝ)) / n - p)
      atTop (𝓝 (1 - p)) := by
  have hw0 := binomial_nonneg n hp0.le hp1
  have hw := binomial_sum n p
  simp_rw [expect_reported _ hw]
  have hlim : Tendsto (fun G : ℕ => aSeq (binomial n p) (G * K + 1)) atTop (𝓝 (n : ℝ)) := by
    unfold aSeq
    have : (n : ℝ) = ∑ j ∈ range n, (1 - 0) := by simp
    rw [this]
    apply tendsto_finsetSum
    intro j hj
    rw [mem_range] at hj
    apply Tendsto.const_sub
    have hF0 := cdf_nonneg hw0 j
    have hF1 : cdf (binomial n p) j < 1 := by
      have hmono : cdf (binomial n p) j ≤ cdf (binomial n p) (n - 1) := by
        unfold cdf
        apply Finset.sum_le_sum
        intro x _
        by_cases hx : x.val ≤ j
        · rw [ite_eq_left hx, ite_eq_left (by omega)]
        · rw [ite_eq_right hx]; split_ifs <;> simp [hw0 x]
      rw [binomial_cdf_pred n hn] at hmono
      have : 0 < p ^ n := pow_pos hp0 n
      linarith
    have hpow := tendsto_pow_atTop_nhds_zero_of_lt_one hF0 hF1
    have hidx : Tendsto (fun G : ℕ => G * K + 1) atTop atTop := by
      apply tendsto_atTop_mono (f := fun G : ℕ => G)
      · intro G; nlinarith
      · exact tendsto_id
    exact hpow.comp hidx
  have hn' : (n : ℝ) ≠ 0 := by positivity
  have := (hlim.div_const (n : ℝ)).sub_const p
  rwa [div_self hn'] at this

end Law

end FeedbackChannel.MultigenRunningMax

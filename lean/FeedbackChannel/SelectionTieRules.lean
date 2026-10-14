import FeedbackChannel.SelectionContainment

/-!
# Theorem A (tie rules) and Theorem B for every tie rule

Source: `paper/selection_law_kl_containment.md`, draft 0.3, §1–§2.

Draw `ω₁, …, ω_K` i.i.d. from `p₀` and keep one of maximal score. A *tie rule* is a kept index
`J = pick(r, (S ω₁, …, S ω_K))`, a function of the score vector and of randomness `r ~ ν`
independent of the sample, lying in the argmax set (the first-index rule takes `r` trivial; the
uniform rule takes `r` a uniformly random order).

**Theorem A.** The kept record has law `π_K(ω) = p₀(ω) m_K(S ω)/q(S ω)` (`keptLaw_eq`), whatever the
tie rule. The proof here is the conditioning argument of the note made combinatorial: swapping the
kept record with an independent record of the same score is a weight-preserving bijection
(`swap_sum`), which gives `P(ω_J = ω) q(S ω) = p₀(ω) P(max score = S ω)`, and
`P(max score = s) = F(s)^K - F(s-)^K` (`prob_max_score_eq`).

**Theorem B for every tie rule** (`theoremB_every_tie_rule`): `KL(law of the kept record ‖ p₀) ≤
ln K - (K - 1)/K`.
-/

namespace FeedbackChannel.SelectionTieRules

open Finset Real FeedbackChannel.SelectionContainment

variable {Ω : Type*} [Fintype Ω] [DecidableEq Ω] (p0 : Ω → ℝ) (S : Ω → ℝ) {K : ℕ}

/-- A tie rule with auxiliary randomness in `R`: the kept index is in the argmax set. -/
structure TieRule (R : Type*) (K : ℕ) where
  pick : R → (Fin K → ℝ) → Fin K
  pick_max : ∀ (r : R) (v : Fin K → ℝ) (k : Fin K), v k ≤ v (pick r v)

/-- Law of the kept record: `K` i.i.d. draws with law `p₀`, independent randomness `r ~ ν`. -/
def keptLaw {R : Type*} [Fintype R] (ν : R → ℝ) (T : TieRule R K) (ω0 : Ω) : ℝ :=
  ∑ r, ν r * ∑ ω : Fin K → Ω, (∏ k, p0 (ω k)) * if ω (T.pick r (S ∘ ω)) = ω0 then 1 else 0

/-- `P(every draw satisfies P) = P(P)^K` for i.i.d. draws. -/
theorem prob_all (P : Ω → Prop) [DecidablePred P] :
    ∑ ω : Fin K → Ω, (∏ k, p0 (ω k)) * (if ∀ k, P (ω k) then 1 else 0) =
      (∑ x, if P x then p0 x else 0) ^ K := by
  conv_rhs => rw [← Finset.card_fin K, ← Finset.prod_const]
  rw [Finset.prod_univ_sum, Fintype.piFinset_univ]
  apply Finset.sum_congr rfl
  intro ω _
  by_cases h : ∀ k, P (ω k)
  · rw [ite_eq_left h, mul_one]
    exact Finset.prod_congr rfl fun k _ => (ite_eq_left (h k)).symm
  · rw [ite_eq_right h, mul_zero]
    obtain ⟨k, hk⟩ := not_forall.mp h
    exact (Finset.prod_eq_zero (mem_univ k) (ite_eq_right hk)).symm

/-- The law of the maximum of `K` i.i.d. scores, read off any argmax index:
`P(S(ω_J) = s) = F(s)^K - F(s-)^K = m_K(s)`. -/
theorem prob_max_score_eq (J : (Fin K → ℝ) → Fin K) (hJ : ∀ (v : Fin K → ℝ) (k : Fin K), v k ≤ v (J v)) (s0 : ℝ) :
    ∑ ω : Fin K → Ω, (∏ k, p0 (ω k)) * (if S (ω (J (S ∘ ω))) = s0 then 1 else 0) =
      maxLaw p0 S K s0 := by
  have hpt : ∀ ω : Fin K → Ω, (if S (ω (J (S ∘ ω))) = s0 then (1 : ℝ) else 0) =
      (if ∀ k, S (ω k) ≤ s0 then 1 else 0) - (if ∀ k, S (ω k) < s0 then 1 else 0) := by
    intro ω
    have hmax : ∀ k, S (ω k) ≤ S (ω (J (S ∘ ω))) := fun k => hJ (S ∘ ω) k
    rcases lt_trichotomy (S (ω (J (S ∘ ω)))) s0 with h | h | h
    · rw [ite_eq_right h.ne, ite_eq_left (fun k => (hmax k).trans h.le),
        ite_eq_left (fun k => lt_of_le_of_lt (hmax k) h)]
      ring
    · rw [ite_eq_left h, ite_eq_left (fun k => h ▸ hmax k), ite_eq_right (fun hall => (hall _).ne h)]
      ring
    · rw [ite_eq_right h.ne', ite_eq_right (fun hall => not_le.mpr h (hall _)),
        ite_eq_right (fun hall => (lt_asymm h) (hall _))]
      ring
  simp_rw [hpt, mul_sub, Finset.sum_sub_distrib]
  rw [prob_all p0 (fun x => S x ≤ s0), prob_all p0 (fun x => S x < s0)]
  unfold maxLaw cdf cdfLt
  rw [Finset.sum_filter, Finset.sum_filter]

/-- Swap the kept record (index `J`) with an extra record. -/
def swap (J : (Fin K → ℝ) → Fin K) (x : (Fin K → Ω) × Ω) : (Fin K → Ω) × Ω :=
  (Function.update x.1 (J (S ∘ x.1)) x.2, x.1 (J (S ∘ x.1)))

omit [Fintype Ω] [DecidableEq Ω] in
theorem score_update (ω : Fin K → Ω) (j : Fin K) (v : Ω) (h : S v = S (ω j)) :
    S ∘ Function.update ω j v = S ∘ ω := by
  rw [Function.comp_update, h]
  exact Function.update_eq_self j (S ∘ ω)

/-- **The swap bijection.** Exchanging the kept record with an independent record of the same
score preserves the product weight and maps `{ω_J = ω₀, S ω' = S ω₀}` onto
`{S(ω_J) = S ω₀, ω' = ω₀}`. -/
theorem swap_sum (J : (Fin K → ℝ) → Fin K) (ω0 : Ω) :
    ∑ x ∈ univ.filter (fun x : (Fin K → Ω) × Ω => x.1 (J (S ∘ x.1)) = ω0 ∧ S x.2 = S ω0),
        (∏ k, p0 (x.1 k)) * p0 x.2 =
      ∑ x ∈ univ.filter (fun x : (Fin K → Ω) × Ω => S (x.1 (J (S ∘ x.1))) = S ω0 ∧ x.2 = ω0),
        (∏ k, p0 (x.1 k)) * p0 x.2 := by
  apply Finset.sum_nbij' (swap S J) (swap S J)
  · rintro ⟨ω, ω'⟩ hx
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hx ⊢
    obtain ⟨h1, h2⟩ := hx
    have hS := score_update S ω (J (S ∘ ω)) ω' (by rw [h2, h1])
    simp only [swap, hS, Function.update_self]
    exact ⟨h2, h1⟩
  · rintro ⟨ω, z⟩ hx
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hx ⊢
    obtain ⟨h1, h2⟩ := hx
    have hS := score_update S ω (J (S ∘ ω)) z (by rw [h2, h1])
    simp only [swap, hS, Function.update_self]
    exact ⟨h2, h1⟩
  · rintro ⟨ω, ω'⟩ hx
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hx
    obtain ⟨h1, h2⟩ := hx
    have hS := score_update S ω (J (S ∘ ω)) ω' (by rw [h2, h1])
    simp only [swap, hS, Function.update_self, Function.update_idem, Function.update_eq_self]
  · rintro ⟨ω, z⟩ hx
    simp only [Finset.mem_filter, Finset.mem_univ, true_and] at hx
    obtain ⟨h1, h2⟩ := hx
    have hS := score_update S ω (J (S ∘ ω)) z (by rw [h2, h1])
    simp only [swap, hS, Function.update_self, Function.update_idem, Function.update_eq_self]
  · rintro ⟨ω, ω'⟩ _
    simp only [swap]
    set j := J (S ∘ ω)
    have hupd : ∀ k, p0 (Function.update ω j ω' k) =
        Function.update (fun k => p0 (ω k)) j (p0 ω') k :=
      fun k => Function.apply_update (fun _ => p0) ω j ω' k
    simp_rw [hupd]
    rw [Finset.prod_update_of_mem (mem_univ j),
      Finset.prod_eq_mul_prod_sdiff_singleton_of_mem (mem_univ j) (fun k => p0 (ω k))]
    ring

/-- `P(ω_J = ω₀) · q(S ω₀) = p₀(ω₀) · m_K(S ω₀)` for every deterministic argmax rule. -/
theorem kept_mul_scoreMass (J : (Fin K → ℝ) → Fin K) (hJ : ∀ (v : Fin K → ℝ) (k : Fin K), v k ≤ v (J v)) (ω0 : Ω) :
    (∑ ω : Fin K → Ω, (∏ k, p0 (ω k)) * if ω (J (S ∘ ω)) = ω0 then 1 else 0) *
        scoreMass p0 S (S ω0) =
      p0 ω0 * maxLaw p0 S K (S ω0) := by
  rw [← prob_max_score_eq p0 S J hJ (S ω0)]
  unfold scoreMass
  rw [Finset.sum_filter, Finset.sum_mul_sum, Finset.mul_sum]
  have hR : ∀ ω : Fin K → Ω, p0 ω0 * ((∏ k, p0 (ω k)) *
      (if S (ω (J (S ∘ ω))) = S ω0 then 1 else 0)) =
      ∑ z, (∏ k, p0 (ω k)) * p0 z * (if S (ω (J (S ∘ ω))) = S ω0 ∧ z = ω0 then 1 else 0) := by
    intro ω
    rw [Finset.sum_eq_single ω0]
    · by_cases h : S (ω (J (S ∘ ω))) = S ω0
      · rw [ite_eq_left h, ite_eq_left ⟨h, rfl⟩]; ring
      · rw [ite_eq_right h, ite_eq_right (fun hh => h hh.1)]; ring
    · intro z _ hz
      rw [ite_eq_right (fun hh => hz hh.2), mul_zero]
    · intro h; exact absurd (mem_univ ω0) h
  simp_rw [hR]
  have hL : ∀ (ω : Fin K → Ω) (z : Ω), (∏ k, p0 (ω k)) * (if ω (J (S ∘ ω)) = ω0 then 1 else 0) *
      (if S z = S ω0 then p0 z else 0) =
      (∏ k, p0 (ω k)) * p0 z * (if ω (J (S ∘ ω)) = ω0 ∧ S z = S ω0 then 1 else 0) := by
    intro ω z
    by_cases h1 : ω (J (S ∘ ω)) = ω0 <;> by_cases h2 : S z = S ω0 <;> simp [h1, h2]
  simp_rw [hL]
  have hswap := swap_sum p0 S J ω0
  rw [Finset.sum_filter, Finset.sum_filter, Fintype.sum_prod_type, Fintype.sum_prod_type] at hswap
  dsimp only at hswap
  simp only [mul_ite, mul_one, mul_zero]
  exact hswap

/-- **Theorem A.** For every tie rule (deterministic in the score vector up to independent
randomness `r ~ ν`, with the kept index in the argmax set), the kept record has law
`π_K(ω) = p₀(ω) m_K(S ω)/q(S ω)`. -/
theorem keptLaw_eq (hp0 : ∀ ω, 0 ≤ p0 ω) {R : Type*} [Fintype R] (ν : R → ℝ)
    (hν : ∑ r, ν r = 1) (T : TieRule R K) (ω0 : Ω) :
    keptLaw p0 S ν T ω0 = bestOfK p0 S K ω0 := by
  have hr : ∀ r, (∑ ω : Fin K → Ω, (∏ k, p0 (ω k)) * if ω (T.pick r (S ∘ ω)) = ω0 then 1 else 0)
      = bestOfK p0 S K ω0 := by
    intro r
    unfold bestOfK
    by_cases hq : scoreMass p0 S (S ω0) = 0
    · have hp : p0 ω0 = 0 :=
        le_antisymm (hq ▸ p0_le_scoreMass p0 S hp0 ω0) (hp0 ω0)
      rw [hq, div_zero]
      apply Finset.sum_eq_zero
      intro ω _
      by_cases h : ω (T.pick r (S ∘ ω)) = ω0
      · rw [ite_eq_left h, mul_one]
        exact Finset.prod_eq_zero (mem_univ (T.pick r (S ∘ ω))) (by rw [h, hp])
      · rw [ite_eq_right h, mul_zero]
    · rw [eq_div_iff hq]
      exact kept_mul_scoreMass p0 S (T.pick r) (T.pick_max r) ω0
  unfold keptLaw
  simp_rw [hr]
  rw [← Finset.sum_mul, hν, one_mul]

/-- **Theorem B, for every tie rule.** For every finite base law `p₀`, score `S`, `K ≥ 1` and tie
rule, `KL(law of the kept record ‖ p₀) ≤ ln K - (K - 1)/K`. -/
theorem theoremB_every_tie_rule (hp0 : ∀ ω, 0 ≤ p0 ω) (hsum : ∑ ω, p0 ω = 1) (hK : 1 ≤ K)
    {R : Type*} [Fintype R] (ν : R → ℝ) (hν : ∑ r, ν r = 1) (T : TieRule R K) :
    kl (keptLaw p0 S ν T) p0 ≤ lam K := by
  have : keptLaw p0 S ν T = bestOfK p0 S K := funext (keptLaw_eq p0 S hp0 ν hν T)
  rw [this]
  exact theoremB p0 S hp0 hsum hK

/-- **Theorem B, equality case, for every tie rule:** `KL = λ_K` iff `K = 1`; for `K ≥ 2` the
inequality is strict. -/
theorem theoremB_every_tie_rule_eq_iff (hp0 : ∀ ω, 0 ≤ p0 ω) (hsum : ∑ ω, p0 ω = 1)
    (hK : 1 ≤ K) {R : Type*} [Fintype R] (ν : R → ℝ) (hν : ∑ r, ν r = 1) (T : TieRule R K) :
    kl (keptLaw p0 S ν T) p0 = lam K ↔ K = 1 := by
  have : keptLaw p0 S ν T = bestOfK p0 S K := funext (keptLaw_eq p0 S hp0 ν hν T)
  rw [this]
  exact theoremB_eq_iff p0 S hp0 hsum hK

end FeedbackChannel.SelectionTieRules

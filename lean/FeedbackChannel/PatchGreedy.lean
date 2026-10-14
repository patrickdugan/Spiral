import FeedbackChannel.PatchStatic

/-!
# Greedy filling is optimal (Proposition 3) and `m*` is monotone along refinement (Proposition 5)

Source: `paper/evaluation_feedback_lattice.md` (version 0.6), §3, Propositions 3 and 5.

An *allocation* is a list of pairs `(category, amount)` whose categories are those of the state
(as a multiset: `P.map Prod.fst ~ L`), with `0 ≤ amount ≤ n`. Amounts are rational, so fractional
allocations (the note's proportional allocation) are included. By Proposition 3
(`prop3_expHits`), a whole-number amount `m_c` in category `c` hits `m_c F_c / n_c` in expectation
whatever the order of the patches, so `alloc_value` is the expected number of hits.

The proofs go through a Lagrangian bound: for every `ρ ≥ 0`, the value of any allocation of total
`M`, and the greedy curve itself, are at most `ρ M + Σ_c n_c (F_c/n_c - ρ)⁺`, with equality for the
greedy curve at a suitable `ρ` when the list is in nonincreasing order of rate.
-/

namespace FeedbackChannel.PatchGreedy

open FeedbackChannel.PatchDP FeedbackChannel.PatchStatic

/-- The categories are in the greedy order: nonincreasing hit rate. -/
def Sorted (L : List Cat) : Prop := L.Pairwise fun c d => rate d ≤ rate c

/-- Every category satisfies `F ≤ n`. -/
def LValid (L : List Cat) : Prop := ∀ c ∈ L, c.2 ≤ c.1

/-- The Lagrangian bound `ρ M + Σ_c n_c (rate c - ρ)⁺`. -/
def dual (L : List Cat) (ρ M : ℚ) : ℚ := ρ * M + (L.map fun d => (d.1 : ℚ) * max (rate d - ρ) 0).sum

/-- Expected hits of an allocation. -/
def alloc_value (P : List (Cat × ℚ)) : ℚ := (P.map fun p => p.2 * rate p.1).sum

/-- Total patches of an allocation. -/
def alloc_total (P : List (Cat × ℚ)) : ℚ := (P.map Prod.snd).sum

/-- `P` is an allocation of patches to the categories `L`. -/
def IsAlloc (L : List Cat) (P : List (Cat × ℚ)) : Prop :=
  (P.map Prod.fst).Perm L ∧ ∀ p ∈ P, 0 ≤ p.2 ∧ p.2 ≤ p.1.1

lemma n_mul_rate {c : Cat} (h : c.2 ≤ c.1) : (c.1 : ℚ) * rate c = c.2 := by
  unfold rate
  rcases Nat.eq_zero_or_pos c.1 with h0 | hpos
  · have : c.2 = 0 := by omega
    simp [h0, this]
  · field_simp

lemma dual_tail_nonneg (L : List Cat) (ρ : ℚ) :
    0 ≤ (L.map fun d => (d.1 : ℚ) * max (rate d - ρ) 0).sum := by
  apply List.sum_nonneg
  intro x hx
  obtain ⟨d, _, rfl⟩ := List.mem_map.1 hx
  exact mul_nonneg (by positivity) (le_max_right _ _)

/-- The greedy curve of any list lies below every Lagrangian bound. -/
theorem curve_le_dual : ∀ (L : List Cat), LValid L → ∀ ρ M : ℚ, 0 ≤ ρ → 0 ≤ M →
    curve L M ≤ dual L ρ M := by
  intro L
  induction L with
  | nil => intro _ ρ M hρ hM; simp [curve, dual]; positivity
  | cons c L ih =>
    intro hv ρ M hρ hM
    have hc := hv c (by simp)
    have hL : LValid L := fun d hd => hv d (by simp [hd])
    have ht := dual_tail_nonneg L ρ
    simp only [curve, dual, List.map_cons, List.sum_cons]
    split_ifs with h
    · have h1 : M * rate c ≤ ρ * M + M * max (rate c - ρ) 0 := by
        have := le_max_left (rate c - ρ) 0
        nlinarith
      have h2 : M * max (rate c - ρ) 0 ≤ (c.1 : ℚ) * max (rate c - ρ) 0 :=
        mul_le_mul_of_nonneg_right h (le_max_right _ _)
      linarith
    · push Not at h
      have := ih hL ρ (M - c.1) hρ (by linarith)
      simp only [dual] at this
      have hF := n_mul_rate hc
      have h3 : (c.1 : ℚ) * (rate c - ρ) ≤ (c.1 : ℚ) * max (rate c - ρ) 0 :=
        mul_le_mul_of_nonneg_left (le_max_left _ _) (by positivity)
      nlinarith

/-- In greedy order the curve attains the Lagrangian bound at some `ρ ≥ 0` that is `0` or one of
the rates. -/
theorem curve_eq_dual : ∀ (L : List Cat), LValid L → Sorted L → ∀ M : ℚ, 0 ≤ M →
    M ≤ litems L → ∃ ρ, (ρ = 0 ∨ ∃ d ∈ L, ρ = rate d) ∧ curve L M = dual L ρ M := by
  intro L
  induction L with
  | nil =>
    intro _ _ M hM hM'
    simp only [litems, List.map_nil, List.sum_nil, Nat.cast_zero] at hM'
    refine ⟨0, Or.inl rfl, ?_⟩
    simp [curve, dual]
  | cons c L ih =>
    intro hv hs M hM hM'
    have hc := hv c (by simp)
    have hL : LValid L := fun d hd => hv d (by simp [hd])
    rw [Sorted, List.pairwise_cons] at hs
    simp only [litems, List.map_cons, List.sum_cons, Nat.cast_add] at hM'
    by_cases h : M ≤ c.1
    · refine ⟨rate c, Or.inr ⟨c, by simp, rfl⟩, ?_⟩
      simp only [curve, dual, h, if_true, List.map_cons, List.sum_cons, sub_self, max_self, mul_zero,
        zero_add]
      have : (L.map fun d => (d.1 : ℚ) * max (rate d - rate c) 0).sum = 0 := by
        apply List.sum_eq_zero
        intro x hx
        obtain ⟨d, hd, rfl⟩ := List.mem_map.1 hx
        have := hs.1 d hd
        rw [max_eq_right (by linarith), mul_zero]
      rw [this]; ring
    · push Not at h
      obtain ⟨ρ, hρ, heq⟩ := ih hL hs.2 (M - c.1) (by linarith) (by simp only [litems]; linarith)
      have hρc : ρ ≤ rate c := by
        rcases hρ with rfl | ⟨d, hd, rfl⟩
        · exact rate_nonneg c
        · exact hs.1 d hd
      refine ⟨ρ, ?_, ?_⟩
      · rcases hρ with h0 | ⟨d, hd, rfl⟩
        · exact Or.inl h0
        · exact Or.inr ⟨d, by simp [hd], rfl⟩
      simp only [curve, if_neg (not_le.2 h), heq, dual, List.map_cons, List.sum_cons]
      rw [max_eq_left (by linarith)]
      have hF := n_mul_rate hc
      linarith [show (c.1 : ℚ) * (rate c - ρ) = c.2 - c.1 * ρ by rw [mul_sub, hF]]


lemma sum_map_le {α : Type*} (l : List α) (f g : α → ℚ) (h : ∀ x ∈ l, f x ≤ g x) :
    (l.map f).sum ≤ (l.map g).sum := by
  induction l with
  | nil => simp
  | cons a l ih =>
    simp only [List.map_cons, List.sum_cons]
    exact add_le_add (h a (by simp)) (ih fun x hx => h x (by simp [hx]))

lemma sum_flatMap_map {α β : Type*} (l : List α) (f : α → List β) (g : β → ℚ) :
    ((l.flatMap f).map g).sum = (l.map fun a => ((f a).map g).sum).sum := by
  induction l with
  | nil => simp
  | cons a l ih => simp [List.flatMap_cons, List.sum_append, ih]

/-- Any allocation's value lies below every Lagrangian bound. -/
theorem alloc_le_dual (L : List Cat) (P : List (Cat × ℚ)) (hP : IsAlloc L P) (ρ : ℚ) :
    alloc_value P ≤ dual L ρ (alloc_total P) := by
  have hperm : ((P.map Prod.fst).map fun d => (d.1 : ℚ) * max (rate d - ρ) 0).sum =
      (L.map fun d => (d.1 : ℚ) * max (rate d - ρ) 0).sum := (hP.1.map _).sum_eq
  rw [List.map_map] at hperm
  unfold dual alloc_value alloc_total
  rw [← hperm]
  have hsplit : ρ * (P.map Prod.snd).sum +
      (P.map ((fun d => (d.1 : ℚ) * max (rate d - ρ) 0) ∘ Prod.fst)).sum =
      (P.map fun p => ρ * p.2 + (p.1.1 : ℚ) * max (rate p.1 - ρ) 0).sum := by
    clear hperm hP
    induction P with
    | nil => simp
    | cons p P ih =>
      simp only [List.map_cons, List.sum_cons, Function.comp] at ih ⊢
      rw [← ih]; ring
  rw [hsplit]
  apply sum_map_le
  intro p hp
  obtain ⟨h0, h1⟩ := hP.2 p hp
  have h2 : p.2 * (rate p.1 - ρ) ≤ p.2 * max (rate p.1 - ρ) 0 :=
    mul_le_mul_of_nonneg_left (le_max_left _ _) h0
  have h3 : p.2 * max (rate p.1 - ρ) 0 ≤ (p.1.1 : ℚ) * max (rate p.1 - ρ) 0 :=
    mul_le_mul_of_nonneg_right h1 (le_max_right _ _)
  nlinarith

/-- The greedy allocation of `M` patches: fill the categories in list order. -/
def galloc : List Cat → ℚ → List (Cat × ℚ)
  | [], _ => []
  | c :: L, M => if M ≤ c.1 then (c, M) :: L.map (fun d => (d, 0)) else (c, (c.1 : ℚ)) :: galloc L (M - c.1)

lemma galloc_spec : ∀ (L : List Cat), LValid L → ∀ (M : ℚ), 0 ≤ M → M ≤ litems L →
    IsAlloc L (galloc L M) ∧ alloc_value (galloc L M) = curve L M ∧ alloc_total (galloc L M) = M := by
  intro L
  induction L with
  | nil =>
    intro _ M hM hM'
    simp only [litems, List.map_nil, List.sum_nil, Nat.cast_zero] at hM'
    have : M = 0 := le_antisymm hM' hM
    subst this
    refine ⟨⟨by simp [galloc], by simp [galloc]⟩, by simp [galloc, alloc_value, curve],
      by simp [galloc, alloc_total]⟩
  | cons c L ih =>
    intro hv M hM hM'
    have hc := hv c (by simp)
    have hL : LValid L := fun d hd => hv d (by simp [hd])
    simp only [litems, List.map_cons, List.sum_cons, Nat.cast_add] at hM'
    by_cases h : M ≤ c.1
    · simp only [galloc, h, if_true, curve]
      refine ⟨⟨?_, ?_⟩, ?_, ?_⟩
      · simp [List.map_map, Function.comp_def]
      · intro p hp
        simp only [List.mem_cons, List.mem_map] at hp
        rcases hp with rfl | ⟨d, _, rfl⟩
        · exact ⟨hM, h⟩
        · simp
      · simp [alloc_value, Function.comp_def]
      · simp [alloc_total, Function.comp_def]
    · push Not at h
      obtain ⟨⟨hperm, hbox⟩, hval, htot⟩ :=
        ih hL (M - c.1) (by linarith) (by simp only [litems]; linarith)
      simp only [galloc, if_neg (not_le.2 h), curve]
      refine ⟨⟨?_, ?_⟩, ?_, ?_⟩
      · simp only [List.map_cons]; exact hperm.cons c
      · intro p hp
        rcases List.mem_cons.1 hp with rfl | hp
        · exact ⟨by positivity, le_rfl⟩
        · exact hbox p hp
      · simp only [alloc_value, List.map_cons, List.sum_cons] at hval ⊢
        rw [hval, n_mul_rate hc]
      · simp only [alloc_total, List.map_cons, List.sum_cons] at htot ⊢
        rw [htot]; ring

/-- **Proposition 3 (greedy is optimal).** With the categories in nonincreasing order of rate,
filling them in turn maximizes the expected number of hits over all allocations of the same total
`M`, at every patch count `0 ≤ M ≤ n`: the greedy curve is the greatest value. -/
theorem prop3_greedy (L : List Cat) (hv : LValid L) (hs : Sorted L) (M : ℚ) (hM : 0 ≤ M)
    (hM' : M ≤ litems L) :
    IsGreatest {x | ∃ P, IsAlloc L P ∧ alloc_total P = M ∧ x = alloc_value P} (curve L M) := by
  obtain ⟨hA, hval, htot⟩ := galloc_spec L hv M hM hM'
  refine ⟨⟨galloc L M, hA, htot, hval.symm⟩, ?_⟩
  rintro x ⟨P, hP, hPt, rfl⟩
  obtain ⟨ρ, -, heq⟩ := curve_eq_dual L hv hs M hM hM'
  rw [heq, ← hPt]
  exact alloc_le_dual L P hP ρ

/-! ### Proposition 5 -/

/-- `Lf` refines `L`: the categories of `Lf` are grouped into parts, one part per category of `L`,
whose item and failure counts add up to that category's (the finer map refines the coarser). -/
def Refines (Lf L : List Cat) : Prop :=
  ∃ parts : List (Cat × List Cat), (parts.map Prod.fst).Perm L ∧ (parts.flatMap Prod.snd).Perm Lf ∧
    ∀ q ∈ parts, (q.2.map Prod.fst).sum = q.1.1 ∧ (q.2.map Prod.snd).sum = q.1.2

lemma n_mul_pos {c : Cat} (h : c.2 ≤ c.1) (ρ : ℚ) :
    (c.1 : ℚ) * max (rate c - ρ) 0 = max ((c.2 : ℚ) - ρ * c.1) 0 := by
  rw [mul_max_of_nonneg _ _ (by positivity), mul_sub, n_mul_rate h, mul_zero, mul_comm]

lemma max_sum_le (l : List ℚ) : max l.sum 0 ≤ (l.map fun x => max x 0).sum := by
  induction l with
  | nil => simp
  | cons a l ih =>
    simp only [List.sum_cons, List.map_cons]
    have h1 := le_max_left a 0
    have h2 := le_max_right a 0
    have h4 : 0 ≤ (l.map fun x => max x 0).sum :=
      List.sum_nonneg fun x hx => by obtain ⟨y, _, rfl⟩ := List.mem_map.1 hx; exact le_max_right _ _
    have h5 := le_trans (le_max_left l.sum 0) ih
    apply max_le <;> linarith

lemma cast_sum_map {α : Type*} (l : List α) (f : α → ℕ) :
    ((l.map f).sum : ℚ) = (l.map fun a => (f a : ℚ)).sum := by
  induction l with
  | nil => simp
  | cons a l ih => simp [ih]

/-- Refining can only raise the Lagrangian bound. -/
lemma dual_tail_refine {L Lf : List Cat} (hR : Refines Lf L) (hv : LValid L) (hvf : LValid Lf) (ρ : ℚ) :
    (L.map fun d => (d.1 : ℚ) * max (rate d - ρ) 0).sum ≤
      (Lf.map fun d => (d.1 : ℚ) * max (rate d - ρ) 0).sum := by
  obtain ⟨parts, hp1, hp2, hp3⟩ := hR
  rw [← (hp1.map _).sum_eq, ← (hp2.map _).sum_eq, List.map_map, sum_flatMap_map]
  apply sum_map_le
  intro q hq
  have hqv : q.1.2 ≤ q.1.1 := hv q.1 (hp1.subset (List.mem_map_of_mem hq))
  have hdv : ∀ d ∈ q.2, d.2 ≤ d.1 := fun d hd =>
    hvf d (hp2.subset (List.mem_flatMap.2 ⟨q, hq, hd⟩))
  simp only [Function.comp, n_mul_pos hqv]
  rw [show (q.2.map fun d => (d.1 : ℚ) * max (rate d - ρ) 0) =
      ((q.2.map fun d => (d.2 : ℚ) - ρ * d.1).map fun x => max x 0) by
    rw [List.map_map]; exact List.map_congr_left fun d hd => n_mul_pos (hdv d hd) ρ]
  refine le_trans (le_of_eq ?_) (max_sum_le _)
  congr 1
  obtain ⟨h1, h2⟩ := hp3 q hq
  rw [← h1, ← h2, cast_sum_map, cast_sum_map]
  clear h1 h2 hdv hqv hq
  induction q.2 with
  | nil => simp
  | cons d l ih => simp only [List.map_cons, List.sum_cons]; linear_combination ih

lemma litems_refine {L Lf : List Cat} (hR : Refines Lf L) : litems Lf = litems L := by
  obtain ⟨parts, hp1, hp2, hp3⟩ := hR
  unfold litems
  rw [← (hp1.map _).sum_eq, ← (hp2.map _).sum_eq, List.map_map]
  have : ((parts.flatMap Prod.snd).map Prod.fst).sum =
      (parts.map fun q => (q.2.map Prod.fst).sum).sum := by
    clear hp1 hp2 hp3
    induction parts with
    | nil => simp
    | cons a l ih => simp [List.flatMap_cons, List.sum_append, ih]
  rw [this]
  congr 1
  exact List.map_congr_left fun q hq => (hp3 q hq).1

/-- Along refinement, the greedy expected-hit curve of the finer map (in its greedy order) lies
above the curve of the coarser one (in any order), at every patch count. -/
theorem curve_mono_refine {L Lf : List Cat} (hR : Refines Lf L) (hv : LValid L) (hvf : LValid Lf)
    (hsf : Sorted Lf) (M : ℚ) (hM : 0 ≤ M) (hM' : M ≤ litems L) : curve L M ≤ curve Lf M := by
  obtain ⟨ρ, hρ, heq⟩ := curve_eq_dual Lf hvf hsf M hM (by rw [litems_refine hR]; exact hM')
  have hρ0 : 0 ≤ ρ := by
    rcases hρ with rfl | ⟨d, _, rfl⟩
    · exact le_rfl
    · exact rate_nonneg d
  calc curve L M ≤ dual L ρ M := curve_le_dual L hv ρ M hρ0 hM
    _ ≤ dual Lf ρ M := by unfold dual; linarith [dual_tail_refine hR hv hvf ρ]
    _ = curve Lf M := heq.symm

lemma mstar_nonneg (pre : List Cat) (c : Cat) (H : ℕ) : 0 ≤ mstar pre c H := by
  unfold mstar; positivity

lemma mstar_le_items (pre post : List Cat) (c : Cat) (H : ℕ) (hc : c.2 ≤ c.1)
    (hhi : H ≤ lfails pre + c.2) : mstar pre c H ≤ litems (pre ++ c :: post) := by
  have hpost : (0 : ℚ) ≤ litems post := by positivity
  have hsplit : (litems (pre ++ c :: post) : ℚ) = litems pre + c.1 + litems post := by
    simp only [litems, List.map_append, List.map_cons, List.sum_append, List.sum_cons]
    push_cast; ring
  rw [hsplit]
  unfold mstar
  rcases Nat.eq_zero_or_pos c.2 with h0 | hpos
  · rw [h0]; simp only [Nat.cast_zero, div_zero]
    have : (0 : ℚ) ≤ c.1 := by positivity
    linarith
  have hF : (0 : ℚ) < c.2 := by exact_mod_cast hpos
  have hHj : ((H - lfails pre : ℕ) : ℚ) ≤ c.2 := by exact_mod_cast (show H - lfails pre ≤ c.2 by omega)
  have : ((H - lfails pre : ℕ) : ℚ) * c.1 / c.2 ≤ c.1 := by
    rw [div_le_iff₀ hF]
    have : (0 : ℚ) ≤ c.1 := by positivity
    nlinarith
  linarith

/-- **Proposition 5 (monotonicity of `m*`).** If the finer map `Lf` refines `L`, the
expected-score crossing of the greedy schedule under `Lf` comes no later than under `L`, for every
failure pattern and every requirement `H` (`j` is the crossing category of each schedule). The
coarse schedule may be in any order, in particular its greedy one. -/
theorem prop5 (L Lf : List Cat) (hR : Refines Lf L) (hv : LValid L) (hvf : LValid Lf)
    (hsf : Sorted Lf) (pre post pref postf : List Cat) (c cf : Cat)
    (hL : L = pre ++ c :: post) (hLf : Lf = pref ++ cf :: postf) (H : ℕ)
    (hlo : lfails pre < H) (hhi : H ≤ lfails pre + c.2)
    (hlof : lfails pref < H) (hhif : H ≤ lfails pref + cf.2) :
    mstar pref cf H ≤ mstar pre c H := by
  by_contra hlt
  push Not at hlt
  subst hL hLf
  have h1 := (prop4_crossing pre post c H hv hlo hhi).1
  have h2 := (prop4_crossing pref postf cf H hvf hlof hhif).2 _ (mstar_nonneg pre c H) hlt
  have h3 := curve_mono_refine hR hv hvf hsf _ (mstar_nonneg pre c H)
    (mstar_le_items pre post c H (hv c (by simp)) hhi)
  linarith

end FeedbackChannel.PatchGreedy

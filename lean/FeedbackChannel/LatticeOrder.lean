import FeedbackChannel.LatticeJoin

/-!
# Propositions 1 and 2: the data-processing law on the channel lattice; category leakage is an
order embedding

Source: `paper/evaluation_feedback_lattice.md` (version 0.6), §1 and §2.

A deterministic channel is a function `f : X → Y` on a finite record set `X`; its partition is the
kernel of `f`. In the note's order `p ≤ q` when `q` refines `p`, written here `Refines g f`
(`g` refines `f`: `g x = g y → f x = f y`). The total variation through `f` is the largest
`|P(U) - Q(U)|` over unions `U` of blocks of `f`, i.e. preimages `f⁻¹ S`. `P, Q` are arbitrary
rational weights on records (in particular distributions).
-/

namespace FeedbackChannel.LatticeOrder

open Finset FeedbackChannel.LatticeJoin

section Prop1

variable {X Y Z : Type*} [Fintype X] [DecidableEq X] [Fintype Y] [DecidableEq Y]
  [Fintype Z] [DecidableEq Z]

/-- `g` refines `f` (the note's `f ≤ g`). -/
def Refines (g : X → Z) (f : X → Y) : Prop := ∀ x y, g x = g y → f x = f y

/-- `TV(f_# P, f_# Q) = max_U |P(U) - Q(U)|` over unions `U = f⁻¹ S` of blocks of `f`. -/
def tvThrough (f : X → Y) (P Q : X → ℚ) : ℚ :=
  (univ : Finset (Finset Y)).sup' ⟨∅, mem_univ _⟩
    fun S => |∑ x ∈ univ.filter (fun x => f x ∈ S), (P x - Q x)|

/-- **Proposition 1 (lattice data-processing law).** If `g` refines `f`, the total variation
through `f` is at most the total variation through `g`, for all `P, Q`. -/
theorem prop1_mono (f : X → Y) (g : X → Z) (h : Refines g f) (P Q : X → ℚ) :
    tvThrough f P Q ≤ tvThrough g P Q := by
  unfold tvThrough
  apply Finset.sup'_le
  intro S _
  set T : Finset Z := (univ.filter fun x => f x ∈ S).image g
  have hset : (univ.filter fun x => f x ∈ S) = univ.filter fun x => g x ∈ T := by
    ext x
    simp only [mem_filter, mem_univ, true_and, T, mem_image]
    constructor
    · intro hx; exact ⟨x, hx, rfl⟩
    · rintro ⟨x', hx', hg⟩
      rw [← h x' x hg]; exact hx'
  rw [hset]
  exact Finset.le_sup' (fun T => |∑ x ∈ univ.filter (fun x => g x ∈ T), (P x - Q x)|) (mem_univ T)

/-- Point mass. -/
def delta (x : X) : X → ℚ := fun z => if z = x then 1 else 0

lemma sum_delta_diff {W : Type*} [DecidableEq W] (k : X → W) (S : Finset W) (x y : X) :
    ∑ z ∈ univ.filter (fun z => k z ∈ S), (delta x z - delta y z) =
      (if k x ∈ S then 1 else 0) - (if k y ∈ S then 1 else 0) := by
  rw [Finset.sum_sub_distrib]
  simp [delta, Finset.sum_ite_eq']

/-- **Proposition 1 (converse).** If `g` does not refine `f`, two point masses have total
variation `1` through `f` and `0` through `g`. -/
theorem prop1_converse (f : X → Y) (g : X → Z) (h : ¬ Refines g f) :
    ∃ x y, tvThrough f (delta x) (delta y) = 1 ∧ tvThrough g (delta x) (delta y) = 0 := by
  unfold Refines at h
  push Not at h
  obtain ⟨x, y, hg, hf⟩ := h
  refine ⟨x, y, ?_, ?_⟩
  · unfold tvThrough
    apply le_antisymm
    · apply Finset.sup'_le
      intro S _
      rw [sum_delta_diff]
      split_ifs <;> norm_num
    · refine le_trans (le_of_eq ?_) (Finset.le_sup' _ (mem_univ {f x}))
      rw [sum_delta_diff]
      simp [Ne.symm hf]
  · unfold tvThrough
    apply le_antisymm
    · apply Finset.sup'_le
      intro T _
      rw [sum_delta_diff, hg, sub_self, abs_zero]
    · exact le_trans (abs_nonneg _) (Finset.le_sup'
        (fun T => |∑ z ∈ univ.filter (fun z => g z ∈ T), (delta x z - delta y z)|) (mem_univ ∅))

end Prop1

section Prop2

variable {ι R R' : Type*} [Fintype ι] [DecidableEq ι] [Fintype R] [DecidableEq R]
  [Fintype R'] [DecidableEq R']

lemma rowCount_decomp (γ : ι → R) (γ' : ι → R') (h : ∀ i j, γ' i = γ' j → γ i = γ j)
    (r : ι → Bool) (a : R) :
    rowCount γ r a = ∑ a', if (∃ j, γ' j = a' ∧ γ j = a) then rowCount γ' r a' else 0 := by
  unfold rowCount
  rw [card_eq_sum_card_fiberwise (f := γ') (t := univ) (by intro i _; simp)]
  refine Finset.sum_congr rfl fun a' _ => ?_
  split_ifs with hex
  · obtain ⟨j, hj1, hj2⟩ := hex
    congr 1
    ext i
    simp only [mem_filter, mem_univ, true_and]
    constructor
    · rintro ⟨⟨_, hr⟩, hi⟩; exact ⟨hi, hr⟩
    · rintro ⟨hi, hr⟩
      exact ⟨⟨(h i j (hi.trans hj1.symm)).trans hj2, hr⟩, hi⟩
  · rw [card_eq_zero, filter_eq_empty_iff]
    intro i hi hia'
    simp only [mem_filter, mem_univ, true_and] at hi
    exact hex ⟨i, hia', hi.1⟩

lemma filter_ne_erase {W : Type*} [DecidableEq W] (κ : ι → W) (w : W) (t : ι) :
    (univ.filter fun k => κ k = w ∧ decide (k ≠ t) = true) = (univ.filter fun k => κ k = w).erase t := by
  ext k
  simp only [mem_filter, mem_univ, true_and, mem_erase, decide_eq_true_eq]
  tauto

lemma card_ne_erase {s : Finset ι} {i : ι} (hi : i ∈ s) : (s.erase i).card ≠ s.card := by
  rw [card_erase_of_mem hi]
  have : 0 < s.card := card_pos.2 ⟨i, hi⟩
  omega

/-- **Proposition 2 (category leakage is an order embedding).** For category maps `γ, γ'`, the
per-category pass counts `Φ(γ')` refine `Φ(γ)` (equal `γ'`-counts force equal `γ`-counts on every
pair of records) iff `γ'` refines `γ`. -/
theorem prop2 (γ : ι → R) (γ' : ι → R') :
    (∀ r s : ι → Bool, rowCount γ' r = rowCount γ' s → rowCount γ r = rowCount γ s) ↔
      (∀ i j, γ' i = γ' j → γ i = γ j) := by
  constructor
  · intro hΦ
    by_contra hγ
    push Not at hγ
    obtain ⟨i, j, h', hne⟩ := hγ
    let r : ι → Bool := fun k => decide (k ≠ i)
    let s : ι → Bool := fun k => decide (k ≠ j)
    have h1 : rowCount γ' r = rowCount γ' s := by
      funext a'
      unfold rowCount
      simp only [r, s]
      rw [filter_ne_erase, filter_ne_erase]
      by_cases ha : γ' i = a'
      · rw [card_erase_of_mem (by simp [ha]), card_erase_of_mem (by simp [← h', ha])]
      · rw [erase_eq_of_notMem (by simp [ha]), erase_eq_of_notMem (by simp [← h', ha])]
    have h2 := congrFun (hΦ r s h1) (γ i)
    unfold rowCount at h2
    simp only [r, s] at h2
    have hj : j ∉ univ.filter (fun k => γ k = γ i) := by simp [Ne.symm hne]
    rw [filter_ne_erase, filter_ne_erase, erase_eq_of_notMem hj] at h2
    exact card_ne_erase (by simp) h2
  · intro hγ r s hrs
    funext a
    rw [rowCount_decomp γ γ' hγ r a, rowCount_decomp γ γ' hγ s a, hrs]

/-- The top endpoint: with singleton categories (`γ = id`) the counts are the item outcomes, so
`Φ(singletons)` is item-level feedback. -/
theorem prop2_item_level (r s : ι → Bool) : rowCount (id : ι → ι) r = rowCount id s ↔ r = s := by
  constructor
  · intro h
    funext i
    have := congrFun h i
    unfold rowCount at this
    have e : ∀ t : ι → Bool, (univ.filter fun k => id k = i ∧ t k = true) =
        if t i = true then {i} else ∅ := by
      intro t
      ext k
      split_ifs with ht <;> simp only [mem_filter, mem_univ, true_and, id, mem_singleton,
        Finset.notMem_empty, iff_false, not_and] <;> [exact ⟨fun h => h.1, fun h => ⟨h, h ▸ ht⟩⟩;
          exact fun hk => hk ▸ ht]
    rw [e, e] at this
    cases hr : r i <;> cases hs : s i <;> simp_all
  · rintro rfl; rfl

end Prop2

end FeedbackChannel.LatticeOrder

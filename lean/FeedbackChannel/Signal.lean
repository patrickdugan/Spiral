import Mathlib.Tactic
import Mathlib.Data.Nat.Log
import Mathlib.Analysis.SpecialFunctions.Log.Basic

/-!
# Training-signal limits: counting and algebra (L1, L2, L3, L4, L6)

Source: `paper/rl_training_signal_limits.md` §4, and for L3 the ceiling law of
`paper/evaluation_feedback_insertions.md` §D.

* Adaptive strategies are depth-indexed decision trees (`Strategy`). The counting lemma
  `Strategy.card_le_pow` says that a strategy of `q` queries whose answers all lie in a set of `m`
  values tells apart at most `m ^ q` hypotheses. L1 and L2 are instances.
* L3 derives the ceiling-check thresholds from the score formulas of the insertions note.
* L4 is the shared-error judge algebra, including the feasibility characterisation.
* L6 is the garbling direction of Blackwell's ordering for deterministic channels, and also for
  stochastic garblings.
-/

namespace FeedbackChannel.Signal

open Finset

universe u

/-! ## Adaptive strategies as decision trees -/

/-- An adaptive strategy that asks exactly `q` queries in `Q`, reads each answer in `A` and may
choose the next query from the answers so far, then outputs a label in `L`. A strategy that stops
earlier is padded with queries whose answers it ignores, so "exactly `q`" loses nothing. -/
inductive Strategy (Q A L : Type u) : ℕ → Type u
  | done : L → Strategy Q A L 0
  | ask {q : ℕ} : Q → (A → Strategy Q A L q) → Strategy Q A L (q + 1)

namespace Strategy

variable {Q A L : Type u}

/-- The label a strategy outputs against the oracle `α`, which answers query `x` with `α x`. -/
def run : {q : ℕ} → Strategy Q A L q → (Q → A) → L
  | _, done l, _ => l
  | _, ask x k, α => run (k (α x)) α

/-- The labels a strategy can output when every answer lies in `vals`. -/
def outcomes [DecidableEq L] (vals : Finset A) : {q : ℕ} → Strategy Q A L q → Finset L
  | _, done l => {l}
  | _, ask _ k => vals.biUnion fun a => outcomes vals (k a)

theorem card_outcomes_le [DecidableEq L] (vals : Finset A) :
    ∀ {q : ℕ} (s : Strategy Q A L q), (s.outcomes vals).card ≤ vals.card ^ q
  | _, done l => by simp [outcomes]
  | _, @ask _ _ _ q x k => by
      simp only [outcomes]
      calc (vals.biUnion fun a => (k a).outcomes vals).card
          ≤ ∑ a ∈ vals, ((k a).outcomes vals).card := card_biUnion_le
        _ ≤ ∑ _a ∈ vals, vals.card ^ q := sum_le_sum fun a _ => card_outcomes_le vals (k a)
        _ = vals.card ^ (q + 1) := by rw [sum_const, smul_eq_mul, pow_succ']

theorem run_mem_outcomes [DecidableEq L] (vals : Finset A) (α : Q → A) (hα : ∀ x, α x ∈ vals) :
    ∀ {q : ℕ} (s : Strategy Q A L q), s.run α ∈ s.outcomes vals
  | _, done l => by simp [run, outcomes]
  | _, ask x k => by
      simp only [run, outcomes, mem_biUnion]
      exact ⟨α x, hα x, run_mem_outcomes vals α hα (k (α x))⟩

/-- **Counting bound for adaptive strategies.** If every candidate hypothesis `h` answers every
query `x` with a value `ans h x` in `vals`, and the strategy's output separates the candidates
(distinct candidates give distinct outputs), then there are at most `#vals ^ q` candidates. -/
theorem card_le_pow {H : Type*} [DecidableEq L] (vals : Finset A) (cands : Finset H)
    (ans : H → Q → A) (hvals : ∀ h ∈ cands, ∀ x, ans h x ∈ vals) {q : ℕ}
    (s : Strategy Q A L q) (hdist : Set.InjOn (fun h => s.run (ans h)) cands) :
    cands.card ≤ vals.card ^ q := by
  calc cands.card = (cands.image fun h => s.run (ans h)).card := (card_image_of_injOn hdist).symm
    _ ≤ (s.outcomes vals).card := by
        apply card_le_card
        intro y hy
        obtain ⟨h, hh, rfl⟩ := mem_image.1 hy
        exact run_mem_outcomes vals (ans h) (hvals h hh) s
    _ ≤ vals.card ^ q := card_outcomes_le vals s

end Strategy

/-- From `N ≤ m ^ q`: `q` is at least `⌈log N / log m⌉` (real logarithms; for `m ≤ 1` the quotient
is `0` by Lean's conventions `log 0 = log 1 = 0` and `x / 0 = 0`). -/
theorem ceil_log_div_le_of_le_pow {N m q : ℕ} (h : N ≤ m ^ q) :
    ⌈Real.log N / Real.log m⌉ ≤ (q : ℤ) := by
  rw [Int.ceil_le]
  push_cast
  rcases Nat.lt_or_ge m 2 with hm | hm
  · have hlog : Real.log m = 0 := by
      interval_cases m <;> simp
    rw [hlog, div_zero]
    positivity
  · rcases Nat.eq_zero_or_pos N with hN | hN
    · subst hN
      simp only [Nat.cast_zero, Real.log_zero, zero_div]
      positivity
    · have hm1 : (1 : ℝ) < m := by exact_mod_cast (by omega : 1 < m)
      have hlogm : 0 < Real.log m := Real.log_pos hm1
      rw [div_le_iff₀ hlogm]
      have hNm : (N : ℝ) ≤ (m : ℝ) ^ q := by exact_mod_cast h
      calc Real.log N ≤ Real.log ((m : ℝ) ^ q) :=
            Real.log_le_log (by exact_mod_cast hN) hNm
        _ = q * Real.log m := by rw [Real.log_pow]

/-! ## L1. Bits per episode -/

/-- **L1.** A deterministic channel `ch` on step records, with `m = #(image of ch)` possible values.
In each of `q` episodes the loop picks an action `x` (adaptively, from the earlier rewards), the
hypothesis `h` produces the step record `record h x`, and the loop sees `ch (record h x)`. If the
loop's output tells apart every hypothesis in `cands`, then `#cands ≤ m ^ q`. -/
theorem L1_card_le {R O X H L : Type} [Fintype R] [DecidableEq O] [DecidableEq L]
    (ch : R → O) (record : H → X → R) (cands : Finset H) {q : ℕ} (s : Strategy X O L q)
    (hdist : Set.InjOn (fun h => s.run fun x => ch (record h x)) cands) :
    cands.card ≤ (univ.image ch).card ^ q :=
  Strategy.card_le_pow (univ.image ch) cands (fun h x => ch (record h x))
    (fun _ _ _ => mem_image_of_mem ch (mem_univ _)) s hdist

/-- **L1, episode count.** Under the hypotheses of `L1_card_le`, the loop needs at least
`⌈log H / log m⌉` episodes, `H = #cands`, `m` the channel's number of values; equivalently
`Nat.clog m H ≤ q` when `m ≥ 2`. -/
theorem L1_episodes {R O X H L : Type} [Fintype R] [DecidableEq O] [DecidableEq L]
    (ch : R → O) (record : H → X → R) (cands : Finset H) {q : ℕ} (s : Strategy X O L q)
    (hdist : Set.InjOn (fun h => s.run fun x => ch (record h x)) cands) :
    ⌈Real.log cands.card / Real.log (univ.image ch).card⌉ ≤ (q : ℤ) ∧
      (1 < (univ.image ch).card → Nat.clog (univ.image ch).card cands.card ≤ q) := by
  have h := L1_card_le ch record cands s hdist
  exact ⟨ceil_log_div_le_of_le_pow h, fun hm => (Nat.clog_le_iff_le_pow hm).2 h⟩

/-- Outcome reward on `T` steps: `true` iff every step succeeded. -/
def outcomeReward {T : ℕ} (r : Fin T → Bool) : Bool := decide (∀ i, r i = true)

/-- **L1, example.** With `T = 3` steps, identifying the step record (eight hypotheses) through the
outcome-reward channel takes at least three episodes, whatever the adaptive strategy. -/
theorem L1_example_outcome {X L : Type} [DecidableEq L]
    (record : (Fin 3 → Bool) → X → (Fin 3 → Bool)) {q : ℕ} (s : Strategy X Bool L q)
    (hdist : Set.InjOn (fun h => s.run fun x => outcomeReward (record h x))
      ((univ : Finset (Fin 3 → Bool)) : Set (Fin 3 → Bool))) : 3 ≤ q := by
  have h := L1_card_le outcomeReward record univ s hdist
  have hm : (univ.image (outcomeReward (T := 3))).card ≤ 2 := by
    simpa using card_le_univ (univ.image (outcomeReward (T := 3)))
  have h8 : (univ : Finset (Fin 3 → Bool)).card = 8 := by simp
  rw [h8] at h
  have h2 : 8 ≤ 2 ^ q := h.trans (Nat.pow_le_pow_left hm q)
  by_contra hq
  have : 2 ^ q ≤ 2 ^ 2 := Nat.pow_le_pow_right (by norm_num) (by omega)
  omega

/-- **L1, example.** With `T = 3` steps, the process-reward channel (the record itself) needs at
least one episode to identify the eight records. -/
theorem L1_example_process {X L : Type} [DecidableEq L]
    (record : (Fin 3 → Bool) → X → (Fin 3 → Bool)) {q : ℕ}
    (s : Strategy X (Fin 3 → Bool) L q)
    (hdist : Set.InjOn (fun h => s.run fun x => id (record h x))
      ((univ : Finset (Fin 3 → Bool)) : Set (Fin 3 → Bool))) : 1 ≤ q := by
  have h := L1_card_le id record univ s hdist
  have h8 : (univ : Finset (Fin 3 → Bool)).card = 8 := by simp
  rw [h8] at h
  by_contra hq
  have hq0 : q = 0 := by omega
  rw [hq0, pow_zero] at h
  omega

/-- Partial credit: the number of successful steps (Hamming weight of the record). -/
def partialCredit {T : ℕ} (r : Fin T → Bool) : ℕ := (univ.filter fun i => r i = true).card

/-- First failure: the length of the all-success prefix, i.e. the (0-based) position of the first
failed step, or `T` if no step failed. -/
def firstFailure {T : ℕ} (r : Fin T → Bool) : ℕ :=
  (univ.filter fun i : Fin T => ∀ j, j ≤ i → r j = true).card

/-- `f` factors through `g`: `f = k ∘ g` for some `k`. -/
def FactorsThrough {R B C : Type*} (f : R → B) (g : R → C) : Prop :=
  ∃ k : C → B, ∀ r, f r = k (g r)

theorem not_factorsThrough_of {R B C : Type*} {f : R → B} {g : R → C} (r r' : R)
    (hg : g r = g r') (hf : f r ≠ f r') : ¬ FactorsThrough f g := by
  rintro ⟨k, hk⟩
  exact hf (by rw [hk r, hk r', hg])

/-- **L1, incomparability.** For every `T ≥ 2`, partial credit and first-failure are incomparable:
neither factors through the other. (For `T ≤ 1` they coincide, so `T ≥ 2` is needed.) -/
theorem L1_incomparable {T : ℕ} (hT : 2 ≤ T) :
    ¬ FactorsThrough (partialCredit (T := T)) (firstFailure (T := T)) ∧
    ¬ FactorsThrough (firstFailure (T := T)) (partialCredit (T := T)) := by
  obtain ⟨i0, hi0⟩ : ∃ i : Fin T, i.val = 0 := ⟨⟨0, by omega⟩, rfl⟩
  obtain ⟨i1, hi1⟩ : ∃ i : Fin T, i.val = 1 := ⟨⟨1, by omega⟩, rfl⟩
  have h01 : i0 ≠ i1 := fun h => by rw [h] at hi0; omega
  have hle0 : ∀ i : Fin T, i0 ≤ i := fun i => by
    rw [Fin.le_iff_val_le_val, hi0]; exact Nat.zero_le _
  -- three witness records: all steps fail; only step 0 fails; only step 1 fails
  have ffF : firstFailure (fun _ : Fin T => false) = 0 := by
    rw [firstFailure, card_eq_zero, filter_eq_empty_iff]
    intro i _ h
    exact absurd (h i0 (hle0 i)) (by simp)
  have ff0 : firstFailure (fun i : Fin T => decide (i ≠ i0)) = 0 := by
    rw [firstFailure, card_eq_zero, filter_eq_empty_iff]
    intro i _ h
    exact absurd (h i0 (hle0 i)) (by simp)
  have ff1 : firstFailure (fun i : Fin T => decide (i ≠ i1)) = 1 := by
    rw [firstFailure, card_eq_one]
    refine ⟨i0, ?_⟩
    ext i
    simp only [mem_filter, mem_univ, true_and, mem_singleton, decide_eq_true_eq]
    constructor
    · intro h
      by_contra hne
      have hi : i1 ≤ i := by
        rw [Fin.le_iff_val_le_val, hi1]
        have : i.val ≠ 0 := fun h0 => hne (Fin.ext (h0.trans hi0.symm))
        omega
      exact h i1 hi rfl
    · intro hi j hj
      rw [hi] at hj
      have : j = i0 := le_antisymm hj (hle0 j)
      rw [this]; exact h01
  have pcF : partialCredit (fun _ : Fin T => false) = 0 := by simp [partialCredit]
  have pc0 : partialCredit (fun i : Fin T => decide (i ≠ i0)) = T - 1 := by
    simp [partialCredit, filter_ne', card_erase_of_mem]
  have pc1 : partialCredit (fun i : Fin T => decide (i ≠ i1)) = T - 1 := by
    simp [partialCredit, filter_ne', card_erase_of_mem]
  constructor
  · exact not_factorsThrough_of (fun _ : Fin T => false) (fun i : Fin T => decide (i ≠ i0))
      (by rw [ffF, ff0]) (by rw [pcF, pc0]; omega)
  · exact not_factorsThrough_of (fun i : Fin T => decide (i ≠ i0)) (fun i : Fin T => decide (i ≠ i1))
      (by rw [pc0, pc1]) (by rw [ff0, ff1]; omega)

/-! ## L2. Score queries -/

/-- The selection set's score after patching the items in `Q`, when the failed items are `S`:
the number of items that pass (unfailed, or failed and patched). -/
def patchedScore (n : ℕ) (S Q : Finset (Fin n)) : ℕ :=
  (univ.filter fun i => i ∉ S ∨ i ∈ Q).card

/-- With `f` failures every score query returns one of the `f + 1` values `n - f, …, n`. -/
theorem patchedScore_mem {n f : ℕ} {S : Finset (Fin n)} (hS : S.card = f) (Q : Finset (Fin n)) :
    patchedScore n S Q ∈ Icc (n - f) n := by
  rw [mem_Icc]
  constructor
  · have h1 : Sᶜ ⊆ univ.filter (fun i => i ∉ S ∨ i ∈ Q) := by
      intro i hi
      rw [mem_compl] at hi
      simp [hi]
    have h2 := card_le_card h1
    rw [card_compl, Fintype.card_fin, hS] at h2
    exact h2
  · calc patchedScore n S Q ≤ (univ : Finset (Fin n)).card := card_filter_le _ _
      _ = n := by simp

/-- **L2, lower bound.** Any adaptive strategy of `q` score queries (each query patches a chosen
subset and reads the set's score) whose output separates the `C(n, f)` possible failure sets of
size `f` satisfies `C(n, f) ≤ (f + 1) ^ q`. -/
theorem L2_lower_bound {n f q : ℕ} {L : Type} [DecidableEq L]
    (s : Strategy (Finset (Fin n)) ℕ L q)
    (hdist : Set.InjOn (fun S => s.run (patchedScore n S))
      ((powersetCard f (univ : Finset (Fin n)) : Finset (Finset (Fin n))) : Set (Finset (Fin n)))) :
    n.choose f ≤ (f + 1) ^ q := by
  rcases le_or_gt f n with hf | hf
  · have h := Strategy.card_le_pow (Icc (n - f) n) (powersetCard f univ) (patchedScore n)
      (fun S hS Q => patchedScore_mem (mem_powersetCard.1 hS).2 Q) s hdist
    rwa [card_powersetCard, card_univ, Fintype.card_fin, Nat.card_Icc,
      (by omega : n + 1 - (n - f) = f + 1)] at h
  · rw [Nat.choose_eq_zero_of_lt hf]
    exact Nat.zero_le _

/-- **L2, as stated in the note.** A strategy of `q` score queries that identifies every failure
set of size `f` (its output is the failure set) has `q ≥ ⌈log C(n,f) / log (f+1)⌉`, and
`q ≥ Nat.clog (f + 1) C(n, f)` (the exact integer ceiling) when `f ≥ 1`. -/
theorem L2_qmin {n f q : ℕ} (s : Strategy (Finset (Fin n)) ℕ (Finset (Fin n)) q)
    (hid : ∀ S ∈ powersetCard f (univ : Finset (Fin n)), s.run (patchedScore n S) = S) :
    n.choose f ≤ (f + 1) ^ q ∧
      ⌈Real.log (n.choose f) / Real.log (f + 1)⌉ ≤ (q : ℤ) ∧
      (1 ≤ f → Nat.clog (f + 1) (n.choose f) ≤ q) := by
  have hdist : Set.InjOn (fun S => s.run (patchedScore n S))
      ((powersetCard f (univ : Finset (Fin n)) : Finset (Finset (Fin n))) : Set (Finset (Fin n))) := by
    intro S hS S' hS' h
    exact (hid S hS).symm.trans (h.trans (hid S' hS'))
  have h := L2_lower_bound s hdist
  refine ⟨h, ?_, fun hf => (Nat.clog_le_iff_le_pow (by omega)).2 h⟩
  have := ceil_log_div_le_of_le_pow h
  push_cast at this
  exact this

/-! ## L3. Noise ceiling and its blind range -/

/-- Per-item ceiling: a predictor blind to label flips at rate `ε ≤ 1/2` that is right on the
true label with probability `c ≤ 1` matches the observed label with probability at most `1 - ε`. -/
theorem L3_ceiling {c ε : ℝ} (hc1 : c ≤ 1) (hε : ε ≤ 1 / 2) :
    c * (1 - ε) + (1 - c) * ε ≤ 1 - ε := by
  nlinarith [mul_nonneg (sub_nonneg.2 hc1) (by linarith : (0 : ℝ) ≤ 1 - 2 * ε)]

/-- Score after memorizing a share `x` of the set chosen without regard to outcomes
(insertions note: `m/n + (1 - m/n) v`). -/
def blindScore (v x : ℝ) : ℝ := x + (1 - x) * v

/-- Score after memorizing a share `x` of the set taken from the failed items
(insertions note: `v + m/n`). -/
def patchScore (v x : ℝ) : ℝ := v + x

/-- **L3, blind memorization.** For `v < 1` the score crosses the ceiling `1 - ε` iff the memorized
share exceeds `(1 - ε - v) / (1 - v)`. -/
theorem L3_blind {v ε x : ℝ} (hv : v < 1) :
    1 - ε < blindScore v x ↔ (1 - ε - v) / (1 - v) < x := by
  have h : 0 < 1 - v := by linarith
  rw [div_lt_iff₀ h, blindScore]
  constructor <;> intro <;> linarith

/-- **L3, patching failures.** The score crosses the ceiling iff the patched share of the set
exceeds `1 - ε - v`. -/
theorem L3_patch {v ε x : ℝ} : 1 - ε < patchScore v x ↔ 1 - ε - v < x := by
  rw [patchScore]
  constructor <;> intro <;> linarith

/-- **L3, patching failures, as a share of the failed items.** Patching a share `y` of the failed
items (a share `y (1 - v)` of the set) crosses the ceiling iff `y > (1 - ε - v)/(1 - v)`. -/
theorem L3_patch_share_of_failed {v ε y : ℝ} (hv : v < 1) :
    1 - ε < patchScore v (y * (1 - v)) ↔ (1 - ε - v) / (1 - v) < y := by
  have h : 0 < 1 - v := by linarith
  rw [div_lt_iff₀ h, patchScore]
  constructor <;> intro <;> linarith

/-- Item-level derivation of the patching score: with pass set `P` among `n` items, patching a
set `M` of failed items gives the observed score `|P|/n + |M|/n`. -/
theorem L3_patch_count {n : ℕ} (P M : Finset (Fin n)) (hM : M ⊆ Pᶜ) :
    ((P ∪ M).card : ℝ) / n = (P.card : ℝ) / n + (M.card : ℝ) / n := by
  have hd : Disjoint P M := by
    rw [disjoint_iff_ne]
    intro a ha b hb hab
    subst hab
    exact (mem_compl.1 (hM hb)) ha
  rw [card_union_of_disjoint hd]
  push_cast
  rw [add_div]

/-- Item-level derivation of the blind score: averaging over all `C(n, m)` memorized sets `M` of
size `m`, the observed score `|P ∪ M| / n` is `m/n + (1 - m/n) v` with `v = |P|/n`. -/
theorem L3_blind_average {n m : ℕ} (hn : 0 < n) (hm : m ≤ n) (P : Finset (Fin n)) :
    (∑ M ∈ powersetCard m (univ : Finset (Fin n)), ((P ∪ M).card : ℝ)) / (n.choose m) / n =
      (m : ℝ) / n + (1 - (m : ℝ) / n) * ((P.card : ℝ) / n) := by
  -- count in ℕ first
  have hcount : ∀ i : Fin n,
      ((powersetCard m (univ : Finset (Fin n))).filter fun M => i ∉ M).card = (n - 1).choose m := by
    intro i
    have : ((powersetCard m (univ : Finset (Fin n))).filter fun M => i ∉ M) =
        powersetCard m (univ.erase i) := by
      ext M
      simp only [mem_filter, mem_powersetCard, subset_erase, subset_univ, true_and]
      tauto
    rw [this, card_powersetCard, card_erase_of_mem (mem_univ i), card_univ, Fintype.card_fin]
  have hsum : ∑ M ∈ powersetCard m (univ : Finset (Fin n)), (P ∪ M).card =
      n.choose m * m + P.card * (n - 1).choose m := by
    have h1 : ∀ M ∈ powersetCard m (univ : Finset (Fin n)),
        (P ∪ M).card = m + ∑ i ∈ P, if i ∉ M then 1 else 0 := by
      intro M hM
      rw [← card_sdiff_add_card, (mem_powersetCard.1 hM).2, add_comm (P \ M).card m,
        sdiff_eq_filter, card_filter]
    rw [sum_congr rfl h1, sum_add_distrib, sum_const, card_powersetCard, card_univ,
      Fintype.card_fin, smul_eq_mul, sum_comm]
    congr 1
    calc ∑ i ∈ P, ∑ M ∈ powersetCard m (univ : Finset (Fin n)), (if i ∉ M then 1 else 0)
        = ∑ _i ∈ P, (n - 1).choose m :=
          sum_congr rfl fun i _ => by rw [← card_filter, hcount i]
      _ = P.card * (n - 1).choose m := by rw [sum_const, smul_eq_mul]
  have hchoose : ((n - 1).choose m : ℝ) * n = (n.choose m : ℝ) * (n - m) := by
    have h := Nat.choose_mul_succ_eq (n - 1) m
    rw [Nat.sub_add_cancel hn] at h
    rw [← Nat.cast_sub hm]
    exact_mod_cast h
  have hn' : (0 : ℝ) < n := by exact_mod_cast hn
  have hC : (0 : ℝ) < n.choose m := by exact_mod_cast Nat.choose_pos hm
  have hsumR : ∑ M ∈ powersetCard m (univ : Finset (Fin n)), ((P ∪ M).card : ℝ) =
      (n.choose m : ℝ) * m + (P.card : ℝ) * ((n - 1).choose m : ℝ) := by
    exact_mod_cast hsum
  have hC' : ((n - 1).choose m : ℝ) = (n.choose m : ℝ) * (n - m) / n :=
    (eq_div_iff hn'.ne').2 hchoose
  rw [hsumR, hC']
  field_simp

/-- **L3, fixture.** Clean accuracy `4/5` and judge error `1/10` give the observed accuracy
`v = 4/5 · 9/10 + 1/5 · 1/10 = 37/50`; the blind-memorization threshold is `8/13` of the set; the
failure-patching threshold is `4/25` of the set, which is `8/13` of the failed items. -/
theorem L3_fixture :
    (4 / 5 : ℝ) * (1 - 1 / 10) + (1 - 4 / 5) * (1 / 10) = 37 / 50 ∧
    ((1 : ℝ) - 1 / 10 - 37 / 50) / (1 - 37 / 50) = 8 / 13 ∧
    (1 : ℝ) - 1 / 10 - 37 / 50 = 4 / 25 ∧
    ((4 : ℝ) / 25) / (1 - 37 / 50) = 8 / 13 := by
  norm_num

/-- **L3, fixture as thresholds.** At `v = 37/50` and `ε = 1/10`: blind memorization crosses the
ceiling iff more than `8/13` of the set is memorized; failure patching iff more than `4/25` of the
set is patched, i.e. more than `8/13` of the failed items. -/
theorem L3_fixture_thresholds :
    (∀ x : ℝ, 1 - 1 / 10 < blindScore (37 / 50) x ↔ 8 / 13 < x) ∧
    (∀ x : ℝ, 1 - 1 / 10 < patchScore (37 / 50) x ↔ 4 / 25 < x) ∧
    (∀ y : ℝ, 1 - 1 / 10 < patchScore (37 / 50) (y * (1 - 37 / 50)) ↔ 8 / 13 < y) := by
  refine ⟨fun x => ?_, fun x => ?_, fun y => ?_⟩
  · rw [L3_blind (by norm_num)]; norm_num
  · rw [L3_patch]; norm_num
  · rw [L3_patch_share_of_failed (by norm_num)]; norm_num

/-! ## L4. A judge that shares errors with the judged -/

/-- Observed accuracy with a judge wrong at rate `e0` on items the controller gets right and `e1`
on items it gets wrong, the controller being right with probability `a`. -/
def observed (a e0 e1 : ℝ) : ℝ := a * (1 - e0) + (1 - a) * e1

/-- The judge's marginal error rate `ε = a e0 + (1 - a) e1`. -/
def marginal (a e0 e1 : ℝ) : ℝ := a * e0 + (1 - a) * e1

/-- **L4, identity.** `a(1 - ε₀) + (1 - a)ε₁ = a - ε + 2(1 - a)ε₁`. -/
theorem L4_identity (a e0 e1 : ℝ) :
    observed a e0 e1 = a - marginal a e0 e1 + 2 * (1 - a) * e1 := by
  unfold observed marginal; ring

/-- **L4, excess.** Against an independent judge with the same marginal error `ε`, the observed
accuracy is higher by exactly `2(1 - a)(ε₁ - ε)`. -/
theorem L4_excess (a e0 e1 : ℝ) :
    observed a e0 e1 - observed a (marginal a e0 e1) (marginal a e0 e1) =
      2 * (1 - a) * (e1 - marginal a e0 e1) := by
  unfold observed marginal; ring

/-- **L4, ceiling.** For `a < 1` the observed accuracy reaches the ceiling `1 - ε` iff
`ε₁ ≥ 1/2`, whatever `a` and `ε`. (The note states it for `0 < a < 1`; `a = 0` is included.) -/
theorem L4_ceiling_iff {a e0 e1 : ℝ} (ha : a < 1) :
    1 - marginal a e0 e1 ≤ observed a e0 e1 ↔ 1 / 2 ≤ e1 := by
  rw [L4_identity]
  have h : 0 < 1 - a := by linarith
  constructor
  · intro hc; nlinarith
  · intro hc; nlinarith

/-- **L4, feasibility cap.** A judge with `ε₀ ≥ 0` has `(1 - a) ε₁ ≤ ε`, i.e. `ε₁ ≤ ε / (1 - a)`. -/
theorem L4_cap {a e0 e1 : ℝ} (ha : 0 ≤ a) (he0 : 0 ≤ e0) : (1 - a) * e1 ≤ marginal a e0 e1 := by
  unfold marginal; nlinarith [mul_nonneg ha he0]

/-- **L4, reachability.** For `0 < a < 1` and `ε ≤ 1`, some feasible judge (rates in
`[0, 1]` with marginal `ε`) reports at least the ceiling `1 - ε` iff `ε ≥ (1 - a)/2`. -/
theorem L4_reachable_iff {a ε : ℝ} (ha0 : 0 < a) (ha1 : a < 1) (hε1 : ε ≤ 1) :
    (∃ e0 e1 : ℝ, 0 ≤ e0 ∧ e0 ≤ 1 ∧ 0 ≤ e1 ∧ e1 ≤ 1 ∧ marginal a e0 e1 = ε ∧
        1 - ε ≤ observed a e0 e1) ↔ (1 - a) / 2 ≤ ε := by
  constructor
  · rintro ⟨e0, e1, h0, -, -, -, hm, hc⟩
    rw [← hm] at hc
    have he1 := (L4_ceiling_iff ha1).1 hc
    have hcap := L4_cap (e1 := e1) ha0.le h0
    rw [hm] at hcap
    nlinarith
  · intro hε
    have ha0' : a ≠ 0 := ha0.ne'
    have ha1' : 1 - a ≠ 0 := by linarith
    rcases le_or_gt ε ((1 + a) / 2) with hle | hgt
    · refine ⟨(ε - (1 - a) / 2) / a, 1 / 2, div_nonneg (by linarith) ha0.le, ?_, by norm_num,
        by norm_num, ?_, ?_⟩
      · rw [div_le_one ha0]; linarith
      · unfold marginal; field_simp; ring
      · have hm : marginal a ((ε - (1 - a) / 2) / a) (1 / 2) = ε := by
          unfold marginal; field_simp; ring
        have := (L4_ceiling_iff (e0 := (ε - (1 - a) / 2) / a) ha1).2 (le_refl _)
        rwa [hm] at this
    · have h1a : 0 < 1 - a := by linarith
      refine ⟨1, (ε - a) / (1 - a), by norm_num, le_refl _, div_nonneg (by linarith) h1a.le,
        ?_, ?_, ?_⟩
      · rw [div_le_one h1a]; linarith
      · unfold marginal; field_simp; ring
      · have hm : marginal a 1 ((ε - a) / (1 - a)) = ε := by
          unfold marginal; field_simp; ring
        have hhalf : 1 / 2 ≤ (ε - a) / (1 - a) := by
          rw [le_div_iff₀ h1a]; linarith
        have := (L4_ceiling_iff (e0 := 1) ha1).2 hhalf
        rwa [hm] at this

/-- **L4, most correlated feasible judge.** With `a ≥ 0` and `ε₀ ≥ 0`, observed accuracy is at most
`a + ε`. -/
theorem L4_observed_le {a e0 e1 : ℝ} (ha : 0 ≤ a) (he0 : 0 ≤ e0) :
    observed a e0 e1 ≤ a + marginal a e0 e1 := by
  have := L4_cap (e1 := e1) ha he0
  rw [L4_identity]; linarith

/-- **L4, fixture** (`a = 4/5`, `ε = 1/10`): the independent judge reports `37/50`; the most
correlated feasible judge (`ε₀ = 0`, `ε₁ = ε/(1 - a) = 1/2`) has marginal `1/10` and reports
`9/10`, the ceiling; the inflation is `4/25`. -/
theorem L4_fixture :
    observed (4 / 5) (1 / 10) (1 / 10) = 37 / 50 ∧
    marginal (4 / 5) 0 (1 / 2) = 1 / 10 ∧
    observed (4 / 5) 0 (1 / 2) = 9 / 10 ∧
    observed (4 / 5) 0 (1 / 2) = 1 - 1 / 10 ∧
    observed (4 / 5) 0 (1 / 2) - observed (4 / 5) (1 / 10) (1 / 10) = 4 / 25 := by
  unfold observed marginal; norm_num

/-! ## L6. Finer feedback is worth at least as much (Blackwell, garbling direction) -/

/-- Reordering a triple sum. -/
theorem sum_comm3 {α β γ : Type*} [Fintype α] [Fintype β] [Fintype γ] (F : α → β → γ → ℝ) :
    ∑ a, ∑ b, ∑ c, F a b c = ∑ c, ∑ a, ∑ b, F a b c :=
  calc ∑ a, ∑ b, ∑ c, F a b c = ∑ a, ∑ c, ∑ b, F a b c :=
        Finset.sum_congr rfl fun _ _ => Finset.sum_comm
    _ = ∑ c, ∑ a, ∑ b, F a b c := Finset.sum_comm

section Blackwell

variable {Θ R Y Y' Act : Type*} [Fintype Θ] [Fintype R] [Fintype Act] [Nonempty Act]

/-- Expected utility of the decision rule `δ` (signal ↦ action) when the loop sees `g r` for the
record `r`, a type `θ` has prior weight `prior θ`, and a record `r` has likelihood `lik θ r`. -/
def expUtil (prior : Θ → ℝ) (lik : Θ → R → ℝ) (u : Act → Θ → ℝ) (g : R → Y) (δ : Y → Act) : ℝ :=
  ∑ θ, ∑ r, prior θ * lik θ r * u (δ (g r)) θ

/-- Bayes value of the deterministic channel `g`: the best expected utility over all decision
rules on `g`'s images. -/
def bayesValue [Fintype Y] [DecidableEq Y] (prior : Θ → ℝ) (lik : Θ → R → ℝ)
    (u : Act → Θ → ℝ) (g : R → Y) : ℝ :=
  univ.sup' univ_nonempty (expUtil prior lik u g)

/-- **L6.** For finite types, any prior, any likelihood of records given types and any utility, the
Bayes value under channel `g` is at least the value under any channel `f` that factors through
`g`. No sign condition on the weights is needed. -/
theorem L6_garbling [Fintype Y] [DecidableEq Y] [Fintype Y'] [DecidableEq Y']
    (prior : Θ → ℝ) (lik : Θ → R → ℝ) (u : Act → Θ → ℝ) (g : R → Y) (f : R → Y')
    (k : Y → Y') (hf : ∀ r, f r = k (g r)) :
    bayesValue prior lik u f ≤ bayesValue prior lik u g := by
  apply Finset.sup'_le
  intro δ _
  have : expUtil prior lik u f δ = expUtil prior lik u g (δ ∘ k) := by
    simp only [expUtil, hf, Function.comp_apply]
  rw [this]
  exact Finset.le_sup' _ (mem_univ _)

/-- Expected utility of `δ` under a stochastic channel `G r y = Pr[signal y | record r]`. -/
def expUtilK (prior : Θ → ℝ) (lik : Θ → R → ℝ) (u : Act → Θ → ℝ) (G : R → Y → ℝ)
    (δ : Y → Act) [Fintype Y] : ℝ :=
  ∑ θ, ∑ r, ∑ y, prior θ * lik θ r * G r y * u (δ y) θ

/-- Bayes value of a stochastic channel. -/
def bayesValueK [Fintype Y] [DecidableEq Y] (prior : Θ → ℝ) (lik : Θ → R → ℝ)
    (u : Act → Θ → ℝ) (G : R → Y → ℝ) : ℝ :=
  univ.sup' univ_nonempty fun δ => expUtilK prior lik u G δ

/-- The garbling `K ∘ G` of a stochastic channel by a Markov kernel `K`. -/
def garble [Fintype Y] (G : R → Y → ℝ) (K : Y → Y' → ℝ) : R → Y' → ℝ :=
  fun r y' => ∑ y, G r y * K y y'

/-- **L6, stochastic garbling (strengthening).** If `K` is a Markov kernel (non-negative entries,
rows summing to one), the Bayes value of `K ∘ G` is at most that of `G`, for any prior, likelihood
and utility. The deterministic case is `K y y' = [y' = k y]`. -/
theorem L6_garbling_stochastic [Fintype Y] [DecidableEq Y] [Fintype Y'] [DecidableEq Y']
    (prior : Θ → ℝ) (lik : Θ → R → ℝ) (u : Act → Θ → ℝ) (G : R → Y → ℝ) (K : Y → Y' → ℝ)
    (hK0 : ∀ y y', 0 ≤ K y y') (hK1 : ∀ y, ∑ y', K y y' = 1) :
    bayesValueK prior lik u (garble G K) ≤ bayesValueK prior lik u G := by
  set h : Y → Act → ℝ := fun y a => ∑ θ, ∑ r, prior θ * lik θ r * G r y * u a θ with hh
  have hG : ∀ δ : Y → Act, expUtilK prior lik u G δ = ∑ y, h y (δ y) := by
    intro δ
    simp only [expUtilK, hh]
    exact sum_comm3 _
  have hGK : ∀ δ : Y' → Act, expUtilK prior lik u (garble G K) δ =
      ∑ y', ∑ y, K y y' * h y (δ y') := by
    intro δ
    calc expUtilK prior lik u (garble G K) δ
        = ∑ θ, ∑ r, ∑ y', ∑ y, K y y' * (prior θ * lik θ r * G r y * u (δ y') θ) := by
          simp only [expUtilK, garble, Finset.mul_sum, Finset.sum_mul]
          refine sum_congr rfl fun θ _ => sum_congr rfl fun r _ => sum_congr rfl fun y' _ =>
            sum_congr rfl fun y _ => by ring
      _ = ∑ y', ∑ θ, ∑ r, ∑ y, K y y' * (prior θ * lik θ r * G r y * u (δ y') θ) :=
          sum_comm3 _
      _ = ∑ y', ∑ y, ∑ θ, ∑ r, K y y' * (prior θ * lik θ r * G r y * u (δ y') θ) :=
          sum_congr rfl fun y' _ => sum_comm3 _
      _ = ∑ y', ∑ y, K y y' * h y (δ y') := by
          simp only [hh, Finset.mul_sum]
  -- a best response for each signal of `G`
  have hbest : ∀ y, ∃ a, ∀ a', h y a' ≤ h y a := fun y => Finite.exists_max (h y)
  choose b hb using hbest
  apply Finset.sup'_le
  intro δ _
  rw [hGK]
  calc ∑ y', ∑ y, K y y' * h y (δ y') ≤ ∑ y', ∑ y, K y y' * h y (b y) :=
        sum_le_sum fun y' _ => sum_le_sum fun y _ =>
          mul_le_mul_of_nonneg_left (hb y (δ y')) (hK0 y y')
    _ = ∑ y, (∑ y', K y y') * h y (b y) := by
        rw [Finset.sum_comm]
        refine Finset.sum_congr rfl fun y _ => ?_
        rw [Finset.sum_mul]
    _ = ∑ y, h y (b y) := by simp [hK1]
    _ = expUtilK prior lik u G b := (hG b).symm
    _ ≤ bayesValueK prior lik u G := Finset.le_sup' (fun δ => expUtilK prior lik u G δ) (mem_univ b)

end Blackwell

end FeedbackChannel.Signal

import Mathlib.Tactic

/-!
# Conservation and claim preservation under authenticated collateral release

State: `locked p` (collateral of party `p` held by a clearing vault or escrow), `free p`
(value under `p`'s own spend authority) and `claim p q` (matured, enforceable amount `p`
owes `q` from its locked collateral). All amounts are integer satoshis (ℤ, with
non-negativity carried as an invariant).

Two release transitions exist, and both require an authenticated statement `auth s`
(a verified clearing statement, e.g. a Nova proof accepted by the settlement layer):

* `pay p q a`: pays `a ≤ claim p q` from `p`'s collateral to `q`, reducing the claim;
* `unlock p a`: returns `a` of `p`'s collateral to `p`, only out of the excess over its
  outstanding claims.

`Theorems`: total value `Σ (locked + free)` is conserved; the backing invariant
`Σ_q claim p q ≤ locked p` is preserved; and any increase of a party's free balance is
witnessed by an authenticated statement. A release recorded in a simulation without
such a statement is outside these transitions: the theorems say nothing about it.
-/

namespace Spiral.Rent

variable {P S : Type*} [Fintype P] [DecidableEq P]

structure CState (P : Type*) where
  locked : P → ℤ
  free : P → ℤ
  claim : P → P → ℤ

def total [Fintype P] (s : CState P) : ℤ := ∑ p, (s.locked p + s.free p)

def Backed [Fintype P] (s : CState P) : Prop :=
  ∀ p, ∑ q, s.claim p q ≤ s.locked p

def Nonneg (s : CState P) : Prop :=
  (∀ p, 0 ≤ s.locked p) ∧ (∀ p, 0 ≤ s.free p) ∧ (∀ p q, 0 ≤ s.claim p q)

inductive Step (auth : S → Prop) : CState P → CState P → Prop where
  | pay (s : CState P) (st : S) (h : auth st) (p q : P) (a : ℤ)
      (ha : 0 ≤ a) (hc : a ≤ s.claim p q) :
      Step auth s
        { locked := Function.update s.locked p (s.locked p - a)
          free := Function.update s.free q (s.free q + a)
          claim := Function.update s.claim p (Function.update (s.claim p) q (s.claim p q - a)) }
  | unlock (s : CState P) (st : S) (h : auth st) (p : P) (a : ℤ)
      (ha : 0 ≤ a) (hx : a + ∑ q, s.claim p q ≤ s.locked p) :
      Step auth s
        { locked := Function.update s.locked p (s.locked p - a)
          free := Function.update s.free p (s.free p + a)
          claim := s.claim }

private lemma sum_update_add (f : P → ℤ) (p : P) (b : ℤ) :
    ∑ x, Function.update f p (f p + b) x = (∑ x, f x) + b := by
  rw [Finset.sum_update_of_mem (Finset.mem_univ p), ← Finset.add_sum_erase _ _ (Finset.mem_univ p)]
  rw [Finset.sdiff_singleton_eq_erase]
  ring

private lemma sum_update_sub (f : P → ℤ) (p : P) (b : ℤ) :
    ∑ x, Function.update f p (f p - b) x = (∑ x, f x) - b := by
  have := sum_update_add f p (-b)
  simp only [sub_eq_add_neg] at *
  exact this

theorem step_conserves {auth : S → Prop} {s t : CState P} (h : Step auth s t) :
    total t = total s := by
  cases h with
  | pay st hst p q a ha hc =>
      unfold total
      dsimp only
      simp only [Finset.sum_add_distrib]
      rw [sum_update_sub, sum_update_add]
      ring
  | unlock st hst p a ha hx =>
      unfold total
      dsimp only
      simp only [Finset.sum_add_distrib]
      rw [sum_update_sub, sum_update_add]
      ring

theorem step_preserves_backing {auth : S → Prop} {s t : CState P} (hb : Backed s)
    (h : Step auth s t) : Backed t := by
  cases h with
  | pay st hst p q a ha hc =>
      intro r
      dsimp only
      by_cases hr : r = p
      · subst hr
        rw [Function.update_self, Function.update_self, sum_update_sub]
        have := hb r
        linarith
      · rw [Function.update_of_ne hr, Function.update_of_ne hr]
        exact hb r
  | unlock st hst p a ha hx =>
      intro r
      dsimp only
      by_cases hr : r = p
      · subst hr
        rw [Function.update_self]
        linarith
      · rw [Function.update_of_ne hr]
        exact hb r

/-- Free balances only grow through an authenticated step. -/
theorem free_increase_authenticated {auth : S → Prop} {s t : CState P}
    (h : Step auth s t) : ∃ st, auth st := by
  cases h with
  | pay st hst _ _ _ _ _ => exact ⟨st, hst⟩
  | unlock st hst _ _ _ _ => exact ⟨st, hst⟩

/-- Reflexive-transitive closure: conservation and backing hold along any history. -/
theorem history_invariants {auth : S → Prop} {s t : CState P}
    (h : Relation.ReflTransGen (Step auth) s t) (hb : Backed s) :
    total t = total s ∧ Backed t := by
  induction h with
  | refl => exact ⟨rfl, hb⟩
  | tail _ hstep ih =>
      exact ⟨(step_conserves hstep).trans ih.1, step_preserves_backing ih.2 hstep⟩

end Spiral.Rent
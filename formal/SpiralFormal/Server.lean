import Mathlib.Tactic

/-!
# Spiral: server capital admission

Paper: "Where the Capital Bound Moves", Section 4, bound relocation.
Reference code: model/server.ts.

The implementation's atomic admission check is:
  committed + grossInputValue ≤ capital.
Forfeiture raises committed by the full input value; sweep lowers it.
The preserved invariant is therefore committed ≤ capital.

The paper's separate inequality over cumulative allocation amounts
is not this invariant. A counterexample below uses its 1.3-million-
satoshi fixture. Recycled capital and simultaneous commitments differ.
-/

namespace Spiral.CapitalBound

/-- Server capital and currently forfeited-but-unrecovered value. -/
structure ServerState where
  capital : Nat
  committed : Nat
  deriving Repr, DecidableEq

/-- An initially unencumbered capital stock. -/
def ServerState.initial (capital : Nat) : ServerState := ⟨capital, 0⟩

/-- The actual instantaneous outstanding-capital budget. -/
def ServerSafe (s : ServerState) : Prop :=
  s.committed ≤ s.capital

/-- Atomic forfeit (full input amount), sweep, and rejected attempt. -/
inductive ServerStep : ServerState → ServerState → Prop where
  | front (s : ServerState) (gross : Nat)
      (admitted : s.committed + gross ≤ s.capital) :
      ServerStep s { s with committed := s.committed + gross }
  | recover (s : ServerState) (amount : Nat)
      (available : amount ≤ s.committed) :
      ServerStep s { s with committed := s.committed - amount }
  | unchanged (s : ServerState) : ServerStep s s

/-- Finite histories of admitted capital changes. -/
inductive ServerTrace : ServerState → ServerState → Prop where
  | refl (s : ServerState) : ServerTrace s s
  | next {s t u : ServerState} :
      ServerStep s t → ServerTrace t u → ServerTrace s u

/-- Server steps preserve the total capital parameter. -/
theorem serverStep_capital_fixed {s t : ServerState}
    (h : ServerStep s t) : t.capital = s.capital := by
  cases h <;> rfl

/-- A sequence of steps leaves the server's total capital unchanged. -/
theorem serverTrace_capital_fixed {s t : ServerState}
    (h : ServerTrace s t) : t.capital = s.capital := by
  induction h with
  | refl _ => rfl
  | next hstep _ ih =>
      exact ih.trans (serverStep_capital_fixed hstep)

/-- The server starts below its capital ceiling. -/
theorem serverSafe_initial (capital : Nat) :
    ServerSafe (ServerState.initial capital) := by
  simp [ServerSafe, ServerState.initial]

/-- Fronting, sweeping, and unchanged requests preserve the budget. -/
theorem serverStep_preserves {s t : ServerState}
    (h : ServerSafe s) (step : ServerStep s t) : ServerSafe t := by
  cases step <;> dsimp [ServerSafe] at * <;> omega

/-- Current outstanding capital stays within the budget at every prefix. -/
theorem server_capital_bound {capital : Nat} {s : ServerState}
    (history : ServerTrace (ServerState.initial capital) s) :
    s.committed ≤ capital := by
  have aux : ∀ (s t : ServerState), ServerTrace s t →
      ServerSafe s → ServerSafe t := by
    intro a b htrace
    induction htrace with
    | refl _ =>
        intro h
        exact h
    | next hstep _ ih =>
        intro h
        exact ih (serverStep_preserves h hstep)
  have hs : ServerSafe s :=
    aux _ _ history (serverSafe_initial capital)
  have hc : s.capital = capital := by
    simpa [ServerState.initial] using (serverTrace_capital_fixed history)
  dsimp [ServerSafe] at hs
  omega

/-- Equivalent forms of the implementation's admission rule. -/
theorem fronting_fits_headroom (s : ServerState) (gross : Nat)
    (h : ServerSafe s) :
    (s.committed + gross ≤ s.capital) ↔
      (gross ≤ s.capital - s.committed) := by
  dsimp [ServerSafe] at h
  omega

/-- The paper's cumulative-spend reading conflicts with current headroom:
three 300,000-sat spends can commit 1,200,000 sat from full 400,000-sat
inputs, leaving 100,000 sat of a 1,300,000-sat server budget. -/
theorem cumulative_allocation_not_headroom :
    ¬ (900000 ≤ 1300000 - 1200000) := by
  norm_num

end Spiral.CapitalBound

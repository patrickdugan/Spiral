import Mathlib.Tactic

/-!
# Spiral: clock-gated settlement ledger accounting

Paper: "Where the Capital Bound Moves", Section 4, cross-class conservation.
Reference implementation: model/ledger.ts.

Source and destination stand for arbitrary (class, holder) accounts
at an event boundary. Holds reserve funds inside the source's settled
balance, rather than minting additional claims. LedgerStep allows
funding, initiation, abort, ordinary settlement, a challenge slash and
unmodified clock ticks or rejected attempts.

Each accepted settlement is assumed to have a corresponding pending
journal event whose clock has fired; the theorem below proves accounting
conditional on that check and on reserve sufficiency. It does not yet
verify event IDs, settlement clocks, or the TypeScript Map implementation.
-/

namespace Spiral.CapitalBound

/-- A two-account projection of the cross-class ledger. All amounts
(including relay fees and slashed collateral) are integer satoshis. -/
structure LedgerState where
  source : Nat
  destination : Nat
  held : Nat
  fees : Nat
  slashed : Nat
  external : Nat
  deriving Repr, DecidableEq

/-- Opening balances are the initial external endowment; zero holds and fees. -/
def LedgerState.initial (source destination : Nat) : LedgerState :=
  ⟨source, destination, 0, 0, 0, source + destination⟩

/-- Holds remain part of the settled source balance. The two equations
also ensure no available balance becomes negative. -/
def LedgerSafe (s : LedgerState) : Prop :=
  s.held ≤ s.source ∧
  s.source + s.destination + s.fees + s.slashed = s.external

/-- Account and journal operations. A successful clock check is required
by the caller before choosing a settle or slash constructor. -/
inductive LedgerStep : LedgerState → LedgerState → Prop where
  | funding (s : LedgerState) (amount : Nat) :
      LedgerStep s { s with
        source := s.source + amount
        external := s.external + amount }
  | initiate (s : LedgerState) (amount fee : Nat)
      (available : s.held + amount + fee ≤ s.source) :
      LedgerStep s { s with held := s.held + amount + fee }
  | abort (s : LedgerState) (amount fee : Nat)
      (reserved : amount + fee ≤ s.held) :
      LedgerStep s { s with held := s.held - (amount + fee) }
  | settle (s : LedgerState) (amount fee : Nat)
      (reserved : amount + fee ≤ s.held)
      (backed : s.held ≤ s.source) :
      LedgerStep s { s with
        held := s.held - (amount + fee)
        source := s.source - (amount + fee)
        destination := s.destination + amount
        fees := s.fees + fee }
  | slash (s : LedgerState) (amount fee : Nat)
      (reserved : amount + fee ≤ s.held)
      (backed : s.held ≤ s.source) :
      LedgerStep s { s with
        held := s.held - (amount + fee)
        source := s.source - (amount + fee)
        slashed := s.slashed + amount
        fees := s.fees + fee }
  | unchanged (s : LedgerState) : LedgerStep s s

/-- Repeated clocked operations. Each prefix has its own safety invariant. -/
inductive LedgerTrace : LedgerState → LedgerState → Prop where
  | refl (s : LedgerState) : LedgerTrace s s
  | next {s t u : LedgerState} :
      LedgerStep s t → LedgerTrace t u → LedgerTrace s u

/-- Funding initially establishes conservation. -/
theorem ledgerSafe_initial (source destination : Nat) :
    LedgerSafe (LedgerState.initial source destination) := by
  simp [LedgerSafe, LedgerState.initial]

/-- Every modeled settlement transition preserves the reserve guard and
the conservation identity, including fees and challenged collateral. -/
theorem ledgerStep_preserves {s t : LedgerState}
    (h : LedgerSafe s) (step : LedgerStep s t) : LedgerSafe t := by
  rcases h with ⟨hreserve, hvalue⟩
  cases step <;>
    constructor <;> (try dsimp [LedgerSafe] at *) <;> omega

/-- Ledger accounting survives every finite sequence of guarded operations. -/
theorem ledgerTrace_preserves {s t : LedgerState}
    (trace : LedgerTrace s t) :
    LedgerSafe s → LedgerSafe t := by
  induction trace with
  | refl _ => intro h; exact h
  | next hstep _ ih =>
      intro h
      exact ih (ledgerStep_preserves h hstep)

/-- Throughout the execution, external funding is exactly the sum of
settled holdings, paid relay/miner fees, and accumulated slashes. -/
theorem cross_class_conservation {source destination : Nat} {s : LedgerState}
    (trace : LedgerTrace (LedgerState.initial source destination) s) :
    s.source + s.destination + s.fees + s.slashed = s.external :=
  (ledgerTrace_preserves trace (ledgerSafe_initial source destination)).2

/-- Pending holds only partition the source balance into reserved and
available capital. They create no additional settled value. -/
theorem held_plus_available_eq_source (s : LedgerState)
    (h : LedgerSafe s) :
    (s.source - s.held) + s.held = s.source := by
  have hbound := h.1
  omega

end Spiral.CapitalBound

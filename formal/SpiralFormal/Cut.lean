import Mathlib.Tactic

/-!
# Spiral: prefix cut conservation

Paper: "Where the Capital Bound Moves", Section 3, Lemma 1 and Proposition 1.

This proof leaf formalizes the cut projection of a Lightning graph.
Outbound and inbound are the nonnegative balances on opposite sides
of a fixed cut. A crossing moves value between these stocks; a funding
event increases one stock, and an internal or failed attempt leaves the
projection unchanged. Every admissible history is represented by
CutTrace. Hence the theorem quantifies over any policy's history.

Scope: a future refinement proof must map per-channel route execution
and the BIP 448 hyperedge model into these abstract transitions.
This file does not claim that correspondence has been proved.
-/

namespace Spiral.CapitalBound

/-- The aggregate stocks, completed crossings, and confirmed capital
additions of one fixed cut. All amounts are in integer satoshis. -/
structure CutState where
  outbound : Nat
  inbound : Nat
  flowOut : Nat
  flowIn : Nat
  fundedOut : Nat
  fundedIn : Nat
  deriving Repr, DecidableEq

/-- Zero flows and zero later funding with the cut's initial balances. -/
def CutState.initial (out₀ in₀ : Nat) : CutState :=
  ⟨out₀, in₀, 0, 0, 0, 0⟩

/-- The two balance identities from which the paper's inequalities follow. -/
def CutInvariant (out₀ in₀ : Nat) (s : CutState) : Prop :=
  s.outbound + s.flowOut = out₀ + s.flowIn + s.fundedOut ∧
  s.inbound + s.flowIn = in₀ + s.flowOut + s.fundedIn

/-- Abstract event semantics for one fixed cut. Only crossings with
available balance can settle. Funding is assumed already confirmed. -/
inductive CutStep : CutState → CutState → Prop where
  | outward (s : CutState) (a : Nat) (h : a ≤ s.outbound) :
      CutStep s { s with
        outbound := s.outbound - a
        inbound := s.inbound + a
        flowOut := s.flowOut + a }
  | inward (s : CutState) (a : Nat) (h : a ≤ s.inbound) :
      CutStep s { s with
        inbound := s.inbound - a
        outbound := s.outbound + a
        flowIn := s.flowIn + a }
  | fundOutbound (s : CutState) (a : Nat) :
      CutStep s { s with
        outbound := s.outbound + a
        fundedOut := s.fundedOut + a }
  | fundInbound (s : CutState) (a : Nat) :
      CutStep s { s with
        inbound := s.inbound + a
        fundedIn := s.fundedIn + a }
  | unchanged (s : CutState) : CutStep s s

/-- Finite histories under any routing policy, including oracle routing. -/
inductive CutTrace : CutState → CutState → Prop where
  | refl (s : CutState) : CutTrace s s
  | next {s t u : CutState} : CutStep s t → CutTrace t u → CutTrace s u

/-- Both conservation identities hold at initialization. -/
theorem cutInvariant_initial (out₀ in₀ : Nat) :
    CutInvariant out₀ in₀ (CutState.initial out₀ in₀) := by
  simp [CutInvariant, CutState.initial]

/-- One admissible crossing, funding event, or unchanged event preserves
both cut balances. The hypothesis describes the event, not its policy. -/
theorem cutStep_preserves {out₀ in₀ : Nat} {s t : CutState}
    (h : CutInvariant out₀ in₀ s) (hs : CutStep s t) :
    CutInvariant out₀ in₀ t := by
  rcases h with ⟨hout, hin⟩
  cases hs <;>
    constructor <;> omega

/-- A complete finite history preserves the identities at every prefix. -/
theorem cutTrace_preserves {s t : CutState} (hs : CutTrace s t) :
    ∀ out₀ in₀, CutInvariant out₀ in₀ s → CutInvariant out₀ in₀ t := by
  induction hs with
  | refl _ =>
      intro out₀ in₀ h
      exact h
  | next hstep _ ih =>
      intro out₀ in₀ h
      exact ih out₀ in₀ (cutStep_preserves h hstep)

/-- Prefix cut bound, in Nat form. Truncated subtraction expresses the
paper's integer inequalities since the right-hand sides are nonnegative. -/
theorem prefix_cut_bound {out₀ in₀ : Nat} {s : CutState}
    (history : CutTrace (CutState.initial out₀ in₀) s) :
    s.flowOut - s.flowIn ≤ out₀ + s.fundedOut ∧
    s.flowIn - s.flowOut ≤ in₀ + s.fundedIn := by
  have h := cutTrace_preserves history out₀ in₀
    (cutInvariant_initial out₀ in₀)
  rcases h with ⟨hout, hin⟩
  constructor <;> omega

/-- Uniformity over every possible admissible policy history.
The hyperedge application requires a separate projection theorem. -/
theorem policy_invariance {out₀ in₀ : Nat} {s : CutState}
    (anyPolicyHistory : CutTrace (CutState.initial out₀ in₀) s) :
    s.flowOut - s.flowIn ≤ out₀ + s.fundedOut :=
  (prefix_cut_bound anyPolicyHistory).1

end Spiral.CapitalBound

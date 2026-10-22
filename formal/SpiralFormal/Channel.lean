import SpiralFormal.Cut
import Mathlib.Tactic

/-!
# Spiral: concrete channel-to-cut refinement

Source: src/spiral_ln/algebra.py, Channel.transfer and NetworkState.apply_route.
Paper: "Where the Capital Bound Moves", Section 3.

The two endpoint balances of one channel have a conserved sum. Transfer
guards model strictly positive amounts, directional reserves and pending
locks. For a channel crossing a fixed cut, its concrete transfer projects
to a CutStep with all other crossing-channel capital framed in unchanged.

This establishes a local correspondence contract for both directions.
It does not establish that the Python loop and the staged-route commit
respect this contract on all possible execution paths. The companion
finite campaign tests that executable correspondence on 128 inputs.
-/

namespace Spiral.CapitalBound

/-- One bilateral channel with fixed capacity equal to its two balances.
Reserve and locked funds constrain the amount that can be sent. -/
structure ConcreteChannel where
  left : Nat
  right : Nat
  reserve : Nat
  lockedLeft : Nat
  lockedRight : Nat
  deriving Repr, DecidableEq

def ConcreteChannel.capacity (c : ConcreteChannel) : Nat :=
  c.left + c.right

/-- An amount is spendable by the left endpoint after reserve and HTLC lock. -/
def ConcreteChannel.LeftGuard (c : ConcreteChannel) (amount : Nat) : Prop :=
  0 < amount ∧ amount + c.reserve + c.lockedLeft ≤ c.left

/-- An amount is spendable by the right endpoint after reserve and HTLC lock. -/
def ConcreteChannel.RightGuard (c : ConcreteChannel) (amount : Nat) : Prop :=
  0 < amount ∧ amount + c.reserve + c.lockedRight ≤ c.right

def ConcreteChannel.sendLeft (c : ConcreteChannel) (amount : Nat) : ConcreteChannel :=
  { c with left := c.left - amount, right := c.right + amount }

def ConcreteChannel.sendRight (c : ConcreteChannel) (amount : Nat) : ConcreteChannel :=
  { c with right := c.right - amount, left := c.left + amount }

/-- Any guarded left-to-right transfer conserves per-channel capacity. -/
theorem sendLeft_preserves_capacity (c : ConcreteChannel) (amount : Nat)
    (h : c.LeftGuard amount) :
    (c.sendLeft amount).capacity = c.capacity := by
  dsimp [ConcreteChannel.LeftGuard] at h
  dsimp [ConcreteChannel.sendLeft, ConcreteChannel.capacity]
  omega

/-- Any guarded right-to-left transfer conserves per-channel capacity. -/
theorem sendRight_preserves_capacity (c : ConcreteChannel) (amount : Nat)
    (h : c.RightGuard amount) :
    (c.sendRight amount).capacity = c.capacity := by
  dsimp [ConcreteChannel.RightGuard] at h
  dsimp [ConcreteChannel.sendRight, ConcreteChannel.capacity]
  omega

/-- An outward crossing is one admissible abstract cut step. Other
channels contributing to the cut may have any nonnegative capital. -/
theorem sendLeft_refines_cut (c : ConcreteChannel) (a frameOut frameIn : Nat)
    (h : c.LeftGuard a) :
    ∃ t : CutState,
      CutStep (CutState.initial (c.left + frameOut) (c.right + frameIn)) t ∧
      t.outbound = (c.sendLeft a).left + frameOut ∧
      t.inbound = (c.sendLeft a).right + frameIn ∧
      t.flowOut = a := by
  let start := CutState.initial (c.left + frameOut) (c.right + frameIn)
  let finish : CutState :=
    { start with
      outbound := start.outbound - a
      inbound := start.inbound + a
      flowOut := start.flowOut + a }
  have ha : a ≤ start.outbound := by
    dsimp [ConcreteChannel.LeftGuard] at h
    dsimp [start, CutState.initial]
    omega
  refine ⟨finish, CutStep.outward start a ha, ?_, ?_, ?_⟩
  · change (c.left + frameOut) - a = (c.left - a) + frameOut
    omega
  · dsimp [finish, start, CutState.initial, ConcreteChannel.sendLeft]
    omega
  · simp [finish, start, CutState.initial]

/-- The same concrete channel transfer in the opposite direction
refines an inward crossing of the fixed cut. -/
theorem sendRight_refines_cut (c : ConcreteChannel) (a frameOut frameIn : Nat)
    (h : c.RightGuard a) :
    ∃ t : CutState,
      CutStep (CutState.initial (c.left + frameOut) (c.right + frameIn)) t ∧
      t.outbound = (c.sendRight a).left + frameOut ∧
      t.inbound = (c.sendRight a).right + frameIn ∧
      t.flowIn = a := by
  let start := CutState.initial (c.left + frameOut) (c.right + frameIn)
  let finish : CutState :=
    { start with
      outbound := start.outbound + a
      inbound := start.inbound - a
      flowIn := start.flowIn + a }
  have ha : a ≤ start.inbound := by
    dsimp [ConcreteChannel.RightGuard] at h
    dsimp [start, CutState.initial]
    omega
  refine ⟨finish, CutStep.inward start a ha, ?_, ?_, ?_⟩
  · dsimp [finish, start, CutState.initial, ConcreteChannel.sendRight]
    omega
  · change (c.right + frameIn) - a = (c.right - a) + frameIn
    omega
  · simp [finish, start, CutState.initial]

/-- If both endpoints are on the same side of a cut, shifting
capital between them leaves that side's aggregate stock unchanged. -/
theorem internal_transfer_preserves_stock (c : ConcreteChannel) (a : Nat)
    (h : c.LeftGuard a) :
    (c.sendLeft a).left + (c.sendLeft a).right = c.left + c.right :=
  sendLeft_preserves_capacity c a h

end Spiral.CapitalBound

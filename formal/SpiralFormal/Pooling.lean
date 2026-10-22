import Mathlib.Tactic

/-!
# Spiral: deterministic capital pooling inequality

Paper: "Where the Capital Bound Moves", Sections 3.3 and 5.1.

A finite family of nonnegative balances at successive times consumes at most
the sum of its per-agent peak envelopes when pooled into one stock. This is
the exact, model-independent part of the pooling argument.

The paper's asymptotic sqrt(k) and pi/2 ratios require distributions,
initial-state restrictions, drift assumptions and a limit theorem. They
are not claimed by this proof leaf. No single-path bound can establish
those expected ratios.
-/

namespace Spiral.CapitalBound

/-- For any finite observation horizon, provisioning for the peak of the
aggregate balance requires no more capital than separately provisioning
every member for its own peak balance. -/
theorem peak_of_pool_le_sum_of_peaks
    {Agent Time : Type*}
    (agents : Finset Agent) (times : Finset Time)
    (balance : Agent → Time → Nat) :
    times.sup (fun t => ∑ a ∈ agents, balance a t) ≤
      ∑ a ∈ agents, times.sup (fun t => balance a t) := by
  apply Finset.sup_le
  intro t ht
  apply Finset.sum_le_sum
  intro a ha
  exact Finset.le_sup ht

/-- A single-agent pool retains exactly the unpooled capital envelope. -/
theorem singleton_pool_has_same_peak
    {Agent Time : Type*} [DecidableEq Agent]
    (a : Agent) (times : Finset Time) (balance : Agent → Time → Nat) :
    times.sup (fun t => ∑ x ∈ ({a} : Finset Agent), balance x t) =
      times.sup (fun t => balance a t) := by
  simp

end Spiral.CapitalBound

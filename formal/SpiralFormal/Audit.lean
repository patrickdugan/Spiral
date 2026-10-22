import SpiralFormal

/-!
# Trusted-assumption inspection

Build this module separately using:
  lake build SpiralFormal.Audit

Inspect the printed axiom dependencies; a successful elaboration alone
does not establish correspondence to the reference models.
-/

#print axioms Spiral.CapitalBound.prefix_cut_bound
#print axioms Spiral.CapitalBound.policy_invariance
#print axioms Spiral.CapitalBound.server_capital_bound
#print axioms Spiral.CapitalBound.fronting_fits_headroom
#print axioms Spiral.CapitalBound.cumulative_allocation_not_headroom

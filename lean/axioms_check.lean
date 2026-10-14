import FeedbackChannel

/-! Prints the axioms each published theorem depends on. Every theorem listed in CLAIMS.md appears
here; the expected output is only `propext`, `Classical.choice` and `Quot.sound`. -/

#print axioms FeedbackChannel.Smoke.judge_identity

-- Lattice and patch policy (paper/evaluation_feedback_lattice.md)
#print axioms FeedbackChannel.PatchDP.val_succ
#print axioms FeedbackChannel.PatchDP.val_eq_of_cert
#print axioms FeedbackChannel.PatchDP.val_one_le_finisher
#print axioms FeedbackChannel.PatchDP.le_val_one
#print axioms FeedbackChannel.PatchDP.theorem10
#print axioms FeedbackChannel.PatchDP.val_one_eq
#print axioms FeedbackChannel.PatchDP.stick_eq
#print axioms FeedbackChannel.PatchDP.theorem10_attained
#print axioms FeedbackChannel.PatchDP.one_hit_rate_witness
#print axioms FeedbackChannel.PatchDP.val_le_pval
#print axioms FeedbackChannel.PatchDP.val_single
#print axioms FeedbackChannel.PatchDP.lemma9
#print axioms FeedbackChannel.PatchStatic.prop3_hitProb
#print axioms FeedbackChannel.PatchStatic.prop3_expHits
#print axioms FeedbackChannel.PatchStatic.curve_single
#print axioms FeedbackChannel.PatchGreedy.prop3_greedy
#print axioms FeedbackChannel.PatchStatic.staticT_within
#print axioms FeedbackChannel.PatchStatic.staticT_skip
#print axioms FeedbackChannel.PatchStatic.prop4_staticT
#print axioms FeedbackChannel.PatchStatic.prop4_crossing
#print axioms FeedbackChannel.PatchStatic.prop4_gap
#print axioms FeedbackChannel.PatchStatic.prop4_one_category
#print axioms FeedbackChannel.PatchStatic.prop4_singletons
#print axioms FeedbackChannel.PatchStatic.static_not_monotone
#print axioms FeedbackChannel.PatchGreedy.curve_le_dual
#print axioms FeedbackChannel.PatchGreedy.curve_eq_dual
#print axioms FeedbackChannel.PatchGreedy.alloc_le_dual
#print axioms FeedbackChannel.PatchGreedy.curve_mono_refine
#print axioms FeedbackChannel.PatchGreedy.prop5
#print axioms FeedbackChannel.PatchWitness.prop7_note_values
#print axioms FeedbackChannel.PatchWitness.prop7_note_pair_insufficient
#print axioms FeedbackChannel.PatchWitness.prop7_own_counts
#print axioms FeedbackChannel.PatchWitness.prop7_own_counts_policy
#print axioms FeedbackChannel.PatchWitness.prop7_context_pair
#print axioms FeedbackChannel.PatchWitness.prop7_with_context
#print axioms FeedbackChannel.PatchWitness3.prop7_note_context_values
#print axioms FeedbackChannel.PatchWitness.prop8_witness
#print axioms FeedbackChannel.PatchWitness.greedy_not_optimal
#print axioms FeedbackChannel.LatticeJoin.acyclic_margins_zero
#print axioms FeedbackChannel.LatticeJoin.not_acyclic_witness
#print axioms FeedbackChannel.LatticeJoin.margins_determine_int_iff
#print axioms FeedbackChannel.LatticeJoin.margins_determine_iff_acyclic
#print axioms FeedbackChannel.LatticeJoin.cells_determine_margins
#print axioms FeedbackChannel.LatticeJoin.prop2c
#print axioms FeedbackChannel.LatticeJoin.prop2c_setoid
#print axioms FeedbackChannel.LatticeJoin.prop2c_four_cycle_witness
#print axioms FeedbackChannel.LatticeOrder.prop1_mono
#print axioms FeedbackChannel.LatticeOrder.prop1_converse
#print axioms FeedbackChannel.LatticeOrder.prop2
#print axioms FeedbackChannel.LatticeOrder.prop2_item_level

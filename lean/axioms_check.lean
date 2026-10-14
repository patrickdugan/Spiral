import FeedbackChannel

/-! Prints the axioms each published theorem depends on. Every theorem the notes link to is listed
here; the expected output is only `propext`, `Classical.choice` and `Quot.sound`. -/

#print axioms FeedbackChannel.Smoke.judge_identity

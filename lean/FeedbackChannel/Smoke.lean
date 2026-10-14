import Mathlib.Tactic

/-!
# Smoke test

Checks that the toolchain and the prebuilt Mathlib load. It also states the simplest result of the
programme, the shared-error judge identity (training-signal note, L4), so the build exercises `ring`
and `nlinarith` on rationals.
-/

namespace FeedbackChannel.Smoke

/-- Observed accuracy with a judge wrong at rate `e0` on items the controller gets right and `e1` on
items it gets wrong equals `a - e + 2(1-a) e1`, where `e = a e0 + (1-a) e1`. -/
theorem judge_identity (a e0 e1 : ℚ) :
    a * (1 - e0) + (1 - a) * e1 = a - (a * e0 + (1 - a) * e1) + 2 * (1 - a) * e1 := by
  ring

end FeedbackChannel.Smoke

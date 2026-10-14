import FeedbackChannel.PatchWitness

/-!
# Proposition 7, the note's witness with totals and category count (three hits)

Source: `paper/evaluation_feedback_lattice.md` (version 0.6), Proposition 7, second witness.
Same method as `FeedbackChannel.PatchWitness` (generated bottom-up evaluation of the programme's
definition, `decide` on multisets, `norm_num` on rationals).
-/

namespace FeedbackChannel.PatchWitness3

open FeedbackChannel.PatchDP FeedbackChannel.PatchWitness

theorem v1_0x0_1x0_2x1_4x2 : val 1 {(0, 0), (1, 0), (2, 1), (4, 2)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (2, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_2x1_4x2 : val 1 {(0, 0), (0, 0), (2, 1), (4, 2)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (2, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x1_4x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (4, 2)} (1, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_2x1_4x2] <;> norm_num

theorem v1_0x0_1x0_1x1_4x2 : val 1 {(0, 0), (1, 0), (1, 1), (4, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (1, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_1x1_4x2 : val 1 {(0, 0), (0, 0), (1, 1), (4, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (1, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_1x1_4x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (1, 1), (4, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (1, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_1x1_4x2] <;> norm_num

theorem v1_0x0_1x1_1x1_3x1 : val 1 {(0, 0), (1, 1), (1, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (1, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_1x1_3x2 : val 1 {(0, 0), (0, 0), (1, 1), (3, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (1, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_1x1_3x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (1, 1), (3, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (1, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_1x1_3x2] <;> norm_num

theorem v1_0x0_1x1_1x1_2x1 : val 1 {(0, 0), (1, 1), (1, 1), (2, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (1, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_1x1_2x2 : val 1 {(0, 0), (0, 0), (1, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (1, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_1x1_2x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (1, 1), (2, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (1, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_1x1_2x2] <;> norm_num

theorem v1_0x0_1x1_1x1_1x1 : val 1 {(0, 0), (1, 1), (1, 1), (1, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (1, 1), (1, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_1x1_2x2__2x2 : firstPatch 2 {(0, 0), (1, 1), (1, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(0, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (1, 1), (1, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(0, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (1, 1), (1, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_1x1] <;> norm_num

theorem v2_0x0_1x1_1x1_2x2 : val 2 {(0, 0), (1, 1), (1, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_1x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_1x1_2x2__2x2] <;> norm_num

theorem fp2_0x0_1x1_1x1_3x2__3x2 : firstPatch 2 {(0, 0), (1, 1), (1, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(0, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(0, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_2x1, v2_0x0_1x1_1x1_2x2] <;> norm_num

theorem v2_0x0_1x1_1x1_3x2 : val 2 {(0, 0), (1, 1), (1, 1), (3, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_1x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_1x1_3x2__3x2] <;> norm_num

theorem fp2_0x0_1x1_1x1_4x2__4x2 : firstPatch 2 {(0, 0), (1, 1), (1, 1), (4, 2)} (4, 2) = (5 / 2 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(0, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(0, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_3x1, v2_0x0_1x1_1x1_3x2] <;> norm_num

theorem v2_0x0_1x1_1x1_4x2 : val 2 {(0, 0), (1, 1), (1, 1), (4, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_1x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_1x1_4x2__4x2] <;> norm_num

theorem fp2_0x0_1x1_2x1_4x2__2x1 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (4, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (1, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_1x1_4x2, v2_0x0_1x1_1x1_4x2] <;> norm_num

theorem v1_0x0_1x1_2x1_3x1 : val 1 {(0, 0), (1, 1), (2, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (2, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_2x1_3x2 : val 1 {(0, 0), (0, 0), (2, 1), (3, 2)} = (4 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (2, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (3, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (3, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x1_3x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (3, 2)} (1, 1) = (7 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_2x1_3x2] <;> norm_num

theorem v1_0x0_1x0_1x1_3x2 : val 1 {(0, 0), (1, 0), (1, 1), (3, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (1, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x1_3x2__2x1 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (3, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (1, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_1x1_3x2, v2_0x0_1x1_1x1_3x2] <;> norm_num

theorem v1_0x0_1x1_2x1_2x1 : val 1 {(0, 0), (1, 1), (2, 1), (2, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (2, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_2x1_2x2 : val 1 {(0, 0), (0, 0), (2, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (2, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x1_2x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (2, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_2x1_2x2] <;> norm_num

theorem v1_0x0_1x0_1x1_2x2 : val 1 {(0, 0), (1, 0), (1, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (1, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x1_2x2__2x1 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (2, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (1, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_1x1_2x2, v2_0x0_1x1_1x1_2x2] <;> norm_num

theorem fp2_0x0_1x1_2x1_2x2__2x2 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(0, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(0, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (1, 2), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_2x1] <;> norm_num

theorem v2_0x0_1x1_2x1_2x2 : val 2 {(0, 0), (1, 1), (2, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_2x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_2x1_2x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x1_2x2__2x2] <;> norm_num

theorem fp2_0x0_1x1_2x1_3x2__3x2 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(0, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(0, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_2x1, v2_0x0_1x1_2x1_2x2] <;> norm_num

theorem v2_0x0_1x1_2x1_3x2 : val 2 {(0, 0), (1, 1), (2, 1), (3, 2)} = (7 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_2x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_2x1_3x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x1_3x2__3x2] <;> norm_num

theorem fp2_0x0_1x1_2x1_4x2__4x2 : firstPatch 2 {(0, 0), (1, 1), (2, 1), (4, 2)} (4, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(0, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(0, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_3x1, v2_0x0_1x1_2x1_3x2] <;> norm_num

theorem v2_0x0_1x1_2x1_4x2 : val 2 {(0, 0), (1, 1), (2, 1), (4, 2)} = (5 / 2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_2x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_2x1_4x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x1_4x2__4x2] <;> norm_num

theorem fp2_0x0_2x1_2x1_4x2__2x1 : firstPatch 2 {(0, 0), (2, 1), (2, 1), (4, 2)} (2, 1) = (3 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x1_4x2, v2_0x0_1x1_2x1_4x2] <;> norm_num

theorem v1_0x0_2x1_2x1_3x1 : val 1 {(0, 0), (2, 1), (2, 1), (3, 1)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (2, 1), (2, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_1x0_2x1_3x2 : val 1 {(0, 0), (1, 0), (2, 1), (3, 2)} = (4 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (2, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (3, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (3, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_2x1_3x2__2x1 : firstPatch 2 {(0, 0), (2, 1), (2, 1), (3, 2)} (2, 1) = (17 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x1_3x2, v2_0x0_1x1_2x1_3x2] <;> norm_num

theorem v1_0x0_2x1_2x1_2x1 : val 1 {(0, 0), (2, 1), (2, 1), (2, 1)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (2, 1), (2, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_1x0_2x1_2x2 : val 1 {(0, 0), (1, 0), (2, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (2, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_2x1_2x2__2x1 : firstPatch 2 {(0, 0), (2, 1), (2, 1), (2, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x1_2x2, v2_0x0_1x1_2x1_2x2] <;> norm_num

theorem fp2_0x0_2x1_2x1_2x2__2x2 : firstPatch 2 {(0, 0), (2, 1), (2, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(0, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(0, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 2), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_2x1] <;> norm_num

theorem v2_0x0_2x1_2x1_2x2 : val 2 {(0, 0), (2, 1), (2, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 2) (by decide) (by decide) fp2_0x0_2x1_2x1_2x2__2x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x1_2x2__2x2] <;> norm_num

theorem fp2_0x0_2x1_2x1_3x2__3x2 : firstPatch 2 {(0, 0), (2, 1), (2, 1), (3, 2)} (3, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(0, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(0, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_2x1_2x1, v2_0x0_2x1_2x1_2x2] <;> norm_num

theorem v2_0x0_2x1_2x1_3x2 : val 2 {(0, 0), (2, 1), (2, 1), (3, 2)} = (8 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (3, 2) (by decide) (by decide) fp2_0x0_2x1_2x1_3x2__3x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x1_3x2__3x2] <;> norm_num

theorem fp2_0x0_2x1_2x1_4x2__4x2 : firstPatch 2 {(0, 0), (2, 1), (2, 1), (4, 2)} (4, 2) = (37 / 12 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(0, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(0, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_2x1_3x1, v2_0x0_2x1_2x1_3x2] <;> norm_num

theorem v2_0x0_2x1_2x1_4x2 : val 2 {(0, 0), (2, 1), (2, 1), (4, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 1) (by decide) (by decide) fp2_0x0_2x1_2x1_4x2__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x1_4x2__4x2] <;> norm_num

theorem fp2_1x0_2x1_2x1_4x2__1x0 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (4, 2)} (1, 0) = (4 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (2, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (2, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_2x1_2x1_4x2] <;> norm_num

theorem v1_1x0_1x0_2x1_4x2 : val 1 {(1, 0), (1, 0), (2, 1), (4, 2)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 0), (2, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_2x1_4x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (4, 2)} (1, 0) = (7 / 2 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_2x1_4x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_4x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (4, 2)} (1, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x1_4x2] <;> norm_num

theorem v1_1x0_1x0_1x1_4x2 : val 1 {(1, 0), (1, 0), (1, 1), (4, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 0), (1, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_1x1_4x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (4, 2)} (1, 0) = (3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (1, 1), (4, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_1x1_4x2] <;> norm_num

theorem fp2_1x0_1x1_1x1_4x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (4, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (1, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_1x1_4x2] <;> norm_num

theorem v1_1x0_1x1_1x1_3x1 : val 1 {(1, 0), (1, 1), (1, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (1, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_1x1_3x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (3, 2)} (1, 0) = (3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (1, 1), (3, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_1x1_3x2] <;> norm_num

theorem fp2_1x0_1x1_1x1_3x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (3, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (1, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_1x1_3x2] <;> norm_num

theorem v1_1x0_1x1_1x1_2x1 : val 1 {(1, 0), (1, 1), (1, 1), (2, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (1, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_1x1_2x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (2, 2)} (1, 0) = (3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (1, 1), (2, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_1x1_2x2] <;> norm_num

theorem fp2_1x0_1x1_1x1_2x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (2, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (1, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_1x1_2x2] <;> norm_num

theorem v1_1x0_1x1_1x1_1x1 : val 1 {(1, 0), (1, 1), (1, 1), (1, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (1, 1), (1, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_1x1_2x2__2x2 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (1, 1), (1, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 0), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (1, 1), (1, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_1x1] <;> norm_num

theorem v2_1x0_1x1_1x1_2x2 : val 2 {(1, 0), (1, 1), (1, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_1x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_1x1_2x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_2x2__2x2] <;> norm_num

theorem fp2_1x0_1x1_1x1_3x2__3x2 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 0), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_2x1, v2_1x0_1x1_1x1_2x2] <;> norm_num

theorem v2_1x0_1x1_1x1_3x2 : val 2 {(1, 0), (1, 1), (1, 1), (3, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_1x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_1x1_3x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_3x2__3x2] <;> norm_num

theorem fp2_1x0_1x1_1x1_4x2__4x2 : firstPatch 2 {(1, 0), (1, 1), (1, 1), (4, 2)} (4, 2) = (5 / 2 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 0), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_3x1, v2_1x0_1x1_1x1_3x2] <;> norm_num

theorem v2_1x0_1x1_1x1_4x2 : val 2 {(1, 0), (1, 1), (1, 1), (4, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_1x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_1x1_4x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_1x1_4x2__4x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_4x2__2x1 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (4, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 0), (1, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x0_1x1_4x2, v2_1x0_1x1_1x1_4x2] <;> norm_num

theorem v1_1x0_1x1_2x1_3x1 : val 1 {(1, 0), (1, 1), (2, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (2, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_2x1_3x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (3, 2)} (1, 0) = (10 / 3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_2x1_3x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_3x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (3, 2)} (1, 1) = (7 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x1_3x2] <;> norm_num

theorem v1_1x0_1x0_1x1_3x2 : val 1 {(1, 0), (1, 0), (1, 1), (3, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 0), (1, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_2x1_3x2__2x1 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (3, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 0), (1, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x0_1x1_3x2, v2_1x0_1x1_1x1_3x2] <;> norm_num

theorem v1_1x0_1x1_2x1_2x1 : val 1 {(1, 0), (1, 1), (2, 1), (2, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (2, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_2x1_2x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (2, 2)} (1, 0) = (3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_2x1_2x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_2x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (2, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x1_2x2] <;> norm_num

theorem v1_1x0_1x0_1x1_2x2 : val 1 {(1, 0), (1, 0), (1, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 0), (1, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_2x1_2x2__2x1 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (2, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 0), (1, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x0_1x1_2x2, v2_1x0_1x1_1x1_2x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_2x2__2x2 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 0), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (1, 2), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_2x1] <;> norm_num

theorem v2_1x0_1x1_2x1_2x2 : val 2 {(1, 0), (1, 1), (2, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_2x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_2x1_2x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_2x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_2x2__2x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_3x2__3x2 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 0), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x1_2x1, v2_1x0_1x1_2x1_2x2] <;> norm_num

theorem v2_1x0_1x1_2x1_3x2 : val 2 {(1, 0), (1, 1), (2, 1), (3, 2)} = (7 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_2x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_2x1_3x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_3x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_3x2__3x2] <;> norm_num

theorem fp2_1x0_1x1_2x1_4x2__4x2 : firstPatch 2 {(1, 0), (1, 1), (2, 1), (4, 2)} (4, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 0), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x1_3x1, v2_1x0_1x1_2x1_3x2] <;> norm_num

theorem v2_1x0_1x1_2x1_4x2 : val 2 {(1, 0), (1, 1), (2, 1), (4, 2)} = (5 / 2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_2x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_2x1_4x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_4x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x1_4x2__4x2] <;> norm_num

theorem fp2_1x0_2x1_2x1_4x2__2x1 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (4, 2)} (2, 1) = (3 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x0_2x1_4x2, v2_1x0_1x1_2x1_4x2] <;> norm_num

theorem v1_1x0_2x1_2x1_3x1 : val 1 {(1, 0), (2, 1), (2, 1), (3, 1)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (2, 1), (2, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_2x1_2x1_3x2__1x0 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (3, 2)} (1, 0) = (11 / 3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (2, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_2x1_2x1_3x2] <;> norm_num

theorem v1_1x0_1x0_2x1_3x2 : val 1 {(1, 0), (1, 0), (2, 1), (3, 2)} = (4 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 0), (2, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (3, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (3, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_2x1_2x1_3x2__2x1 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (3, 2)} (2, 1) = (17 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x0_2x1_3x2, v2_1x0_1x1_2x1_3x2] <;> norm_num

theorem v1_1x0_2x1_2x1_2x1 : val 1 {(1, 0), (2, 1), (2, 1), (2, 1)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (2, 1), (2, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_2x1_2x1_2x2__1x0 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (2, 2)} (1, 0) = (3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (2, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_2x1_2x1_2x2] <;> norm_num

theorem v1_1x0_1x0_2x1_2x2 : val 1 {(1, 0), (1, 0), (2, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 0), (2, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_2x1_2x1_2x2__2x1 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (2, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x0_2x1_2x2, v2_1x0_1x1_2x1_2x2] <;> norm_num

theorem fp2_1x0_2x1_2x1_2x2__2x2 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 0), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 2), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x1_2x1] <;> norm_num

theorem v2_1x0_2x1_2x1_2x2 : val 2 {(1, 0), (2, 1), (2, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 2) (by decide) (by decide) fp2_1x0_2x1_2x1_2x2__2x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_2x1_2x1_2x2__1x0] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_2x2__2x2] <;> norm_num

theorem fp2_1x0_2x1_2x1_3x2__3x2 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (3, 2)} (3, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 0), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_2x1_2x1_2x1, v2_1x0_2x1_2x1_2x2] <;> norm_num

theorem v2_1x0_2x1_2x1_3x2 : val 2 {(1, 0), (2, 1), (2, 1), (3, 2)} = (8 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (3, 2) (by decide) (by decide) fp2_1x0_2x1_2x1_3x2__3x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_2x1_2x1_3x2__1x0] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_3x2__3x2] <;> norm_num

theorem fp2_1x0_2x1_2x1_4x2__4x2 : firstPatch 2 {(1, 0), (2, 1), (2, 1), (4, 2)} (4, 2) = (37 / 12 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 0), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_2x1_2x1_3x1, v2_1x0_2x1_2x1_3x2] <;> norm_num

theorem v2_1x0_2x1_2x1_4x2 : val 2 {(1, 0), (2, 1), (2, 1), (4, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 1) (by decide) (by decide) fp2_1x0_2x1_2x1_4x2__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_2x1_2x1_4x2__1x0] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_1x0_2x1_2x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_4x2__1x1 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (4, 2)} (1, 1) = (4 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_2x1_2x1_4x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_4x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (4, 2)} (1, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_2x1_4x2] <;> norm_num

theorem fp3_1x1_1x1_1x1_4x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (1, 1), (4, 2)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (1, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_1x1_4x2] <;> norm_num

theorem fp2_1x1_1x1_1x1_3x1__1x1 : firstPatch 2 {(1, 1), (1, 1), (1, 1), (3, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (1, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_3x1] <;> norm_num

theorem v1_1x1_1x1_1x1_2x0 : val 1 {(1, 1), (1, 1), (1, 1), (2, 0)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 1), (1, 1), (1, 1), (2, 0)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x1_1x1_1x1_2x1__1x1 : firstPatch 2 {(1, 1), (1, 1), (1, 1), (2, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (1, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_2x1] <;> norm_num

theorem fp2_1x1_1x1_1x1_1x1__1x1 : firstPatch 2 {(1, 1), (1, 1), (1, 1), (1, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (1, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (1, 1), (1, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (1, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (1, 1), (1, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_1x1] <;> norm_num

theorem v2_1x1_1x1_1x1_1x1 : val 2 {(1, 1), (1, 1), (1, 1), (1, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_1x1_1x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_1x1_1x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_1x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_1x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_1x1__1x1] <;> norm_num

theorem fp2_1x1_1x1_1x1_2x1__2x1 : firstPatch 2 {(1, 1), (1, 1), (1, 1), (2, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (1, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (1, 1), (1, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_1x1, v2_1x1_1x1_1x1_1x1] <;> norm_num

theorem v2_1x1_1x1_1x1_2x1 : val 2 {(1, 1), (1, 1), (1, 1), (2, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_1x1_2x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_1x1_2x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_2x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_2x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_2x1__2x1] <;> norm_num

theorem fp2_1x1_1x1_1x1_3x1__3x1 : firstPatch 2 {(1, 1), (1, 1), (1, 1), (3, 1)} (3, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (1, 1), (2, 0)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (1, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_1x1_2x0, v2_1x1_1x1_1x1_2x1] <;> norm_num

theorem v2_1x1_1x1_1x1_3x1 : val 2 {(1, 1), (1, 1), (1, 1), (3, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_1x1_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_1x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_1x1_3x1__3x1] <;> norm_num

theorem fp3_1x1_1x1_1x1_3x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (1, 1), (3, 2)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (1, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_1x1_3x2] <;> norm_num

theorem fp3_1x1_1x1_1x1_2x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (1, 1), (2, 2)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (1, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_1x1_2x2] <;> norm_num

theorem fp3_1x1_1x1_1x1_2x2__2x2 : firstPatch 3 {(1, 1), (1, 1), (1, 1), (2, 2)} (2, 2) = (3 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 1), (1, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (1, 1), (1, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 1), (1, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_1x1_1x1] <;> norm_num

theorem v3_1x1_1x1_1x1_2x2 : val 3 {(1, 1), (1, 1), (1, 1), (2, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_1x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_2x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_2x2__2x2] <;> norm_num

theorem fp3_1x1_1x1_1x1_3x2__3x2 : firstPatch 3 {(1, 1), (1, 1), (1, 1), (3, 2)} (3, 2) = (10 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (1, 1), (1, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_1x1_2x1, v3_1x1_1x1_1x1_2x2] <;> norm_num

theorem v3_1x1_1x1_1x1_3x2 : val 3 {(1, 1), (1, 1), (1, 1), (3, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_1x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_3x2__3x2] <;> norm_num

theorem fp3_1x1_1x1_1x1_4x2__4x2 : firstPatch 3 {(1, 1), (1, 1), (1, 1), (4, 2)} (4, 2) = (7 / 2 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (1, 1), (1, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_1x1_3x1, v3_1x1_1x1_1x1_3x2] <;> norm_num

theorem v3_1x1_1x1_1x1_4x2 : val 3 {(1, 1), (1, 1), (1, 1), (4, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_1x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_1x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_4x2__2x1 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (4, 2)} (2, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_1x1_4x2, v3_1x1_1x1_1x1_4x2] <;> norm_num

theorem fp2_1x1_1x1_2x1_3x1__1x1 : firstPatch 2 {(1, 1), (1, 1), (2, 1), (3, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_3x1] <;> norm_num

theorem fp2_1x1_1x1_2x1_3x1__2x1 : firstPatch 2 {(1, 1), (1, 1), (2, 1), (3, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (1, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_3x1, v2_1x1_1x1_1x1_3x1] <;> norm_num

theorem v1_1x1_1x1_2x0_2x1 : val 1 {(1, 1), (1, 1), (2, 0), (2, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 1), (1, 1), (2, 0), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x1_1x1_2x1_2x1__1x1 : firstPatch 2 {(1, 1), (1, 1), (2, 1), (2, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_2x1] <;> norm_num

theorem fp2_1x1_1x1_2x1_2x1__2x1 : firstPatch 2 {(1, 1), (1, 1), (2, 1), (2, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (1, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_2x1, v2_1x1_1x1_1x1_2x1] <;> norm_num

theorem v2_1x1_1x1_2x1_2x1 : val 2 {(1, 1), (1, 1), (2, 1), (2, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_2x1_2x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_2x1_2x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x1_2x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x1_2x1__2x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x1_2x1__2x1] <;> norm_num

theorem fp2_1x1_1x1_2x1_3x1__3x1 : firstPatch 2 {(1, 1), (1, 1), (2, 1), (3, 1)} (3, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 0), (2, 1)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_2x0_2x1, v2_1x1_1x1_2x1_2x1] <;> norm_num

theorem v2_1x1_1x1_2x1_3x1 : val 2 {(1, 1), (1, 1), (2, 1), (3, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_2x1_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_2x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x1_3x1__2x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x1_3x1__3x1] <;> norm_num

theorem fp3_1x1_1x1_2x1_3x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (3, 2)} (1, 1) = (10 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_2x1_3x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_3x2__2x1 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (3, 2)} (2, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_1x1_3x2, v3_1x1_1x1_1x1_3x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_2x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (2, 2)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_2x1_2x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_2x2__2x1 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (2, 2)} (2, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (1, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_1x1_2x2, v3_1x1_1x1_1x1_2x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_2x2__2x2 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (2, 2)} (2, 2) = (3 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (1, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 2), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_1x1_2x1] <;> norm_num

theorem v3_1x1_1x1_2x1_2x2 : val 3 {(1, 1), (1, 1), (2, 1), (2, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_2x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_2x1_2x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_2x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_2x2__2x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_3x2__3x2 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (3, 2)} (3, 2) = (10 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (1, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x1_2x1, v3_1x1_1x1_2x1_2x2] <;> norm_num

theorem v3_1x1_1x1_2x1_3x2 : val 3 {(1, 1), (1, 1), (2, 1), (3, 2)} = (10 / 3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_2x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_2x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_3x2__3x2] <;> norm_num

theorem fp3_1x1_1x1_2x1_4x2__4x2 : firstPatch 3 {(1, 1), (1, 1), (2, 1), (4, 2)} (4, 2) = (11 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (1, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x1_3x1, v3_1x1_1x1_2x1_3x2] <;> norm_num

theorem v3_1x1_1x1_2x1_4x2 : val 3 {(1, 1), (1, 1), (2, 1), (4, 2)} = (7 / 2 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_2x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_2x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_4x2__2x1 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (4, 2)} (2, 1) = (4 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_2x1_4x2, v3_1x1_1x1_2x1_4x2] <;> norm_num

theorem fp2_1x1_2x1_2x1_3x1__1x1 : firstPatch 2 {(1, 1), (2, 1), (2, 1), (3, 1)} (1, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_2x1_3x1] <;> norm_num

theorem fp2_1x1_2x1_2x1_3x1__2x1 : firstPatch 2 {(1, 1), (2, 1), (2, 1), (3, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x1_3x1, v2_1x1_1x1_2x1_3x1] <;> norm_num

theorem v1_1x1_2x0_2x1_2x1 : val 1 {(1, 1), (2, 0), (2, 1), (2, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 1), (2, 0), (2, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x1_2x1_2x1_2x1__1x1 : firstPatch 2 {(1, 1), (2, 1), (2, 1), (2, 1)} (1, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_2x1_2x1] <;> norm_num

theorem fp2_1x1_2x1_2x1_2x1__2x1 : firstPatch 2 {(1, 1), (2, 1), (2, 1), (2, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x1_2x1, v2_1x1_1x1_2x1_2x1] <;> norm_num

theorem v2_1x1_2x1_2x1_2x1 : val 2 {(1, 1), (2, 1), (2, 1), (2, 1)} = (5 / 2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_2x1_2x1_2x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_2x1_2x1_2x1__1x1] <;> norm_num
  · rw [fp2_1x1_2x1_2x1_2x1__2x1] <;> norm_num
  · rw [fp2_1x1_2x1_2x1_2x1__2x1] <;> norm_num
  · rw [fp2_1x1_2x1_2x1_2x1__2x1] <;> norm_num

theorem fp2_1x1_2x1_2x1_3x1__3x1 : firstPatch 2 {(1, 1), (2, 1), (2, 1), (3, 1)} (3, 1) = (3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 0), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_2x0_2x1_2x1, v2_1x1_2x1_2x1_2x1] <;> norm_num

theorem v2_1x1_2x1_2x1_3x1 : val 2 {(1, 1), (2, 1), (2, 1), (3, 1)} = (5 / 2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_2x1_2x1_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_2x1_2x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_2x1_2x1_3x1__2x1] <;> norm_num
  · rw [fp2_1x1_2x1_2x1_3x1__2x1] <;> norm_num
  · rw [fp2_1x1_2x1_2x1_3x1__3x1] <;> norm_num

theorem fp3_1x1_2x1_2x1_3x2__1x1 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (3, 2)} (1, 1) = (11 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_2x1_2x1_3x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_3x2__2x1 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (3, 2)} (2, 1) = (23 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_2x1_3x2, v3_1x1_1x1_2x1_3x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_2x2__1x1 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (2, 2)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_2x1_2x1_2x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_2x2__2x1 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (2, 2)} (2, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_2x1_2x2, v3_1x1_1x1_2x1_2x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_2x2__2x2 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (2, 2)} (2, 2) = (3 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 2), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x1_2x1] <;> norm_num

theorem v3_1x1_2x1_2x1_2x2 : val 3 {(1, 1), (2, 1), (2, 1), (2, 2)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_2x1_2x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_2x1_2x1_2x2__1x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_2x2__2x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_3x2__3x2 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (3, 2)} (3, 2) = (11 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x1_2x1_2x1, v3_1x1_2x1_2x1_2x2] <;> norm_num

theorem v3_1x1_2x1_2x1_3x2 : val 3 {(1, 1), (2, 1), (2, 1), (3, 2)} = (11 / 3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_2x1_2x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_2x1_2x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_3x2__3x2] <;> norm_num

theorem fp3_1x1_2x1_2x1_4x2__4x2 : firstPatch 3 {(1, 1), (2, 1), (2, 1), (4, 2)} (4, 2) = (49 / 12 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x1_2x1_3x1, v3_1x1_2x1_2x1_3x2] <;> norm_num

theorem v3_1x1_2x1_2x1_4x2 : val 3 {(1, 1), (2, 1), (2, 1), (4, 2)} = (4 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_2x1_2x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_2x1_2x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x1_4x2__4x2] <;> norm_num

theorem fp3_2x1_2x1_2x1_4x2__2x1 : firstPatch 3 {(2, 1), (2, 1), (2, 1), (4, 2)} (2, 1) = (9 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (2, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (2, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_2x1_2x1_4x2, v3_1x1_2x1_2x1_4x2] <;> norm_num

theorem fp2_2x1_2x1_2x1_3x1__2x1 : firstPatch 2 {(2, 1), (2, 1), (2, 1), (3, 1)} (2, 1) = (3 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (2, 1), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_2x1_2x1_3x1, v2_1x1_2x1_2x1_3x1] <;> norm_num

theorem v1_2x0_2x1_2x1_2x1 : val 1 {(2, 0), (2, 1), (2, 1), (2, 1)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(2, 0), (2, 1), (2, 1), (2, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_2x1_2x1_2x1_2x1__2x1 : firstPatch 2 {(2, 1), (2, 1), (2, 1), (2, 1)} (2, 1) = (3 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (2, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (2, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_2x1_2x1_2x1, v2_1x1_2x1_2x1_2x1] <;> norm_num

theorem v2_2x1_2x1_2x1_2x1 : val 2 {(2, 1), (2, 1), (2, 1), (2, 1)} = (3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 1) (by decide) (by decide) fp2_2x1_2x1_2x1_2x1__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_2x1_2x1_2x1_2x1__2x1] <;> norm_num
  · rw [fp2_2x1_2x1_2x1_2x1__2x1] <;> norm_num
  · rw [fp2_2x1_2x1_2x1_2x1__2x1] <;> norm_num
  · rw [fp2_2x1_2x1_2x1_2x1__2x1] <;> norm_num

theorem fp2_2x1_2x1_2x1_3x1__3x1 : firstPatch 2 {(2, 1), (2, 1), (2, 1), (3, 1)} (3, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(2, 0), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(2, 1), (2, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_2x0_2x1_2x1_2x1, v2_2x1_2x1_2x1_2x1] <;> norm_num

theorem v2_2x1_2x1_2x1_3x1 : val 2 {(2, 1), (2, 1), (2, 1), (3, 1)} = (3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 1) (by decide) (by decide) fp2_2x1_2x1_2x1_3x1__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_2x1_2x1_2x1_3x1__2x1] <;> norm_num
  · rw [fp2_2x1_2x1_2x1_3x1__2x1] <;> norm_num
  · rw [fp2_2x1_2x1_2x1_3x1__2x1] <;> norm_num
  · rw [fp2_2x1_2x1_2x1_3x1__3x1] <;> norm_num

theorem fp3_2x1_2x1_2x1_3x2__2x1 : firstPatch 3 {(2, 1), (2, 1), (2, 1), (3, 2)} (2, 1) = (25 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (2, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_2x1_2x1_3x2, v3_1x1_2x1_2x1_3x2] <;> norm_num

theorem fp3_2x1_2x1_2x1_2x2__2x1 : firstPatch 3 {(2, 1), (2, 1), (2, 1), (2, 2)} (2, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (2, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(2, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_2x1_2x1_2x2, v3_1x1_2x1_2x1_2x2] <;> norm_num

theorem fp3_2x1_2x1_2x1_2x2__2x2 : firstPatch 3 {(2, 1), (2, 1), (2, 1), (2, 2)} (2, 2) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(2, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(2, 1), (2, 1), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 2), (2, 1), (2, 1), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x1_2x1_2x1] <;> norm_num

theorem v3_2x1_2x1_2x1_2x2 : val 3 {(2, 1), (2, 1), (2, 1), (2, 2)} = (7 / 2 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (2, 1) (by decide) (by decide) fp3_2x1_2x1_2x1_2x2__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_2x1_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_2x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_2x2__2x2] <;> norm_num

theorem fp3_2x1_2x1_2x1_3x2__3x2 : firstPatch 3 {(2, 1), (2, 1), (2, 1), (3, 2)} (3, 2) = (25 / 6 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(2, 1), (2, 1), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(2, 1), (2, 1), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(2, 1), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_2x1_2x1_2x1_2x1, v3_2x1_2x1_2x1_2x2] <;> norm_num

theorem v3_2x1_2x1_2x1_3x2 : val 3 {(2, 1), (2, 1), (2, 1), (3, 2)} = (25 / 6 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (2, 1) (by decide) (by decide) fp3_2x1_2x1_2x1_3x2__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_2x1_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_3x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_3x2__3x2] <;> norm_num

theorem fp3_2x1_2x1_2x1_4x2__4x2 : firstPatch 3 {(2, 1), (2, 1), (2, 1), (4, 2)} (4, 2) = (55 / 12 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(2, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(2, 1), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(2, 1), (2, 1), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(2, 1), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_2x1_2x1_2x1_3x1, v3_2x1_2x1_2x1_3x2] <;> norm_num

theorem v3_2x1_2x1_2x1_4x2 : val 3 {(2, 1), (2, 1), (2, 1), (4, 2)} = (9 / 2 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (2, 1) (by decide) (by decide) fp3_2x1_2x1_2x1_4x2__2x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_2x1_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_4x2__2x1] <;> norm_num
  · rw [fp3_2x1_2x1_2x1_4x2__4x2] <;> norm_num

theorem v1_0x0_1x0_3x1_4x2 : val 1 {(0, 0), (1, 0), (3, 1), (4, 2)} = (5 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (3, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (4, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (4, 2) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_3x1_4x2 : val 1 {(0, 0), (0, 0), (3, 1), (4, 2)} = (5 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (3, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (4, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (4, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_3x1_4x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (3, 1), (4, 2)} (1, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (3, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_3x1_4x2] <;> norm_num

theorem v1_0x0_1x1_2x0_4x2 : val 1 {(0, 0), (1, 1), (2, 0), (4, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (2, 0), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_3x1_4x2__3x1 : firstPatch 2 {(0, 0), (1, 1), (3, 1), (4, 2)} (3, 1) = (3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (1, 1), (2, 0), (4, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x0_4x2, v2_0x0_1x1_2x1_4x2] <;> norm_num

theorem v1_0x0_1x1_3x1_3x1 : val 1 {(0, 0), (1, 1), (3, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (3, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_0x0_3x1_3x2 : val 1 {(0, 0), (0, 0), (3, 1), (3, 2)} = (4 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (3, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (3, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (3, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_3x1_3x2__1x1 : firstPatch 2 {(0, 0), (1, 1), (3, 1), (3, 2)} (1, 1) = (7 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (3, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_3x1_3x2] <;> norm_num

theorem v1_0x0_1x1_2x0_3x2 : val 1 {(0, 0), (1, 1), (2, 0), (3, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (2, 0), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_3x1_3x2__3x1 : firstPatch 2 {(0, 0), (1, 1), (3, 1), (3, 2)} (3, 1) = (26 / 9 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (1, 1), (2, 0), (3, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(0, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x0_3x2, v2_0x0_1x1_2x1_3x2] <;> norm_num

theorem v1_0x0_0x0_2x2_3x1 : val 1 {(0, 0), (0, 0), (2, 2), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (0, 0), (2, 2), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x2_3x1__1x1 : firstPatch 2 {(0, 0), (1, 1), (2, 2), (3, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 0), (2, 2), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(0, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (0, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_0x0_2x2_3x1] <;> norm_num

theorem fp2_0x0_1x1_2x2_3x1__2x2 : firstPatch 2 {(0, 0), (1, 1), (2, 2), (3, 1)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(0, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(0, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (1, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_1x1_3x1] <;> norm_num

theorem v1_0x0_1x1_2x0_2x2 : val 1 {(0, 0), (1, 1), (2, 0), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 1), (2, 0), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_1x1_2x2_3x1__3x1 : firstPatch 2 {(0, 0), (1, 1), (2, 2), (3, 1)} (3, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(0, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(0, 0), (1, 1), (2, 0), (2, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(0, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(0, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x0_2x2, v2_0x0_1x1_2x1_2x2] <;> norm_num

theorem v2_0x0_1x1_2x2_3x1 : val 2 {(0, 0), (1, 1), (2, 2), (3, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_2x2_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_2x2_3x1__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_2x2_3x1__2x2] <;> norm_num
  · rw [fp2_0x0_1x1_2x2_3x1__3x1] <;> norm_num

theorem fp2_0x0_1x1_3x1_3x2__3x2 : firstPatch 2 {(0, 0), (1, 1), (3, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(0, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(0, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_3x1, v2_0x0_1x1_2x2_3x1] <;> norm_num

theorem v2_0x0_1x1_3x1_3x2 : val 2 {(0, 0), (1, 1), (3, 1), (3, 2)} = (7 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_3x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_3x1_3x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_3x1_3x2__3x1] <;> norm_num
  · rw [fp2_0x0_1x1_3x1_3x2__3x2] <;> norm_num

theorem fp2_0x0_1x1_3x1_4x2__4x2 : firstPatch 2 {(0, 0), (1, 1), (3, 1), (4, 2)} (4, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(0, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (1, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(0, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_3x1_3x1, v2_0x0_1x1_3x1_3x2] <;> norm_num

theorem v2_0x0_1x1_3x1_4x2 : val 2 {(0, 0), (1, 1), (3, 1), (4, 2)} = (8 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_0x0_1x1_3x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_1x1_3x1_4x2__1x1] <;> norm_num
  · rw [fp2_0x0_1x1_3x1_4x2__3x1] <;> norm_num
  · rw [fp2_0x0_1x1_3x1_4x2__4x2] <;> norm_num

theorem fp2_0x0_2x1_3x1_4x2__2x1 : firstPatch 2 {(0, 0), (2, 1), (3, 1), (4, 2)} (2, 1) = (19 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (3, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_3x1_4x2, v2_0x0_1x1_3x1_4x2] <;> norm_num

theorem v1_0x0_2x0_2x1_4x2 : val 1 {(0, 0), (2, 0), (2, 1), (4, 2)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (2, 0), (2, 1), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_3x1_4x2__3x1 : firstPatch 2 {(0, 0), (2, 1), (3, 1), (4, 2)} (3, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (2, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (2, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x0_2x1_4x2, v2_0x0_2x1_2x1_4x2] <;> norm_num

theorem v1_0x0_2x1_3x1_3x1 : val 1 {(0, 0), (2, 1), (3, 1), (3, 1)} = (3 / 2 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (2, 1), (3, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 1) (by decide) (by decide) hmin] <;> norm_num

theorem v1_0x0_1x0_3x1_3x2 : val 1 {(0, 0), (1, 0), (3, 1), (3, 2)} = (4 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (3, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (3, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (3, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_3x1_3x2__2x1 : firstPatch 2 {(0, 0), (2, 1), (3, 1), (3, 2)} (2, 1) = (17 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (3, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_3x1_3x2, v2_0x0_1x1_3x1_3x2] <;> norm_num

theorem v1_0x0_2x0_2x1_3x2 : val 1 {(0, 0), (2, 0), (2, 1), (3, 2)} = (4 / 3 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (2, 0), (2, 1), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (3, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (3, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_3x1_3x2__3x1 : firstPatch 2 {(0, 0), (2, 1), (3, 1), (3, 2)} (3, 1) = (29 / 9 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (2, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(0, 0), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(0, 0), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x0_2x1_3x2, v2_0x0_2x1_2x1_3x2] <;> norm_num

theorem v1_0x0_1x0_2x2_3x1 : val 1 {(0, 0), (1, 0), (2, 2), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (1, 0), (2, 2), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_2x2_3x1__2x1 : firstPatch 2 {(0, 0), (2, 1), (2, 2), (3, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 0), (2, 2), (3, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(0, 0), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 1) = {(0, 0), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x2_3x1, v2_0x0_1x1_2x2_3x1] <;> norm_num

theorem fp2_0x0_2x1_2x2_3x1__2x2 : firstPatch 2 {(0, 0), (2, 1), (2, 2), (3, 1)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(0, 0), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(0, 0), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(0, 0), (1, 2), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x1_3x1] <;> norm_num

theorem v1_0x0_2x0_2x1_2x2 : val 1 {(0, 0), (2, 0), (2, 1), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(0, 0), (2, 0), (2, 1), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (2, 2) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (2, 2) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_0x0_2x1_2x2_3x1__3x1 : firstPatch 2 {(0, 0), (2, 1), (2, 2), (3, 1)} (3, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(0, 0), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(0, 0), (2, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(0, 0), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(0, 0), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x0_2x1_2x2, v2_0x0_2x1_2x1_2x2] <;> norm_num

theorem v2_0x0_2x1_2x2_3x1 : val 2 {(0, 0), (2, 1), (2, 2), (3, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (2, 2) (by decide) (by decide) fp2_0x0_2x1_2x2_3x1__2x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_2x1_2x2_3x1__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_2x2_3x1__2x2] <;> norm_num
  · rw [fp2_0x0_2x1_2x2_3x1__3x1] <;> norm_num

theorem fp2_0x0_2x1_3x1_3x2__3x2 : firstPatch 2 {(0, 0), (2, 1), (3, 1), (3, 2)} (3, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(0, 0), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(0, 0), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(0, 0), (2, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_2x1_3x1, v2_0x0_2x1_2x2_3x1] <;> norm_num

theorem v2_0x0_2x1_3x1_3x2 : val 2 {(0, 0), (2, 1), (3, 1), (3, 2)} = (8 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (3, 2) (by decide) (by decide) fp2_0x0_2x1_3x1_3x2__3x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_2x1_3x1_3x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_3x1_3x2__3x1] <;> norm_num
  · rw [fp2_0x0_2x1_3x1_3x2__3x2] <;> norm_num

theorem fp2_0x0_2x1_3x1_4x2__4x2 : firstPatch 2 {(0, 0), (2, 1), (3, 1), (4, 2)} (4, 2) = (37 / 12 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(0, 0), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (2, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(0, 0), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(0, 0), (2, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_3x1_3x1, v2_0x0_2x1_3x1_3x2] <;> norm_num

theorem v2_0x0_2x1_3x1_4x2 : val 2 {(0, 0), (2, 1), (3, 1), (4, 2)} = (37 / 12 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (4, 2) (by decide) (by decide) fp2_0x0_2x1_3x1_4x2__4x2
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · exact absurd hpos (by norm_num)
  · rw [fp2_0x0_2x1_3x1_4x2__2x1] <;> norm_num
  · rw [fp2_0x0_2x1_3x1_4x2__3x1] <;> norm_num
  · rw [fp2_0x0_2x1_3x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_2x1_3x1_4x2__1x1 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (1, 1) = (49 / 12 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (3, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_2x1_3x1_4x2] <;> norm_num

theorem fp2_1x0_1x1_3x1_4x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (4, 2)} (1, 0) = (11 / 3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (3, 1), (4, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_3x1_4x2] <;> norm_num

theorem fp2_1x0_1x1_3x1_4x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (4, 2)} (1, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (3, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_3x1_4x2] <;> norm_num

theorem v1_1x0_1x1_2x0_4x2 : val 1 {(1, 0), (1, 1), (2, 0), (4, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (2, 0), (4, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_3x1_4x2__3x1 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (4, 2)} (3, 1) = (3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(1, 0), (1, 1), (2, 0), (4, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(1, 0), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x0_4x2, v2_1x0_1x1_2x1_4x2] <;> norm_num

theorem v1_1x0_1x1_3x1_3x1 : val 1 {(1, 0), (1, 1), (3, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (3, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_3x1_3x2__1x0 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (3, 2)} (1, 0) = (10 / 3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (3, 1), (3, 2)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_3x1_3x2] <;> norm_num

theorem fp2_1x0_1x1_3x1_3x2__1x1 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (3, 2)} (1, 1) = (7 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (3, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_3x1_3x2] <;> norm_num

theorem v1_1x0_1x1_2x0_3x2 : val 1 {(1, 0), (1, 1), (2, 0), (3, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (2, 0), (3, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_3x1_3x2__3x1 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (3, 2)} (3, 1) = (26 / 9 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(1, 0), (1, 1), (2, 0), (3, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(1, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x0_3x2, v2_1x0_1x1_2x1_3x2] <;> norm_num

theorem fp2_1x0_1x1_2x2_3x1__1x0 : firstPatch 2 {(1, 0), (1, 1), (2, 2), (3, 1)} (1, 0) = (3 : ℚ) := by
  have e1 : hitC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 2), (3, 1)} := by decide
  have e2 : missC (1, 0) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 0) = {(0, 0), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_0x0_1x1_2x2_3x1] <;> norm_num

theorem fp2_1x0_1x1_2x2_3x1__1x1 : firstPatch 2 {(1, 0), (1, 1), (2, 2), (3, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 0), (2, 2), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 0), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x0_2x2_3x1] <;> norm_num

theorem fp2_1x0_1x1_2x2_3x1__2x2 : firstPatch 2 {(1, 0), (1, 1), (2, 2), (3, 1)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(1, 0), (1, 1), (1, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_1x1_3x1] <;> norm_num

theorem v1_1x0_1x1_2x0_2x2 : val 1 {(1, 0), (1, 1), (2, 0), (2, 2)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 0), (1, 1), (2, 0), (2, 2)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x0_1x1_2x2_3x1__3x1 : firstPatch 2 {(1, 0), (1, 1), (2, 2), (3, 1)} (3, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 0), (1, 1), (2, 0), (2, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 0), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x0_2x2, v2_1x0_1x1_2x1_2x2] <;> norm_num

theorem v2_1x0_1x1_2x2_3x1 : val 2 {(1, 0), (1, 1), (2, 2), (3, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_2x2_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_2x2_3x1__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_2x2_3x1__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_2x2_3x1__2x2] <;> norm_num
  · rw [fp2_1x0_1x1_2x2_3x1__3x1] <;> norm_num

theorem fp2_1x0_1x1_3x1_3x2__3x2 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 0), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 0), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x1_3x1, v2_1x0_1x1_2x2_3x1] <;> norm_num

theorem v2_1x0_1x1_3x1_3x2 : val 2 {(1, 0), (1, 1), (3, 1), (3, 2)} = (7 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_3x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_3x1_3x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_3x1_3x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_3x1_3x2__3x1] <;> norm_num
  · rw [fp2_1x0_1x1_3x1_3x2__3x2] <;> norm_num

theorem fp2_1x0_1x1_3x1_4x2__4x2 : firstPatch 2 {(1, 0), (1, 1), (3, 1), (4, 2)} (4, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (1, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 0), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 0), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_3x1_3x1, v2_1x0_1x1_3x1_3x2] <;> norm_num

theorem v2_1x0_1x1_3x1_4x2 : val 2 {(1, 0), (1, 1), (3, 1), (4, 2)} = (8 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x0_1x1_3x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x0_1x1_3x1_4x2__1x0] <;> norm_num
  · rw [fp2_1x0_1x1_3x1_4x2__1x1] <;> norm_num
  · rw [fp2_1x0_1x1_3x1_4x2__3x1] <;> norm_num
  · rw [fp2_1x0_1x1_3x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_1x1_3x1_4x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (3, 1), (4, 2)} (1, 1) = (11 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (3, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_3x1_4x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_4x2__1x1 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (4, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 0), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 0), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 0), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 0), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x0_4x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_4x2__2x0 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (4, 2)} (2, 0) = (3 : ℚ) := by
  have e1 : hitC (2, 0) ::ₘ ({(1, 1), (1, 1), (2, 0), (4, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (1, 1), (4, 2)} := by decide
  have e2 : missC (2, 0) ::ₘ ({(1, 1), (1, 1), (2, 0), (4, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (1, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_1x0_1x1_1x1_4x2] <;> norm_num

theorem v1_1x1_1x1_2x0_3x1 : val 1 {(1, 1), (1, 1), (2, 0), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 1), (1, 1), (2, 0), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x1_1x1_2x0_3x2__1x1 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (3, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 0), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 0), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 0), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 0), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x0_3x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_3x2__2x0 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (3, 2)} (2, 0) = (3 : ℚ) := by
  have e1 : hitC (2, 0) ::ₘ ({(1, 1), (1, 1), (2, 0), (3, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (1, 1), (3, 2)} := by decide
  have e2 : missC (2, 0) ::ₘ ({(1, 1), (1, 1), (2, 0), (3, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (1, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_1x0_1x1_1x1_3x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_2x2__1x1 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (2, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 0), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 0), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 0), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 0), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_2x0_2x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_2x2__2x0 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (2, 2)} (2, 0) = (3 : ℚ) := by
  have e1 : hitC (2, 0) ::ₘ ({(1, 1), (1, 1), (2, 0), (2, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (1, 1), (2, 2)} := by decide
  have e2 : missC (2, 0) ::ₘ ({(1, 1), (1, 1), (2, 0), (2, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (1, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_1x0_1x1_1x1_2x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_2x2__2x2 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (1, 1), (2, 0), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 1), (2, 0)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (1, 1), (2, 0), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 2), (2, 0)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_1x1_2x0] <;> norm_num

theorem v2_1x1_1x1_2x0_2x2 : val 2 {(1, 1), (1, 1), (2, 0), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_2x0_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_2x0_2x2__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_2x2__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_2x2__2x0] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_2x2__2x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_3x2__3x2 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (1, 1), (2, 0), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (2, 0), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (1, 1), (2, 0), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (2, 0), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_2x0_2x1, v2_1x1_1x1_2x0_2x2] <;> norm_num

theorem v2_1x1_1x1_2x0_3x2 : val 2 {(1, 1), (1, 1), (2, 0), (3, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_2x0_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_2x0_3x2__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_3x2__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_3x2__2x0] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_3x2__3x2] <;> norm_num

theorem fp2_1x1_1x1_2x0_4x2__4x2 : firstPatch 2 {(1, 1), (1, 1), (2, 0), (4, 2)} (4, 2) = (5 / 2 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (1, 1), (2, 0), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (2, 0), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (1, 1), (2, 0), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (2, 0), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_2x0_3x1, v2_1x1_1x1_2x0_3x2] <;> norm_num

theorem v2_1x1_1x1_2x0_4x2 : val 2 {(1, 1), (1, 1), (2, 0), (4, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_2x0_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_2x0_4x2__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_4x2__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_4x2__2x0] <;> norm_num
  · rw [fp2_1x1_1x1_2x0_4x2__4x2] <;> norm_num

theorem fp3_1x1_1x1_3x1_4x2__3x1 : firstPatch 3 {(1, 1), (1, 1), (3, 1), (4, 2)} (3, 1) = (4 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 0), (4, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x0_4x2, v3_1x1_1x1_2x1_4x2] <;> norm_num

theorem fp2_1x1_1x1_3x1_3x1__1x1 : firstPatch 2 {(1, 1), (1, 1), (3, 1), (3, 1)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (3, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_1x1_3x1_3x1] <;> norm_num

theorem fp2_1x1_1x1_3x1_3x1__3x1 : firstPatch 2 {(1, 1), (1, 1), (3, 1), (3, 1)} (3, 1) = (8 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 0), (3, 1)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_2x0_3x1, v2_1x1_1x1_2x1_3x1] <;> norm_num

theorem v2_1x1_1x1_3x1_3x1 : val 2 {(1, 1), (1, 1), (3, 1), (3, 1)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_1x1_3x1_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_1x1_3x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_3x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_1x1_3x1_3x1__3x1] <;> norm_num
  · rw [fp2_1x1_1x1_3x1_3x1__3x1] <;> norm_num

theorem fp3_1x1_1x1_3x1_3x2__1x1 : firstPatch 3 {(1, 1), (1, 1), (3, 1), (3, 2)} (1, 1) = (10 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (3, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_3x1_3x2] <;> norm_num

theorem fp3_1x1_1x1_3x1_3x2__3x1 : firstPatch 3 {(1, 1), (1, 1), (3, 1), (3, 2)} (3, 1) = (35 / 9 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 0), (3, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x0_3x2, v3_1x1_1x1_2x1_3x2] <;> norm_num

theorem fp3_1x1_1x1_2x2_3x1__1x1 : firstPatch 3 {(1, 1), (1, 1), (2, 2), (3, 1)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (1, 1), (2, 2), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_1x1_2x2_3x1] <;> norm_num

theorem fp3_1x1_1x1_2x2_3x1__2x2 : firstPatch 3 {(1, 1), (1, 1), (2, 2), (3, 1)} (2, 2) = (3 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 1), (3, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (1, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_1x1_3x1] <;> norm_num

theorem fp3_1x1_1x1_2x2_3x1__3x1 : firstPatch 3 {(1, 1), (1, 1), (2, 2), (3, 1)} (3, 1) = (11 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 0), (2, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (1, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x0_2x2, v3_1x1_1x1_2x1_2x2] <;> norm_num

theorem v3_1x1_1x1_2x2_3x1 : val 3 {(1, 1), (1, 1), (2, 2), (3, 1)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_2x2_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_2x2_3x1__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x2_3x1__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_2x2_3x1__2x2] <;> norm_num
  · rw [fp3_1x1_1x1_2x2_3x1__3x1] <;> norm_num

theorem fp3_1x1_1x1_3x1_3x2__3x2 : firstPatch 3 {(1, 1), (1, 1), (3, 1), (3, 2)} (3, 2) = (10 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (1, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x1_3x1, v3_1x1_1x1_2x2_3x1] <;> norm_num

theorem v3_1x1_1x1_3x1_3x2 : val 3 {(1, 1), (1, 1), (3, 1), (3, 2)} = (10 / 3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_3x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_3x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_3x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_3x1_3x2__3x1] <;> norm_num
  · rw [fp3_1x1_1x1_3x1_3x2__3x2] <;> norm_num

theorem fp3_1x1_1x1_3x1_4x2__4x2 : firstPatch 3 {(1, 1), (1, 1), (3, 1), (4, 2)} (4, 2) = (11 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (1, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_3x1_3x1, v3_1x1_1x1_3x1_3x2] <;> norm_num

theorem v3_1x1_1x1_3x1_4x2 : val 3 {(1, 1), (1, 1), (3, 1), (4, 2)} = (11 / 3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_1x1_3x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_1x1_3x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_3x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_1x1_3x1_4x2__3x1] <;> norm_num
  · rw [fp3_1x1_1x1_3x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_2x1_3x1_4x2__2x1 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (2, 1) = (25 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (3, 1), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (3, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_3x1_4x2, v3_1x1_1x1_3x1_4x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_4x2__1x1 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (4, 2)} (1, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 0), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x0_2x1_4x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_4x2__2x0 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (4, 2)} (2, 0) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 0) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (2, 1), (4, 2)} := by decide
  have e2 : missC (2, 0) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_1x0_1x1_2x1_4x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_4x2__2x1 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (4, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 0), (4, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 0), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x0_4x2, v2_1x1_1x1_2x0_4x2] <;> norm_num

theorem v1_1x1_2x0_2x1_3x1 : val 1 {(1, 1), (2, 0), (2, 1), (3, 1)} = (1 : ℚ) := by
  have hmin : ∀ d ∈ ({(1, 1), (2, 0), (2, 1), (3, 1)} : Multiset Cat), 1 ≤ d.2 → finisher (1, 1) ≤ finisher d := by
    intro d hd hd1
    simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
    rcases hd with rfl | rfl | rfl | rfl <;> (try norm_num at hd1) <;> (try norm_num)
  rw [val_one_eq _ (by decide) (1, 1) (by decide) (by decide) hmin] <;> norm_num

theorem fp2_1x1_2x0_2x1_3x2__1x1 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (3, 2)} (1, 1) = (7 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 0), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x0_2x1_3x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_3x2__2x0 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (3, 2)} (2, 0) = (10 / 3 : ℚ) := by
  have e1 : hitC (2, 0) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (2, 1), (3, 2)} := by decide
  have e2 : missC (2, 0) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_1x0_1x1_2x1_3x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_3x2__2x1 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (3, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 0), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 0), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x0_3x2, v2_1x1_1x1_2x0_3x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_2x2__1x1 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (2, 2)} (1, 1) = (2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 0), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x0_2x1_2x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_2x2__2x0 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (2, 2)} (2, 0) = (3 : ℚ) := by
  have e1 : hitC (2, 0) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (2, 1), (2, 2)} := by decide
  have e2 : missC (2, 0) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (2, 0) = {(1, 0), (1, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v2_1x0_1x1_2x1_2x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_2x2__2x1 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (2, 2)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 0), (2, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 0), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_2x0_2x2, v2_1x1_1x1_2x0_2x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_2x2__2x2 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (2, 2)} (2, 2) = (2 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (2, 0), (2, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (2, 0), (2, 1), (2, 2)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 2), (2, 0), (2, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_1x1_2x0_2x1] <;> norm_num

theorem v2_1x1_2x0_2x1_2x2 : val 2 {(1, 1), (2, 0), (2, 1), (2, 2)} = (2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_2x0_2x1_2x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_2x0_2x1_2x2__1x1] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_2x2__2x0] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_2x2__2x1] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_2x2__2x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_3x2__3x2 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (3, 2)} (3, 2) = (7 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (2, 0), (2, 1), (2, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (2, 0), (2, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (2, 0), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_2x0_2x1_2x1, v2_1x1_2x0_2x1_2x2] <;> norm_num

theorem v2_1x1_2x0_2x1_3x2 : val 2 {(1, 1), (2, 0), (2, 1), (3, 2)} = (7 / 3 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_2x0_2x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_2x0_2x1_3x2__1x1] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_3x2__2x0] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_3x2__2x1] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_3x2__3x2] <;> norm_num

theorem fp2_1x1_2x0_2x1_4x2__4x2 : firstPatch 2 {(1, 1), (2, 0), (2, 1), (4, 2)} (4, 2) = (8 / 3 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (2, 0), (2, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (2, 0), (2, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (2, 0), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_2x0_2x1_3x1, v2_1x1_2x0_2x1_3x2] <;> norm_num

theorem v2_1x1_2x0_2x1_4x2 : val 2 {(1, 1), (2, 0), (2, 1), (4, 2)} = (5 / 2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_2x0_2x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_2x0_2x1_4x2__1x1] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_4x2__2x0] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_4x2__2x1] <;> norm_num
  · rw [fp2_1x1_2x0_2x1_4x2__4x2] <;> norm_num

theorem fp3_1x1_2x1_3x1_4x2__3x1 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (3, 1) = (9 / 2 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 0), (2, 1), (4, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 1), (2, 1), (4, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x0_2x1_4x2, v3_1x1_2x1_2x1_4x2] <;> norm_num

theorem fp2_1x1_2x1_3x1_3x1__1x1 : firstPatch 2 {(1, 1), (2, 1), (3, 1), (3, 1)} (1, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (3, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_0x0_2x1_3x1_3x1] <;> norm_num

theorem fp2_1x1_2x1_3x1_3x1__2x1 : firstPatch 2 {(1, 1), (2, 1), (3, 1), (3, 1)} (2, 1) = (5 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (3, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x0_1x1_3x1_3x1, v2_1x1_1x1_3x1_3x1] <;> norm_num

theorem fp2_1x1_2x1_3x1_3x1__3x1 : firstPatch 2 {(1, 1), (2, 1), (3, 1), (3, 1)} (3, 1) = (3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 0), (2, 1), (3, 1)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 1), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (2 : ℕ) - 1 = 1 from rfl, v1_1x1_2x0_2x1_3x1, v2_1x1_2x1_2x1_3x1] <;> norm_num

theorem v2_1x1_2x1_3x1_3x1 : val 2 {(1, 1), (2, 1), (3, 1), (3, 1)} = (5 / 2 : ℚ) := by
  apply val_eq_of_cert 1 _ _ (1, 1) (by decide) (by decide) fp2_1x1_2x1_3x1_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp2_1x1_2x1_3x1_3x1__1x1] <;> norm_num
  · rw [fp2_1x1_2x1_3x1_3x1__2x1] <;> norm_num
  · rw [fp2_1x1_2x1_3x1_3x1__3x1] <;> norm_num
  · rw [fp2_1x1_2x1_3x1_3x1__3x1] <;> norm_num

theorem fp3_1x1_2x1_3x1_3x2__1x1 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (3, 2)} (1, 1) = (11 / 3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (3, 1), (3, 2)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_2x1_3x1_3x2] <;> norm_num

theorem fp3_1x1_2x1_3x1_3x2__2x1 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (3, 2)} (2, 1) = (23 / 6 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (3, 1), (3, 2)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_3x1_3x2, v3_1x1_1x1_3x1_3x2] <;> norm_num

theorem fp3_1x1_2x1_3x1_3x2__3x1 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (3, 2)} (3, 1) = (38 / 9 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 0), (2, 1), (3, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 1), (2, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x0_2x1_3x2, v3_1x1_2x1_2x1_3x2] <;> norm_num

theorem fp3_1x1_2x1_2x2_3x1__1x1 : firstPatch 3 {(1, 1), (2, 1), (2, 2), (3, 1)} (1, 1) = (3 : ℚ) := by
  have e1 : hitC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 0), (2, 1), (2, 2), (3, 1)} := by decide
  have e2 : missC (1, 1) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (1, 1) = {(0, 1), (2, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_0x0_2x1_2x2_3x1] <;> norm_num

theorem fp3_1x1_2x1_2x2_3x1__2x1 : firstPatch 3 {(1, 1), (2, 1), (2, 2), (3, 1)} (2, 1) = (7 / 2 : ℚ) := by
  have e1 : hitC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 0), (1, 1), (2, 2), (3, 1)} := by decide
  have e2 : missC (2, 1) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 1) = {(1, 1), (1, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x0_1x1_2x2_3x1, v3_1x1_1x1_2x2_3x1] <;> norm_num

theorem fp3_1x1_2x1_2x2_3x1__2x2 : firstPatch 3 {(1, 1), (2, 1), (2, 2), (3, 1)} (2, 2) = (3 : ℚ) := by
  have e1 : hitC (2, 2) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (2, 2) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (2, 2) = {(1, 1), (1, 2), (2, 1), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_1x1_2x1_3x1] <;> norm_num

theorem fp3_1x1_2x1_2x2_3x1__3x1 : firstPatch 3 {(1, 1), (2, 1), (2, 2), (3, 1)} (3, 1) = (11 / 3 : ℚ) := by
  have e1 : hitC (3, 1) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 0), (2, 1), (2, 2)} := by decide
  have e2 : missC (3, 1) ::ₘ ({(1, 1), (2, 1), (2, 2), (3, 1)} : Multiset Cat).erase (3, 1) = {(1, 1), (2, 1), (2, 1), (2, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x0_2x1_2x2, v3_1x1_2x1_2x1_2x2] <;> norm_num

theorem v3_1x1_2x1_2x2_3x1 : val 3 {(1, 1), (2, 1), (2, 2), (3, 1)} = (3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_2x1_2x2_3x1__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_2x1_2x2_3x1__1x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x2_3x1__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_2x2_3x1__2x2] <;> norm_num
  · rw [fp3_1x1_2x1_2x2_3x1__3x1] <;> norm_num

theorem fp3_1x1_2x1_3x1_3x2__3x2 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (3, 2)} (3, 2) = (11 / 3 : ℚ) := by
  have e1 : hitC (3, 2) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (2, 1), (2, 1), (3, 1)} := by decide
  have e2 : missC (3, 2) ::ₘ ({(1, 1), (2, 1), (3, 1), (3, 2)} : Multiset Cat).erase (3, 2) = {(1, 1), (2, 1), (2, 2), (3, 1)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x1_2x1_3x1, v3_1x1_2x1_2x2_3x1] <;> norm_num

theorem v3_1x1_2x1_3x1_3x2 : val 3 {(1, 1), (2, 1), (3, 1), (3, 2)} = (11 / 3 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_2x1_3x1_3x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_2x1_3x1_3x2__1x1] <;> norm_num
  · rw [fp3_1x1_2x1_3x1_3x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_3x1_3x2__3x1] <;> norm_num
  · rw [fp3_1x1_2x1_3x1_3x2__3x2] <;> norm_num

theorem fp3_1x1_2x1_3x1_4x2__4x2 : firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (4, 2) = (49 / 12 : ℚ) := by
  have e1 : hitC (4, 2) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (2, 1), (3, 1), (3, 1)} := by decide
  have e2 : missC (4, 2) ::ₘ ({(1, 1), (2, 1), (3, 1), (4, 2)} : Multiset Cat).erase (4, 2) = {(1, 1), (2, 1), (3, 1), (3, 2)} := by decide
  rw [firstPatch, e1, e2, show (3 : ℕ) - 1 = 2 from rfl, v2_1x1_2x1_3x1_3x1, v3_1x1_2x1_3x1_3x2] <;> norm_num

theorem v3_1x1_2x1_3x1_4x2 : val 3 {(1, 1), (2, 1), (3, 1), (4, 2)} = (49 / 12 : ℚ) := by
  apply val_eq_of_cert 2 _ _ (1, 1) (by decide) (by decide) fp3_1x1_2x1_3x1_4x2__1x1
  intro d hd hpos
  simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
  rcases hd with rfl | rfl | rfl | rfl
  · rw [fp3_1x1_2x1_3x1_4x2__1x1] <;> norm_num
  · rw [fp3_1x1_2x1_3x1_4x2__2x1] <;> norm_num
  · rw [fp3_1x1_2x1_3x1_4x2__3x1] <;> norm_num
  · rw [fp3_1x1_2x1_3x1_4x2__4x2] <;> norm_num

/-- **Proposition 7, the note's second witness, values.** With three hits needed, ten items, five
failures and four categories, patching `(2,1)` first is strictly better than `(4,2)` first in
`{(2,1),(2,1),(2,1),(4,2)}` (`9/2` against `55/12`) and strictly worse in
`{(1,1),(2,1),(3,1),(4,2)}` (`25/6` against `49/12`). In the second state `(1,1)` ties `(4,2)` at
the optimum `49/12`, so, as with the first witness, a rule ranking `(1,1)` on top is not defeated
by this pair; `PatchWitness.prop7_with_context` gives a pair that is. -/
theorem prop7_note_context_values :
    items {(2, 1), (2, 1), (2, 1), (4, 2)} = 10 ∧ items {(1, 1), (2, 1), (3, 1), (4, 2)} = 10 ∧
    fails {(2, 1), (2, 1), (2, 1), (4, 2)} = 5 ∧ fails {(1, 1), (2, 1), (3, 1), (4, 2)} = 5 ∧
    firstPatch 3 {(2, 1), (2, 1), (2, 1), (4, 2)} (2, 1) = 9 / 2 ∧
    firstPatch 3 {(2, 1), (2, 1), (2, 1), (4, 2)} (4, 2) = 55 / 12 ∧
    firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (2, 1) = 25 / 6 ∧
    firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (4, 2) = 49 / 12 ∧
    firstPatch 3 {(1, 1), (2, 1), (3, 1), (4, 2)} (1, 1) = 49 / 12 ∧
    val 3 {(1, 1), (2, 1), (3, 1), (4, 2)} = 49 / 12 :=
  ⟨by decide, by decide, by decide, by decide, fp3_2x1_2x1_2x1_4x2__2x1, fp3_2x1_2x1_2x1_4x2__4x2,
    fp3_1x1_2x1_3x1_4x2__2x1, fp3_1x1_2x1_3x1_4x2__4x2, fp3_1x1_2x1_3x1_4x2__1x1,
    v3_1x1_2x1_3x1_4x2⟩

end FeedbackChannel.PatchWitness3

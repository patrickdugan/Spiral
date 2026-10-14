import Mathlib.Tactic

/-!
# Mixed gain laws: the window-sum recursion and the distance-two closure (multigen note §6, 0.5)

Source: `paper/evaluation_feedback_multigen.md`, draft 0.5, §6 "Mixed gain laws (0.5)"; code
`src/spiral_ln/evaluation_feedback_multigen.py` (`drift_kernel`, `mixed_window_sums`,
`mixed_count_structure`).

**The chain.** States `x = (c, i)`: incumbent count `c ∈ {0, …, n}` and level `i`. From level `i` the
best of the generation's `K` candidates has count `J` and, if accepted, moves the level to `ℓ`
(`ℓ = min(top, i + μ)` for the accepted candidate's gain multiple `μ`, which may be `0`); the joint
law of `(J, ℓ)` is `ρ i J ℓ` (`drift_kernel` writes it as `q_μ Bin(n, p(i+μ))(J) S_J`). A rule with
cap `a(c)` accepts iff `J > a(c)` and then moves to `(J, ℓ)`; the naive rule has `a(c) = c`, a
threshold rule `a(c) = c + t(c)`. This file works with an arbitrary finite joint law `ρ` (one per
level, total mass one); the note's hypotheses enter as `gain_nonneg` (`ρ i J ℓ ≠ 0 → i ≤ ℓ`) and the
monotonicity of `H` in the level ("the best of `K` is stochastically non-decreasing in the level").

**Objects (note's notation).** Target `m`; `u_k = P^k 1{c ≥ m}` (naive kernel `P`); `s_k = 1 - u_k`;
`H(i)` the probability that a draw from level `i` has count `≥ m`; for `a < m` the window sums
`W^a_k(x) = ∑_{c < J ≤ a} ρ(y) [s_k(x) - s_k(y)]` (which equal `(P u_k - Q u_k)(x)` for the rule
with `a(c) = a`), `E^a_k(x) = ∑_{(c,a]} ρ(y) (H(i_y) - H(i)) s_k(y)`, `B_a = ∑_{(c,a]} ρ(y)`,
`A = P(stay)`.

**Formalized.**
* `window_recursion`: the exact recursion
  `W^a_k = (1 - H(i)) W^a_{k-1} + E^a_{k-1} + ∑_{y ∈ (c,a]} ρ(y) W^{m-1}_{k-1}(y) - B_a W^{m-1}_{k-1}(x)`.
* `E_nonneg`: `E^a ≥ 0`; `full_window_nonneg` / `L1`: the full-window slacks `W^{m-1} ≥ 0`, i.e.
  (L1) `s_{k+1}(x) ≤ (1 - H(i)) s_k(x)`, for every gain law (`full_window_nonneg_of_landing` is
  the same under the weaker hypothesis that every landing level has `H(ℓ) ≥ H(i)`).
* `distance_two_closure` and `distance_two_nonneg`: at `c = m - 2`,
  `W_k = A W_{k-1} + E_{k-1} ≥ 0`.
* `gated_le_naive_near_target`: hence one step of any threshold rule followed by naive steps is
  dominated, `(Q u_k)(x) ≤ (P u_k)(x)`, at every state with `c ≥ m - 2`.
-/

namespace FeedbackChannel.MultigenMixed

open Finset

/-- Sum over counts `J ∈ {0, …, n}` and landing levels `ℓ ∈ {0, …, L - 1}`. -/
def S2 (n L : ℕ) (g : ℕ → ℕ → ℝ) : ℝ := ∑ J ∈ range (n + 1), ∑ ℓ ∈ range L, g J ℓ

theorem S2_congr {n L : ℕ} {g h : ℕ → ℕ → ℝ} (H : ∀ J ℓ, g J ℓ = h J ℓ) : S2 n L g = S2 n L h :=
  Finset.sum_congr rfl fun J _ => Finset.sum_congr rfl fun ℓ _ => H J ℓ

theorem S2_add (n L : ℕ) (g h : ℕ → ℕ → ℝ) :
    S2 n L (fun J ℓ => g J ℓ + h J ℓ) = S2 n L g + S2 n L h := by
  unfold S2; simp_rw [Finset.sum_add_distrib]

theorem S2_sub (n L : ℕ) (g h : ℕ → ℕ → ℝ) :
    S2 n L (fun J ℓ => g J ℓ - h J ℓ) = S2 n L g - S2 n L h := by
  unfold S2; simp_rw [Finset.sum_sub_distrib]

theorem S2_mul_left (n L : ℕ) (r : ℝ) (g : ℕ → ℕ → ℝ) :
    S2 n L (fun J ℓ => r * g J ℓ) = r * S2 n L g := by
  unfold S2; simp_rw [← Finset.mul_sum]

theorem S2_mono {n L : ℕ} {g h : ℕ → ℕ → ℝ} (H : ∀ J ℓ, g J ℓ ≤ h J ℓ) : S2 n L g ≤ S2 n L h :=
  Finset.sum_le_sum fun J _ => Finset.sum_le_sum fun ℓ _ => H J ℓ

theorem S2_nonneg {n L : ℕ} {g : ℕ → ℕ → ℝ} (H : ∀ J ℓ, 0 ≤ g J ℓ) : 0 ≤ S2 n L g :=
  Finset.sum_nonneg fun J _ => Finset.sum_nonneg fun ℓ _ => H J ℓ

theorem S2_zero (n L : ℕ) : S2 n L (fun _ _ => 0) = 0 := by simp [S2]

theorem S2_eq_zero {n L : ℕ} {g : ℕ → ℕ → ℝ} (H : ∀ J ℓ, g J ℓ = 0) : S2 n L g = 0 :=
  (S2_congr H).trans (S2_zero n L)

/-- One generation's draw law: from level `i`, the best candidate has count `J` and its acceptance
would move the level to `ℓ`, with probability `ρ i J ℓ`. -/
structure DrawLaw (n L : ℕ) where
  ρ : ℕ → ℕ → ℕ → ℝ
  nonneg : ∀ i J ℓ, 0 ≤ ρ i J ℓ
  total : ∀ i, S2 n L (ρ i) = 1

variable {n L : ℕ} (D : DrawLaw n L)

/-- The one-generation operator of the rule with cap `cap` (accept iff `J > cap c`):
`(Q f)(c, i) = ∑ ρ i J ℓ · (f(c, i) if J ≤ cap c, else f(J, ℓ))`. The naive kernel is `cap = id`. -/
def kernel (cap : ℕ → ℕ) (f : ℕ × ℕ → ℝ) (x : ℕ × ℕ) : ℝ :=
  S2 n L fun J ℓ => D.ρ x.2 J ℓ * (if J ≤ cap x.1 then f x else f (J, ℓ))

/-- The hitting indicator `1{c ≥ m}`. -/
def hit (m : ℕ) (x : ℕ × ℕ) : ℝ := if m ≤ x.1 then 1 else 0

/-- `u_k = P^k 1{c ≥ m}` under the naive kernel `P`. -/
def u (m : ℕ) : ℕ → ℕ × ℕ → ℝ
  | 0 => hit m
  | k + 1 => kernel D id (u m k)

/-- `s_k = 1 - u_k`. -/
def s (m k : ℕ) (x : ℕ × ℕ) : ℝ := 1 - u D m k x

/-- `H(i)`: probability that a draw from level `i` has count `≥ m`. -/
def H (m i : ℕ) : ℝ := S2 n L fun J ℓ => if m ≤ J then D.ρ i J ℓ else 0

/-- `A(x)`: probability that the naive rule stays at `x`. -/
def A (x : ℕ × ℕ) : ℝ := S2 n L fun J ℓ => if J ≤ x.1 then D.ρ x.2 J ℓ else 0

/-- `B_a(x)`: mass of the landings with count in the window `(c, a]`. -/
def B (a : ℕ) (x : ℕ × ℕ) : ℝ := S2 n L fun J ℓ => if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ else 0

/-- The window sum `W^a_k(x) = ∑_{c < J ≤ a} ρ(y) [s_k(x) - s_k(y)]`. -/
def W (m a k : ℕ) (x : ℕ × ℕ) : ℝ :=
  S2 n L fun J ℓ => if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ * (s D m k x - s D m k (J, ℓ)) else 0

/-- `E^a_k(x) = ∑_{(c,a]} ρ(y) (H(i_y) - H(i)) s_k(y)`. -/
def E (m a k : ℕ) (x : ℕ × ℕ) : ℝ :=
  S2 n L fun J ℓ =>
    if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ * (H D m ℓ - H D m x.2) * s D m k (J, ℓ) else 0

/-- `∑_{y ∈ (c,a]} ρ(y) W^{m-1}_k(y)`: the landings' own full-window slacks. -/
def landingSlack (m a k : ℕ) (x : ℕ × ℕ) : ℝ :=
  S2 n L fun J ℓ => if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ * W D m (m - 1) k (J, ℓ) else 0

/-! ## Basic facts -/

theorem kernel_bounds (cap : ℕ → ℕ) (f : ℕ × ℕ → ℝ) (hf : ∀ y, 0 ≤ f y ∧ f y ≤ 1)
    (x : ℕ × ℕ) : 0 ≤ kernel D cap f x ∧ kernel D cap f x ≤ 1 := by
  constructor
  · apply S2_nonneg
    intro J ℓ
    apply mul_nonneg (D.nonneg _ _ _)
    split_ifs
    · exact (hf _).1
    · exact (hf _).1
  · rw [← D.total x.2]
    apply S2_mono
    intro J ℓ
    have := D.nonneg x.2 J ℓ
    split_ifs
    · nlinarith [(hf x).2]
    · nlinarith [(hf (J, ℓ)).2]

theorem u_bounds (m k : ℕ) (x : ℕ × ℕ) : 0 ≤ u D m k x ∧ u D m k x ≤ 1 := by
  induction k generalizing x with
  | zero => unfold u hit; split_ifs <;> norm_num
  | succ k ih => exact kernel_bounds D id _ ih x

theorem s_nonneg (m k : ℕ) (x : ℕ × ℕ) : 0 ≤ s D m k x := by
  unfold s; linarith [(u_bounds D m k x).2]

/-- Above the target the naive chain has already hit: `u_k = 1` on `c ≥ m`. -/
theorem u_top (m k : ℕ) (x : ℕ × ℕ) (hx : m ≤ x.1) : u D m k x = 1 := by
  induction k generalizing x with
  | zero => simp [u, hit, hx]
  | succ k ih =>
    show kernel D id (u D m k) x = 1
    rw [← D.total x.2]
    apply S2_congr
    intro J ℓ
    split_ifs with h
    · rw [ih x hx, mul_one]
    · rw [ih (J, ℓ) (by simp only [id] at h; simp only; omega), mul_one]

theorem s_top (m k : ℕ) (y : ℕ × ℕ) (hy : m ≤ y.1) : s D m k y = 0 := by
  unfold s; rw [u_top D m k y hy]; ring

theorem s_zero_below (m : ℕ) (x : ℕ × ℕ) (hx : x.1 < m) : s D m 0 x = 1 := by
  simp [s, u, hit, Nat.not_le.mpr hx]

theorem A_nonneg (x : ℕ × ℕ) : 0 ≤ A D x :=
  S2_nonneg fun J ℓ => by split_ifs <;> simp [D.nonneg]

/-- The three regions `J ≤ c`, `c < J ≤ m - 1`, `J ≥ m` partition the draws when `c < m`:
`A + B_{m-1} + H = 1`. -/
theorem partition (m : ℕ) (x : ℕ × ℕ) (hx : x.1 < m) :
    A D x + B D (m - 1) x + H D m x.2 = 1 := by
  rw [← D.total x.2]
  unfold A B H
  rw [← S2_add, ← S2_add]
  apply S2_congr
  intro J ℓ
  by_cases h1 : J ≤ x.1
  · rw [ite_eq_left h1, ite_eq_right (by omega), ite_eq_right (by omega)]; ring
  · by_cases h2 : J ≤ m - 1
    · rw [ite_eq_right h1, ite_eq_left ⟨by omega, h2⟩, ite_eq_right (by omega)]; ring
    · rw [ite_eq_right h1, ite_eq_right (by omega), ite_eq_left (by omega)]; ring

/-- The difference between the naive and a gated step is the window sum over `(c, cap c]`. -/
theorem kernel_sub (cap : ℕ → ℕ) (f : ℕ × ℕ → ℝ) (x : ℕ × ℕ) (hcap : x.1 ≤ cap x.1) :
    kernel D id f x - kernel D cap f x =
      S2 n L fun J ℓ => if x.1 < J ∧ J ≤ cap x.1 then D.ρ x.2 J ℓ * (f (J, ℓ) - f x) else 0 := by
  unfold kernel
  rw [← S2_sub]
  apply S2_congr
  intro J ℓ
  simp only [id]
  by_cases h1 : J ≤ x.1
  · rw [ite_eq_left h1, ite_eq_left (by omega), ite_eq_right (by omega)]; ring
  · by_cases h2 : J ≤ cap x.1
    · rw [ite_eq_right h1, ite_eq_left h2, ite_eq_left ⟨by omega, h2⟩]; ring
    · rw [ite_eq_right h1, ite_eq_right h2, ite_eq_right (by omega)]; ring

/-- For `f = u_k` the gated deficit is exactly the window sum `W^{cap c}_k(x)`. -/
theorem kernel_sub_u (cap : ℕ → ℕ) (m k : ℕ) (x : ℕ × ℕ) (hcap : x.1 ≤ cap x.1) :
    kernel D id (u D m k) x - kernel D cap (u D m k) x = W D m (cap x.1) k x := by
  rw [kernel_sub D cap _ x hcap]
  unfold W s
  apply S2_congr
  intro J ℓ
  split_ifs <;> ring

/-- One naive step of the survival function below the target:
`s_{k+1}(x) = (1 - H(i)) s_k(x) - W^{m-1}_k(x)` for `c < m`. -/
theorem s_succ (m k : ℕ) (x : ℕ × ℕ) (hx : x.1 < m) :
    s D m (k + 1) x = (1 - H D m x.2) * s D m k x - W D m (m - 1) k x := by
  have h1 : s D m (k + 1) x =
      S2 n L fun J ℓ => D.ρ x.2 J ℓ * (if J ≤ x.1 then s D m k x else s D m k (J, ℓ)) := by
    show 1 - kernel D id (u D m k) x = _
    unfold kernel
    rw [← D.total x.2, ← S2_sub]
    apply S2_congr
    intro J ℓ
    simp only [id, s]
    split_ifs <;> ring
  have h2 : ∀ J ℓ, D.ρ x.2 J ℓ * (if J ≤ x.1 then s D m k x else s D m k (J, ℓ)) =
      D.ρ x.2 J ℓ * s D m k x - (if m ≤ J then D.ρ x.2 J ℓ else 0) * s D m k x -
        (if x.1 < J ∧ J ≤ m - 1 then D.ρ x.2 J ℓ * (s D m k x - s D m k (J, ℓ)) else 0) := by
    intro J ℓ
    by_cases hJ1 : J ≤ x.1
    · rw [ite_eq_left hJ1, ite_eq_right (by omega), ite_eq_right (by omega)]; ring
    · by_cases hJ2 : m ≤ J
      · rw [ite_eq_right hJ1, ite_eq_left hJ2, ite_eq_right (by omega), s_top D m k (J, ℓ) hJ2]; ring
      · rw [ite_eq_right hJ1, ite_eq_right hJ2, ite_eq_left ⟨by omega, by omega⟩]; ring
  rw [h1, S2_congr h2, S2_sub, S2_sub]
  unfold H W
  rw [show (S2 n L fun J ℓ => D.ρ x.2 J ℓ * s D m k x) = S2 n L (D.ρ x.2) * s D m k x by
      unfold S2; simp_rw [Finset.sum_mul],
    show (S2 n L fun J ℓ => (if m ≤ J then D.ρ x.2 J ℓ else 0) * s D m k x) =
      (S2 n L fun J ℓ => if m ≤ J then D.ρ x.2 J ℓ else 0) * s D m k x by
      unfold S2; simp_rw [Finset.sum_mul],
    D.total x.2]
  ring

/-! ## The window-sum recursion -/

/-- **The window-sum recursion** (note §6, mixed gain laws, exact for `a < m`):
`W^a_{k+1}(x) = (1 - H(i)) W^a_k(x) + E^a_k(x) + ∑_{y ∈ (c,a]} ρ(y) W^{m-1}_k(y) - B_a W^{m-1}_k(x)`. -/
theorem window_recursion (m a k : ℕ) (ha : a < m) (x : ℕ × ℕ) :
    W D m a (k + 1) x = (1 - H D m x.2) * W D m a k x + E D m a k x + landingSlack D m a k x -
      B D a x * W D m (m - 1) k x := by
  have hterm : ∀ J ℓ,
      (if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ * (s D m (k + 1) x - s D m (k + 1) (J, ℓ)) else 0) =
        (1 - H D m x.2) *
            (if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ * (s D m k x - s D m k (J, ℓ)) else 0) +
          (if x.1 < J ∧ J ≤ a then
              D.ρ x.2 J ℓ * (H D m ℓ - H D m x.2) * s D m k (J, ℓ) else 0) +
          (if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ * W D m (m - 1) k (J, ℓ) else 0) -
          W D m (m - 1) k x * (if x.1 < J ∧ J ≤ a then D.ρ x.2 J ℓ else 0) := by
    intro J ℓ
    split_ifs with h
    · rw [s_succ D m k x (by omega), s_succ D m k (J, ℓ) (by simp only; omega)]
      ring
    · ring
  unfold W
  rw [S2_congr hterm, S2_sub, S2_add, S2_add, S2_mul_left, S2_mul_left]
  unfold E landingSlack B W
  ring

/-- `E^a ≥ 0`: landings never lower the level (`gain_nonneg`) and `H` is non-decreasing in the
level. -/
theorem E_nonneg (m a k : ℕ) (x : ℕ × ℕ)
    (gain_nonneg : ∀ i J ℓ, D.ρ i J ℓ ≠ 0 → i ≤ ℓ) (H_mono : Monotone (H D m)) :
    0 ≤ E D m a k x := by
  apply S2_nonneg
  intro J ℓ
  split_ifs
  · by_cases hρ : D.ρ x.2 J ℓ = 0
    · rw [hρ]; ring_nf; exact le_rfl
    · have hle := H_mono (gain_nonneg x.2 J ℓ hρ)
      apply mul_nonneg (mul_nonneg (D.nonneg _ _ _) (by linarith)) (s_nonneg D m k _)
  · exact le_rfl

/-- **(L1) for every gain law**, window form: the full-window slacks are non-negative,
`W^{m-1}_k(x) ≥ 0` for every state below the target, whenever every possible landing level is at
least as good as the current one for reaching `m` (`H(i) ≤ H(ℓ)` if `ρ i J ℓ ≠ 0`). -/
theorem full_window_nonneg_of_landing (m : ℕ)
    (hH : ∀ i J ℓ, D.ρ i J ℓ ≠ 0 → H D m i ≤ H D m ℓ) (k : ℕ) :
    ∀ x : ℕ × ℕ, x.1 < m → 0 ≤ W D m (m - 1) k x := by
  induction k with
  | zero =>
    intro x hx
    apply le_of_eq
    symm
    unfold W
    apply S2_eq_zero
    intro J ℓ
    split_ifs with h
    · rw [s_zero_below D m x hx, s_zero_below D m (J, ℓ) (by simp only; omega)]; ring
    · rfl
  | succ k ih =>
    intro x hx
    -- each windowed term is at least `(1 - H(i)) ρ (s_k x - s_k y) - ρ W_k(x)`
    have hterm : ∀ J ℓ,
        (1 - H D m x.2) *
            (if x.1 < J ∧ J ≤ m - 1 then D.ρ x.2 J ℓ * (s D m k x - s D m k (J, ℓ)) else 0) -
          W D m (m - 1) k x * (if x.1 < J ∧ J ≤ m - 1 then D.ρ x.2 J ℓ else 0) ≤
        (if x.1 < J ∧ J ≤ m - 1 then
            D.ρ x.2 J ℓ * (s D m (k + 1) x - s D m (k + 1) (J, ℓ)) else 0) := by
      intro J ℓ
      split_ifs with h
      · have hy : (J, ℓ).1 < m := by simp only; omega
        rw [s_succ D m k x hx, s_succ D m k (J, ℓ) hy]
        have hWy := ih (J, ℓ) hy
        have hsy := s_nonneg D m k (J, ℓ)
        have hρ := D.nonneg x.2 J ℓ
        by_cases hρ0 : D.ρ x.2 J ℓ = 0
        · rw [hρ0]; simp
        · have hH := hH x.2 J ℓ hρ0
          have : (1 - H D m ℓ) * s D m k (J, ℓ) - W D m (m - 1) k (J, ℓ) ≤
              (1 - H D m x.2) * s D m k (J, ℓ) := by nlinarith
          nlinarith
      · simp
    have hsum := S2_mono (n := n) (L := L) hterm
    rw [S2_sub, S2_mul_left, S2_mul_left] at hsum
    change (1 - H D m x.2) * W D m (m - 1) k x - W D m (m - 1) k x * B D (m - 1) x ≤
      W D m (m - 1) (k + 1) x at hsum
    have hpart := partition D m x hx
    have hA := A_nonneg D x
    have hW := ih x hx
    have : (1 - H D m x.2) * W D m (m - 1) k x - W D m (m - 1) k x * B D (m - 1) x =
        A D x * W D m (m - 1) k x := by rw [← hpart]; ring
    nlinarith

/-- **(L1) for every gain law**, window form, under the note's hypotheses (gains `≥ 0`, `H`
non-decreasing in the level). -/
theorem full_window_nonneg (m : ℕ) (gain_nonneg : ∀ i J ℓ, D.ρ i J ℓ ≠ 0 → i ≤ ℓ)
    (H_mono : Monotone (H D m)) (k : ℕ) :
    ∀ x : ℕ × ℕ, x.1 < m → 0 ≤ W D m (m - 1) k x :=
  full_window_nonneg_of_landing D m (fun i J ℓ h => H_mono (gain_nonneg i J ℓ h)) k

/-- **(L1) for every gain law**: `s_{k+1}(x) ≤ (1 - H(i)) s_k(x)` below the target. -/
theorem L1 (m : ℕ) (gain_nonneg : ∀ i J ℓ, D.ρ i J ℓ ≠ 0 → i ≤ ℓ) (H_mono : Monotone (H D m))
    (k : ℕ) (x : ℕ × ℕ) (hx : x.1 < m) : s D m (k + 1) x ≤ (1 - H D m x.2) * s D m k x := by
  rw [s_succ D m k x hx]
  linarith [full_window_nonneg D m gain_nonneg H_mono k x hx]

/-! ## The distance-two closure -/

/-- At `c = m - 2` the landings' own windows `(m - 1, m - 1]` are empty. -/
theorem landingSlack_eq_zero (m k : ℕ) (x : ℕ × ℕ) (hx : x.1 + 2 = m) :
    landingSlack D m (m - 1) k x = 0 := by
  unfold landingSlack
  apply S2_eq_zero
  intro J ℓ
  split_ifs with h
  · have : W D m (m - 1) k (J, ℓ) = 0 := by
      unfold W
      apply S2_eq_zero
      intro J' ℓ'
      rw [ite_eq_right (by simp only; omega)]
    rw [this, mul_zero]
  · rfl

/-- **The distance-two closure** (note §6): at `c = m - 2` the negative term cancels and
`W_{k+1} = A W_k + E_k`, for every gain law. -/
theorem distance_two_closure (m k : ℕ) (x : ℕ × ℕ) (hx : x.1 + 2 = m) :
    W D m (m - 1) (k + 1) x = A D x * W D m (m - 1) k x + E D m (m - 1) k x := by
  rw [window_recursion D m (m - 1) k (by omega) x, landingSlack_eq_zero D m k x hx]
  have hpart := partition D m x (by omega)
  have : A D x = 1 - H D m x.2 - B D (m - 1) x := by linarith
  rw [this]
  ring

/-- **The distance-two theorem** (note §6): `W_k ≥ 0` at `c = m - 2` for every `k`, for every
gain law with non-negative gains and `H` non-decreasing in the level. -/
theorem distance_two_nonneg (m : ℕ) (gain_nonneg : ∀ i J ℓ, D.ρ i J ℓ ≠ 0 → i ≤ ℓ)
    (H_mono : Monotone (H D m)) (x : ℕ × ℕ) (hx : x.1 + 2 = m) (k : ℕ) :
    0 ≤ W D m (m - 1) k x := by
  induction k with
  | zero =>
    apply le_of_eq
    symm
    unfold W
    apply S2_eq_zero
    intro J ℓ
    split_ifs with h
    · rw [s_zero_below D m x (by omega), s_zero_below D m (J, ℓ) (by simp only; omega)]; ring
    · rfl
  | succ k ih =>
    rw [distance_two_closure D m k x hx]
    have := E_nonneg D m (m - 1) k x gain_nonneg H_mono
    have := A_nonneg D x
    positivity

/-- **Consequence:** one step of any threshold rule (cap `a(c) = c + t(c)`) followed by naive steps
is dominated by the naive rule for the hitting objective `1{c ≥ m}`, `(Q u_k)(x) ≤ (P u_k)(x)`, at
every state with `c ≥ m - 2`, for every gain law. (At `c ≥ m - 1` this is immediate; at `c = m - 2`
it is the distance-two theorem.) -/
theorem gated_le_naive_near_target (m : ℕ) (t : ℕ → ℕ)
    (gain_nonneg : ∀ i J ℓ, D.ρ i J ℓ ≠ 0 → i ≤ ℓ) (H_mono : Monotone (H D m)) (k : ℕ)
    (x : ℕ × ℕ) (hx : m ≤ x.1 + 2) :
    kernel D (fun c => c + t c) (u D m k) x ≤ kernel D id (u D m k) x := by
  have hdiff := kernel_sub D (fun c => c + t c) (u D m k) x (by simp)
  suffices h : 0 ≤ S2 n L fun J ℓ =>
      if x.1 < J ∧ J ≤ x.1 + t x.1 then D.ρ x.2 J ℓ * (u D m k (J, ℓ) - u D m k x) else 0 by
    linarith
  -- split the window at the target
  have hsplit : ∀ J ℓ,
      (if x.1 < J ∧ J ≤ x.1 + t x.1 then D.ρ x.2 J ℓ * (u D m k (J, ℓ) - u D m k x) else 0) =
        (if x.1 < J ∧ J ≤ x.1 + t x.1 ∧ J < m then
            D.ρ x.2 J ℓ * (s D m k x - s D m k (J, ℓ)) else 0) +
          (if x.1 < J ∧ J ≤ x.1 + t x.1 ∧ m ≤ J then D.ρ x.2 J ℓ * (1 - u D m k x) else 0) := by
    intro J ℓ
    by_cases h : x.1 < J ∧ J ≤ x.1 + t x.1
    · by_cases hm : J < m
      · rw [ite_eq_left h, ite_eq_left ⟨h.1, h.2, hm⟩, ite_eq_right (by omega)]
        unfold s; ring
      · rw [ite_eq_left h, ite_eq_right (by omega), ite_eq_left ⟨h.1, h.2, by omega⟩,
          u_top D m k (J, ℓ) (by simp only; omega)]
        ring
    · rw [ite_eq_right h, ite_eq_right (by tauto), ite_eq_right (by tauto)]; ring
  rw [S2_congr hsplit, S2_add]
  apply add_nonneg
  · -- the part below the target: empty, or the full window at `c = m - 2`
    by_cases hc : x.1 + 2 = m ∧ m - 1 ≤ x.1 + t x.1
    · have : (S2 n L fun J ℓ => if x.1 < J ∧ J ≤ x.1 + t x.1 ∧ J < m then
            D.ρ x.2 J ℓ * (s D m k x - s D m k (J, ℓ)) else 0) = W D m (m - 1) k x := by
        unfold W
        apply S2_congr
        intro J ℓ
        by_cases h : x.1 < J ∧ J ≤ x.1 + t x.1 ∧ J < m
        · rw [ite_eq_left h, ite_eq_left ⟨h.1, by omega⟩]
        · rw [ite_eq_right h, ite_eq_right (by omega)]
      rw [this]
      exact distance_two_nonneg D m gain_nonneg H_mono x hc.1 k
    · apply le_of_eq
      symm
      apply S2_eq_zero
      intro J ℓ
      rw [ite_eq_right (by omega)]
  · apply S2_nonneg
    intro J ℓ
    split_ifs
    · exact mul_nonneg (D.nonneg _ _ _) (by linarith [(u_bounds D m k x).2])
    · exact le_rfl

end FeedbackChannel.MultigenMixed

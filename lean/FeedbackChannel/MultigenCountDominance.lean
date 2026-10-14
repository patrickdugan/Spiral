import FeedbackChannel.MultigenMixed

/-!
# Proposition 9: dominance in count under a fixed gain (multigen note §6)

Source: `paper/evaluation_feedback_multigen.md`, draft 0.5, §6, Proposition 9; code
`src/spiral_ln/evaluation_feedback_multigen.py` (`count_dominance_lemma_fixture`).

**Fixed gain.** Every accepted candidate raises the level by one lattice step: from level `i` the
best candidate's count has law `π_i` and acceptance moves the level to `nx i` (`i + 1`, or the top
level, which is absorbing in the level). The hypothesis of the note's proof is that the best of
`K` is stochastically non-decreasing in the level; it enters only as `hstoch`:
`P(M_i ≥ m) ≤ P(M_{nx i} ≥ m)` for every `m` and `i`.

**Proposition 9.** For every threshold rule `t ≥ 0`, every state `x` and every `g`,
`P^t_x(c_g ≥ m) ≤ P^0_x(c_g ≥ m)` for every `m` (stochastic dominance of the count;
`gated_hit_le`), hence `E^t_x[ψ(c_g)] ≤ E^0_x[ψ(c_g)]` for every non-decreasing `ψ`
(`gated_expect_le`); one gated step followed by naive steps is already dominated
(`one_gated_step_le`).

*Proof (the note's lemmas).* `u_k = P^k 1{c ≥ m}`, `s_k = 1 - u_k`.
(L1) `s_{k+1}(x) ≤ (1 - H(x)) s_k(x)` — `MultigenMixed.full_window_nonneg_of_landing`.
(L2) `s_k(c, i) ≤ s_k(c + 1, i)` for `c + 1 < m` — `L2`.
(L3) `s_k(c, nx i) ≤ s_k(c, i)` — `L3`, through the comparison sequence `R` (`R_le_s`, `s_le_R`).
(L4) every window sum `W_a = (P u_k - Q u_k)(x)` is `≥ 0` — `L4`; then
`Q^k f = Q(Q^{k-1} f) ≤ Q(P^{k-1} f) ≤ P^k f`.
-/

namespace FeedbackChannel.MultigenCountDominance

open Finset FeedbackChannel.MultigenMixed

/-- A fixed-gain draw law: from level `i` the best count has law `π i`, and acceptance moves the
level to `nx i < L`. -/
structure FixedGain (n L : ℕ) where
  π : ℕ → ℕ → ℝ
  nx : ℕ → ℕ
  nonneg : ∀ i J, 0 ≤ π i J
  total : ∀ i, ∑ J ∈ range (n + 1), π i J = 1
  nx_lt : ∀ i, nx i < L

variable {n L : ℕ} (F : FixedGain n L)

/-- The fixed-gain law as a joint law of (count, landing level). -/
def FixedGain.toDrawLaw : DrawLaw n L where
  ρ i J ℓ := if ℓ = F.nx i then F.π i J else 0
  nonneg i J ℓ := by
    show 0 ≤ (if ℓ = F.nx i then F.π i J else 0)
    split_ifs
    · exact F.nonneg i J
    · exact le_rfl
  total i := by
    unfold S2
    rw [← F.total i]
    apply Finset.sum_congr rfl
    intro J _
    rw [Finset.sum_ite_eq' (range L) (F.nx i) (fun _ => F.π i J),
      ite_eq_left (mem_range.mpr (F.nx_lt i))]

/-- `P(M_i ≥ m)`. -/
def tail (m i : ℕ) : ℝ := ∑ J ∈ range (n + 1), if m ≤ J then F.π i J else 0

/-- `P(M_i ≤ c)`: the probability of staying at count `c`. -/
def stay (c i : ℕ) : ℝ := ∑ J ∈ range (n + 1), if J ≤ c then F.π i J else 0

/-- `P(c < M_i ≤ m - 1)`. -/
def mid (m c i : ℕ) : ℝ := ∑ J ∈ range (n + 1), if c < J ∧ J ≤ m - 1 then F.π i J else 0

theorem S2_conc (i : ℕ) (h : ℕ → ℕ → ℝ) (hz : ∀ J ℓ, ℓ ≠ F.nx i → h J ℓ = 0) :
    S2 n L h = ∑ J ∈ range (n + 1), h J (F.nx i) := by
  unfold S2
  apply Finset.sum_congr rfl
  intro J _
  rw [Finset.sum_eq_single (F.nx i)]
  · intro ℓ _ hℓ; exact hz J ℓ hℓ
  · intro h'; exact absurd (mem_range.mpr (F.nx_lt i)) h'

theorem rho_eq (i J ℓ : ℕ) : F.toDrawLaw.ρ i J ℓ = if ℓ = F.nx i then F.π i J else 0 := rfl

theorem H_eq (m i : ℕ) : H F.toDrawLaw m i = tail F m i := by
  unfold H tail
  rw [S2_conc F i]
  · simp [rho_eq]
  · intro J ℓ hℓ; simp [rho_eq, hℓ]

theorem A_eq (c i : ℕ) : A F.toDrawLaw (c, i) = stay F c i := by
  unfold A stay
  rw [S2_conc F i]
  · simp [rho_eq]
  · intro J ℓ hℓ; simp [rho_eq, hℓ]

theorem B_eq (m c i : ℕ) : B F.toDrawLaw (m - 1) (c, i) = mid F m c i := by
  unfold B mid
  rw [S2_conc F i]
  · simp [rho_eq]
  · intro J ℓ hℓ; simp [rho_eq, hℓ]

theorem kernel_eq (cap : ℕ → ℕ) (f : ℕ × ℕ → ℝ) (c i : ℕ) :
    kernel F.toDrawLaw cap f (c, i) =
      ∑ J ∈ range (n + 1), F.π i J * (if J ≤ cap c then f (c, i) else f (J, F.nx i)) := by
  unfold kernel
  rw [S2_conc F i]
  · simp [rho_eq]
  · intro J ℓ hℓ; simp [rho_eq, hℓ]

theorem W_eq (m a k c i : ℕ) : W F.toDrawLaw m a k (c, i) =
    ∑ J ∈ range (n + 1), if c < J ∧ J ≤ a then
      F.π i J * (s F.toDrawLaw m k (c, i) - s F.toDrawLaw m k (J, F.nx i)) else 0 := by
  unfold W
  rw [S2_conc F i]
  · apply Finset.sum_congr rfl; intro J _; simp [rho_eq]
  · intro J ℓ hℓ; simp [rho_eq, hℓ]

theorem stay_nonneg (c i : ℕ) : 0 ≤ stay F c i :=
  Finset.sum_nonneg fun J _ => by split_ifs <;> simp [F.nonneg]

/-- The landing level is never worse for reaching `m`. -/
theorem landing_le (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) :
    ∀ i J ℓ, F.toDrawLaw.ρ i J ℓ ≠ 0 → H F.toDrawLaw m i ≤ H F.toDrawLaw m ℓ := by
  intro i J ℓ h
  rw [rho_eq] at h
  have : ℓ = F.nx i := by
    by_contra hne; exact h (ite_eq_right hne)
  rw [this, H_eq, H_eq]
  exact hstoch i

/-- One naive step of `s` in the fixed-gain chain, below the target:
`s_{k+1}(c, i) = P(stay) s_k(c, i) + ∑_{c < J ≤ m-1} π_i(J) s_k(J, nx i)`. -/
theorem s_step (m k c i : ℕ) (hc : c < m) :
    s F.toDrawLaw m (k + 1) (c, i) = stay F c i * s F.toDrawLaw m k (c, i) +
      ∑ J ∈ range (n + 1),
        if c < J ∧ J ≤ m - 1 then F.π i J * s F.toDrawLaw m k (J, F.nx i) else 0 := by
  have h1 : s F.toDrawLaw m (k + 1) (c, i) = ∑ J ∈ range (n + 1), F.π i J *
      (if J ≤ c then s F.toDrawLaw m k (c, i) else s F.toDrawLaw m k (J, F.nx i)) := by
    show 1 - kernel F.toDrawLaw id (u F.toDrawLaw m k) (c, i) = _
    rw [kernel_eq, ← F.total i, ← Finset.sum_sub_distrib]
    apply Finset.sum_congr rfl
    intro J _
    simp only [id, s]
    split_ifs <;> ring
  rw [h1]
  unfold stay
  rw [Finset.sum_mul, ← Finset.sum_add_distrib]
  apply Finset.sum_congr rfl
  intro J _
  by_cases hJ1 : J ≤ c
  · rw [ite_eq_left hJ1, ite_eq_left hJ1, ite_eq_right (by omega)]; ring
  · by_cases hJ2 : m ≤ J
    · rw [ite_eq_right hJ1, ite_eq_right hJ1, ite_eq_right (by omega),
        s_top F.toDrawLaw m k (J, F.nx i) hJ2]
      ring
    · rw [ite_eq_right hJ1, ite_eq_right hJ1, ite_eq_left ⟨by omega, by omega⟩]; ring

theorem partition_eq (m c i : ℕ) (hc : c < m) : stay F c i + mid F m c i + tail F m i = 1 := by
  have := partition F.toDrawLaw m (c, i) hc
  rwa [A_eq, B_eq, H_eq] at this

/-- (L1) in the fixed-gain chain: `s_{k+1}(c, i) ≤ (1 - P(M_i ≥ m)) s_k(c, i)`. -/
theorem L1 (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (k c i : ℕ) (hc : c < m) :
    s F.toDrawLaw m (k + 1) (c, i) ≤ (1 - tail F m i) * s F.toDrawLaw m k (c, i) := by
  rw [s_succ F.toDrawLaw m k (c, i) hc, H_eq]
  have := full_window_nonneg_of_landing F.toDrawLaw m (landing_le F m hstoch) k (c, i) hc
  linarith

/-! ## (L2) and (L3) -/

/-- (L2) at horizon `k`, as a proposition. -/
def L2At (m k : ℕ) : Prop :=
  ∀ c i, c + 1 < m → s F.toDrawLaw m k (c, i) ≤ s F.toDrawLaw m k (c + 1, i)

theorem L2At_chain {m k : ℕ} (h : L2At F m k) (i : ℕ) {c J : ℕ} (hcJ : c ≤ J) (hJ : J < m) :
    s F.toDrawLaw m k (c, i) ≤ s F.toDrawLaw m k (J, i) := by
  induction J, hcJ using Nat.le_induction with
  | base => exact le_rfl
  | succ J hcJ ih => exact (ih (by omega)).trans (h J i hJ)

/-- The comparison sequence of (L3): wait at `(c, i)`, then run the chain from `(c, nx i)`. -/
noncomputable def R (m c i : ℕ) : ℕ → ℝ
  | 0 => 1
  | j + 1 => stay F c i * R m c i j + mid F m c i * s F.toDrawLaw m j (c, F.nx i)

theorem R_le_s (m k c i : ℕ) (hc : c < m) (hL2 : ∀ j < k, L2At F m j) :
    ∀ j ≤ k, R F m c i j ≤ s F.toDrawLaw m j (c, i) := by
  intro j
  induction j with
  | zero => intro _; rw [R, s_zero_below F.toDrawLaw m (c, i) hc]
  | succ j ih =>
    intro hj
    rw [R, s_step F m j c i hc]
    have hR := ih (by omega)
    have h1 : stay F c i * R F m c i j ≤ stay F c i * s F.toDrawLaw m j (c, i) :=
      mul_le_mul_of_nonneg_left hR (stay_nonneg F c i)
    have h2 : mid F m c i * s F.toDrawLaw m j (c, F.nx i) ≤ ∑ J ∈ range (n + 1),
        if c < J ∧ J ≤ m - 1 then F.π i J * s F.toDrawLaw m j (J, F.nx i) else 0 := by
      unfold mid
      rw [Finset.sum_mul]
      apply Finset.sum_le_sum
      intro J _
      split_ifs with h
      · have := L2At_chain F (hL2 j (by omega)) (F.nx i) (le_of_lt h.1) (by omega)
        exact mul_le_mul_of_nonneg_left this (F.nonneg i J)
      · simp
    linarith

theorem s_le_R (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (c i : ℕ) (hc : c < m) :
    ∀ j, s F.toDrawLaw m j (c, F.nx i) ≤ R F m c i j := by
  intro j
  induction j with
  | zero => rw [R, s_zero_below F.toDrawLaw m (c, F.nx i) hc]
  | succ j ih =>
    rw [R]
    have hL1 := L1 F m hstoch j c (F.nx i) hc
    have hσ := s_nonneg F.toDrawLaw m j (c, F.nx i)
    have hH := hstoch i
    have hpart := partition_eq F m c i hc
    have hA := stay_nonneg F c i
    have : (1 - tail F m (F.nx i)) * s F.toDrawLaw m j (c, F.nx i) ≤
        (stay F c i + mid F m c i) * s F.toDrawLaw m j (c, F.nx i) := by
      apply mul_le_mul_of_nonneg_right _ hσ
      linarith
    nlinarith

/-- (L3) at horizon `k`, given (L2) at every earlier horizon. -/
theorem L3_of_L2 (m k : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i))
    (hL2 : ∀ j < k, L2At F m j) (c i : ℕ) (hc : c < m) :
    s F.toDrawLaw m k (c, F.nx i) ≤ s F.toDrawLaw m k (c, i) :=
  (s_le_R F m hstoch c i hc k).trans (R_le_s F m k c i hc hL2 k le_rfl)

/-- **(L2)** `s_k(c, i) ≤ s_k(c + 1, i)` for `c + 1 < m`, every `k`. -/
theorem L2 (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (k : ℕ) : L2At F m k := by
  induction k using Nat.strong_induction_on with
  | _ k ih =>
    intro c i hc
    rcases k with _ | j
    · rw [s_zero_below F.toDrawLaw m (c, i) (by simp only; omega),
        s_zero_below F.toDrawLaw m (c + 1, i) (by simp only; omega)]
    · have hL2j := ih j (by omega)
      have hL3j := L3_of_L2 F m j hstoch (fun j' hj' => ih j' (by omega)) (c + 1) i hc
      rw [s_step F m j c i (by omega), s_step F m j (c + 1) i hc]
      unfold stay
      rw [Finset.sum_mul, Finset.sum_mul, ← sub_nonneg, add_sub_add_comm, ← Finset.sum_sub_distrib,
        ← Finset.sum_sub_distrib, ← Finset.sum_add_distrib]
      apply Finset.sum_nonneg
      intro J _
      have hπ := F.nonneg i J
      have hL2c := hL2j c i (by omega)
      by_cases h1 : J ≤ c
      · rw [ite_eq_left (by omega : J ≤ c + 1), ite_eq_left h1, ite_eq_right (by omega),
          ite_eq_right (by omega)]
        nlinarith
      · by_cases h2 : J = c + 1
        · subst h2
          rw [ite_eq_left le_rfl, ite_eq_right h1, ite_eq_right (by omega),
            ite_eq_left ⟨by omega, by omega⟩]
          nlinarith
        · rw [ite_eq_right (by omega : ¬ J ≤ c + 1), ite_eq_right h1]
          by_cases h3 : J ≤ m - 1
          · rw [ite_eq_left ⟨by omega, h3⟩, ite_eq_left ⟨by omega, h3⟩]; ring_nf; exact le_rfl
          · rw [ite_eq_right (by omega), ite_eq_right (by omega)]; ring_nf; exact le_rfl

/-- **(L3)** `s_k(c, nx i) ≤ s_k(c, i)` for `c < m`, every `k`. -/
theorem L3 (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (k c i : ℕ) (hc : c < m) :
    s F.toDrawLaw m k (c, F.nx i) ≤ s F.toDrawLaw m k (c, i) :=
  L3_of_L2 F m k hstoch (fun j _ => L2 F m hstoch j) c i hc

/-! ## (L4) and dominance -/

/-- **(L4)** every window sum is non-negative: `W_a(x) = ∑_{c < J ≤ a} π_i(J) [u_k(J, nx i) - u_k(c, i)] ≥ 0`. -/
theorem L4 (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (a k c i : ℕ) :
    0 ≤ W F.toDrawLaw m a k (c, i) := by
  rw [W_eq]
  by_cases hc : m ≤ c
  · apply Finset.sum_nonneg
    intro J _
    split_ifs with h
    · rw [s_top F.toDrawLaw m k (c, i) hc, s_top F.toDrawLaw m k (J, F.nx i) (by simp only; omega)]
      simp
    · exact le_rfl
  push Not at hc
  set sx := s F.toDrawLaw m k (c, i)
  set f : ℕ → ℝ := fun J => s F.toDrawLaw m k (J, F.nx i)
  -- the full window below the target is non-negative (L1)
  have hfull : 0 ≤ ∑ J ∈ range (n + 1),
      if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0 := by
    have := full_window_nonneg_of_landing F.toDrawLaw m (landing_le F m hstoch) k (c, i) hc
    rwa [W_eq] at this
  have hmono : ∀ J J', c < J → J ≤ J' → J' ≤ m - 1 → f J ≤ f J' := by
    intro J J' hJ hJJ' hJ'
    exact L2At_chain F (L2 F m hstoch k) (F.nx i) hJJ' (by omega)
  -- split the window at the target
  have hsplit : ∀ J, (if c < J ∧ J ≤ a then F.π i J * (sx - f J) else 0) =
      (if J ≤ a then (if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0) else 0) +
        (if c < J ∧ J ≤ a ∧ m ≤ J then F.π i J * sx else 0) := by
    intro J
    by_cases h1 : c < J ∧ J ≤ a
    · by_cases h2 : m ≤ J
      · rw [ite_eq_left h1, ite_eq_left h1.2, ite_eq_right (by omega), ite_eq_left ⟨h1.1, h1.2, h2⟩]
        simp only [f]
        rw [s_top F.toDrawLaw m k (J, F.nx i) h2]
        ring
      · rw [ite_eq_left h1, ite_eq_left h1.2, ite_eq_left ⟨h1.1, by omega⟩,
          ite_eq_right (by omega)]
        ring
    · rw [ite_eq_right h1]
      by_cases h3 : J ≤ a
      · have h4 : ¬ c < J := fun h => h1 ⟨h, h3⟩
        rw [ite_eq_left h3, ite_eq_right (fun h => h4 h.1), ite_eq_right (fun h => h4 h.1)]
        ring
      · rw [ite_eq_right h3, ite_eq_right (fun h => h3 h.2.1)]; ring
  rw [Finset.sum_congr rfl (fun J _ => hsplit J), Finset.sum_add_distrib]
  apply add_nonneg
  · -- the prefix of the full window
    by_contra hneg
    push Not at hneg
    obtain ⟨J0, hJ0, hlt⟩ := Finset.exists_lt_of_sum_lt (s := range (n + 1))
      (f := fun J => if J ≤ a then (if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0) else 0)
      (g := fun _ => (0 : ℝ)) (by simpa using hneg)
    have hJ0a : J0 ≤ a := by by_contra h; rw [ite_eq_right h] at hlt; exact lt_irrefl _ hlt
    rw [ite_eq_left hJ0a] at hlt
    have hJ0w : c < J0 ∧ J0 ≤ m - 1 := by
      by_contra h; rw [ite_eq_right h] at hlt; exact lt_irrefl _ hlt
    rw [ite_eq_left hJ0w] at hlt
    have hsx : sx < f J0 := by
      by_contra h
      push Not at h
      have := mul_nonneg (F.nonneg i J0) (sub_nonneg.mpr h)
      linarith
    -- the suffix of the full window is non-positive
    have hsuf : ∑ J ∈ range (n + 1),
        (if J ≤ a then 0 else (if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0)) ≤ 0 := by
      apply Finset.sum_nonpos
      intro J _
      split_ifs with ha hw
      · exact le_rfl
      · have := hmono J0 J hJ0w.1 (by omega) hw.2
        exact mul_nonpos_of_nonneg_of_nonpos (F.nonneg i J) (by linarith)
      · exact le_rfl
    have hdecomp : (∑ J ∈ range (n + 1),
        if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0) =
        (∑ J ∈ range (n + 1),
          if J ≤ a then (if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0) else 0) +
        ∑ J ∈ range (n + 1),
          (if J ≤ a then 0 else (if c < J ∧ J ≤ m - 1 then F.π i J * (sx - f J) else 0)) := by
      rw [← Finset.sum_add_distrib]
      apply Finset.sum_congr rfl
      intro J _
      split_ifs <;> ring
    linarith
  · apply Finset.sum_nonneg
    intro J _
    split_ifs
    · exact mul_nonneg (F.nonneg i J) (s_nonneg F.toDrawLaw m k (c, i))
    · exact le_rfl

/-- **One gated step followed by naive steps is dominated:** `Q P^k 1{c ≥ m} ≤ P^{k+1} 1{c ≥ m}`
for every threshold rule `t`. -/
theorem one_gated_step_le (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (t : ℕ → ℕ)
    (k : ℕ) (x : ℕ × ℕ) :
    kernel F.toDrawLaw (fun c => c + t c) (u F.toDrawLaw m k) x ≤
      kernel F.toDrawLaw id (u F.toDrawLaw m k) x := by
  have h := kernel_sub_u F.toDrawLaw (fun c => c + t c) m k x (by simp)
  have := L4 F m hstoch (x.1 + t x.1) k x.1 x.2
  simp only [Prod.mk.eta] at this
  linarith

theorem kernel_mono (cap : ℕ → ℕ) {f g : ℕ × ℕ → ℝ} (h : ∀ y, f y ≤ g y) (x : ℕ × ℕ) :
    kernel F.toDrawLaw cap f x ≤ kernel F.toDrawLaw cap g x := by
  unfold kernel
  apply S2_mono
  intro J ℓ
  apply mul_le_mul_of_nonneg_left _ (F.toDrawLaw.nonneg _ _ _)
  split_ifs
  · exact h x
  · exact h (J, ℓ)

/-- **Proposition 9, hitting form** (stochastic dominance of the count): for every threshold rule
`t`, state `x`, target `m` and generation `g`, `P^t_x(c_g ≥ m) ≤ P^0_x(c_g ≥ m)`. -/
theorem gated_hit_le (m : ℕ) (hstoch : ∀ i, tail F m i ≤ tail F m (F.nx i)) (t : ℕ → ℕ)
    (g : ℕ) (x : ℕ × ℕ) :
    (kernel F.toDrawLaw (fun c => c + t c))^[g] (hit m) x ≤ u F.toDrawLaw m g x := by
  induction g generalizing x with
  | zero => rfl
  | succ g ih =>
    rw [Function.iterate_succ_apply']
    exact (kernel_mono F _ ih x).trans (one_gated_step_le F m hstoch t g x)

/-! ## Non-decreasing objectives -/

theorem S2_finsum (M : Finset ℕ) (g : ℕ → ℕ → ℕ → ℝ) :
    S2 n L (fun J ℓ => ∑ m ∈ M, g m J ℓ) = ∑ m ∈ M, S2 n L (g m) := by
  unfold S2
  have : ∀ J, ∑ ℓ ∈ range L, ∑ m ∈ M, g m J ℓ = ∑ m ∈ M, ∑ ℓ ∈ range L, g m J ℓ :=
    fun J => Finset.sum_comm
  simp_rw [this]
  exact Finset.sum_comm

/-- The one-generation operator is affine: it fixes constants and is linear. -/
theorem kernel_affine (cap : ℕ → ℕ) (a : ℝ) (b : ℕ → ℝ) (M : Finset ℕ) (f : ℕ → ℕ × ℕ → ℝ)
    (x : ℕ × ℕ) :
    kernel F.toDrawLaw cap (fun y => a + ∑ m ∈ M, b m * f m y) x =
      a + ∑ m ∈ M, b m * kernel F.toDrawLaw cap (f m) x := by
  unfold kernel
  have hterm : ∀ J ℓ, F.toDrawLaw.ρ x.2 J ℓ * (if J ≤ cap x.1 then a + ∑ m ∈ M, b m * f m x
      else a + ∑ m ∈ M, b m * f m (J, ℓ)) =
      a * F.toDrawLaw.ρ x.2 J ℓ + ∑ m ∈ M, b m *
        (F.toDrawLaw.ρ x.2 J ℓ * (if J ≤ cap x.1 then f m x else f m (J, ℓ))) := by
    intro J ℓ
    split_ifs
    · rw [mul_add, Finset.mul_sum]
      congr 1
      · ring
      · apply Finset.sum_congr rfl; intro m _; ring
    · rw [mul_add, Finset.mul_sum]
      congr 1
      · ring
      · apply Finset.sum_congr rfl; intro m _; ring
  rw [S2_congr hterm, S2_add, S2_mul_left, F.toDrawLaw.total x.2, mul_one, S2_finsum]
  congr 1
  apply Finset.sum_congr rfl
  intro m _
  rw [S2_mul_left]

theorem iterate_affine (cap : ℕ → ℕ) (a : ℝ) (b : ℕ → ℝ) (M : Finset ℕ) (g : ℕ) :
    ∀ (f : ℕ → ℕ × ℕ → ℝ) (x : ℕ × ℕ),
      (kernel F.toDrawLaw cap)^[g] (fun y => a + ∑ m ∈ M, b m * f m y) x =
        a + ∑ m ∈ M, b m * (kernel F.toDrawLaw cap)^[g] (f m) x := by
  induction g with
  | zero => intro f x; rfl
  | succ g ih =>
    intro f x
    rw [Function.iterate_succ_apply]
    have : kernel F.toDrawLaw cap (fun y => a + ∑ m ∈ M, b m * f m y) =
        fun y => a + ∑ m ∈ M, b m * kernel F.toDrawLaw cap (f m) y :=
      funext fun y => kernel_affine F cap a b M f y
    rw [this, ih (fun m => kernel F.toDrawLaw cap (f m)) x]
    simp only [Function.iterate_succ_apply]

theorem u_eq_iterate (m g : ℕ) : u F.toDrawLaw m g = (kernel F.toDrawLaw id)^[g] (hit m) := by
  induction g with
  | zero => rfl
  | succ g ih =>
    rw [Function.iterate_succ_apply', ← ih]
    rfl

/-- A non-decreasing objective on counts `{0, …, n}` as a combination of hitting indicators. -/
theorem objective_decomp (ψ : ℕ → ℝ) (y : ℕ × ℕ) :
    ψ (min y.1 n) = ψ 0 + ∑ m ∈ range n, (ψ (m + 1) - ψ m) * hit (m + 1) y := by
  have hk : min y.1 n ≤ n := min_le_right _ _
  rw [← Finset.sum_range_add_sum_Ico _ hk]
  have h1 : ∑ m ∈ range (min y.1 n), (ψ (m + 1) - ψ m) * hit (m + 1) y =
      ∑ m ∈ range (min y.1 n), (ψ (m + 1) - ψ m) := by
    apply Finset.sum_congr rfl
    intro m hm
    rw [mem_range] at hm
    unfold hit
    rw [ite_eq_left (by omega), mul_one]
  have h2 : ∑ m ∈ Ico (min y.1 n) n, (ψ (m + 1) - ψ m) * hit (m + 1) y = 0 := by
    apply Finset.sum_eq_zero
    intro m hm
    rw [mem_Ico] at hm
    unfold hit
    rw [ite_eq_right (by omega), mul_zero]
  rw [h1, h2, Finset.sum_range_sub (fun m => ψ m)]
  ring

/-- **Proposition 9** (dominance in count): for every non-decreasing `ψ` on counts, every threshold
rule `t`, state `x` and generation `g`, `E^t_x[ψ(c_g)] ≤ E^0_x[ψ(c_g)]`. -/
theorem gated_expect_le (hstoch : ∀ m i, tail F m i ≤ tail F m (F.nx i)) (t : ℕ → ℕ)
    (ψ : ℕ → ℝ) (hψ : Monotone ψ) (g : ℕ) (x : ℕ × ℕ) :
    (kernel F.toDrawLaw (fun c => c + t c))^[g] (fun y => ψ (min y.1 n)) x ≤
      (kernel F.toDrawLaw id)^[g] (fun y => ψ (min y.1 n)) x := by
  have hdec : (fun y : ℕ × ℕ => ψ (min y.1 n)) =
      fun y => ψ 0 + ∑ m ∈ range n, (ψ (m + 1) - ψ m) * hit (m + 1) y :=
    funext (objective_decomp (n := n) ψ)
  rw [hdec, iterate_affine F _ (ψ 0) (fun m => ψ (m + 1) - ψ m) (range n) g
      (fun m => hit (m + 1)) x,
    iterate_affine F _ (ψ 0) (fun m => ψ (m + 1) - ψ m) (range n) g (fun m => hit (m + 1)) x]
  apply add_le_add le_rfl
  apply Finset.sum_le_sum
  intro m _
  apply mul_le_mul_of_nonneg_left _ (sub_nonneg.mpr (hψ (Nat.le_succ m)))
  rw [← u_eq_iterate]
  exact gated_hit_le F (m + 1) (hstoch (m + 1)) t g x

end FeedbackChannel.MultigenCountDominance

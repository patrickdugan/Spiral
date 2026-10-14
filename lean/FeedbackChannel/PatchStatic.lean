import FeedbackChannel.PatchDP

/-!
# Static patch schedules: Propositions 3 and 4 of the lattice note

Source: `paper/evaluation_feedback_lattice.md` (version 0.6), §3; Python
`conditional_hit_probability`, `expected_hits_after`, `expected_score_crossing`,
`expected_patches_static`, `crossing_error_bound`.

A *static schedule* patches the categories one after another in a fixed list order, each completely,
each uniformly at random without replacement. All probabilities are obtained by first-step analysis
on `(n, F)` exactly as in the dynamic programme: a patch in `(n, F)` hits with probability `F / n`,
leaving `(n - 1, F - 1)`, else `(n - 1, F)`.
-/

namespace FeedbackChannel.PatchStatic

open FeedbackChannel.PatchDP

/-! ### Proposition 3: every patch in a category has the same unconditional hit probability -/

/-- Unconditional probability that the `(j + 1)`-th patch in a category with `n` items and `F`
failures hits (first-step analysis on the first patch). -/
def hitProb : ℕ → ℕ → ℕ → ℚ
  | 0, n, F => (F : ℚ) / n
  | j + 1, n, F => (F : ℚ) / n * hitProb j (n - 1) (F - 1) + (1 - (F : ℚ) / n) * hitProb j (n - 1) F

/-- **Proposition 3 (exchangeability).** The `j`-th patch in a category hits with unconditional
probability `F / n` for every `j ≤ n`. (The conditional probability `(F - h) / (n - j + 1)` given
`h` earlier hits is the model's transition: after `j - 1` patches with `h` hits the category is
`(n - j + 1, F - h)` and `rate` of that pair is the stated ratio.) -/
theorem prop3_hitProb : ∀ (j n F : ℕ), j < n → F ≤ n → hitProb j n F = (F : ℚ) / n := by
  intro j
  induction j with
  | zero => intro n F _ _; rfl
  | succ j ih =>
    intro n F hj hF
    obtain ⟨m, rfl⟩ : ∃ m, n = m + 1 := ⟨n - 1, by omega⟩
    have hm : 0 < m := by omega
    simp only [hitProb, Nat.add_sub_cancel]
    have hmq : (m : ℚ) ≠ 0 := by exact_mod_cast hm.ne'
    rcases Nat.eq_zero_or_pos F with h0 | h1
    · subst h0; simp; rw [ih m 0 (by omega) (by omega)]; simp
    rw [ih m (F - 1) (by omega) (by omega)]
    rcases Nat.lt_or_ge F (m + 1) with hlt | hge
    · rw [ih m F (by omega) (by omega)]
      rw [Nat.cast_sub h1]
      push_cast
      field_simp
      ring
    · have : F = m + 1 := by omega
      subst this
      push_cast
      rw [div_self (by positivity)]
      simp only [Nat.add_sub_cancel, sub_self, zero_mul, add_zero, one_mul]
      field_simp

/-- Expected hits of `m` patches in one category (first-step analysis). -/
def expHits : ℕ → ℕ → ℕ → ℚ
  | 0, _, _ => 0
  | m + 1, n, F => (F : ℚ) / n * (1 + expHits m (n - 1) (F - 1)) + (1 - (F : ℚ) / n) * expHits m (n - 1) F

/-- **Proposition 3 (hypergeometric mean).** `m` patches in a category hit `m F / n` in
expectation, for every `m ≤ n`. -/
theorem prop3_expHits : ∀ (m n F : ℕ), m ≤ n → F ≤ n → expHits m n F = (m : ℚ) * F / n := by
  intro m
  induction m with
  | zero => intro n F _ _; simp [expHits]
  | succ m ih =>
    intro n F hm hF
    obtain ⟨k, rfl⟩ : ∃ k, n = k + 1 := ⟨n - 1, by omega⟩
    simp only [expHits, Nat.add_sub_cancel]
    rcases Nat.eq_zero_or_pos m with hm0 | hmpos
    · subst hm0; simp [expHits]
    have hk : 0 < k := by omega
    have hkq : (k : ℚ) ≠ 0 := by exact_mod_cast hk.ne'
    rcases Nat.eq_zero_or_pos F with h0 | h1
    · subst h0; rw [ih k 0 (by omega) (by omega)]; simp
    rw [ih k (F - 1) (by omega) (by omega)]
    rcases Nat.lt_or_ge F (k + 1) with hlt | hge
    · rw [ih k F (by omega) (by omega), Nat.cast_sub h1]
      push_cast
      field_simp
      ring
    · have : F = k + 1 := by omega
      subst this
      push_cast
      rw [div_self (by positivity)]
      simp only [Nat.add_sub_cancel, sub_self, zero_mul, add_zero, one_mul]
      field_simp
      ring

/-! ### The static schedule's stopping time -/

/-- Fuel for the static recursion: items plus categories (each step consumes an item or drops an
exhausted category). -/
def sfuel (L : List Cat) : ℕ := (L.map Prod.fst).sum + L.length

/-- Expected patches to `H` hits under the static schedule that patches the categories of `L`
completely, in list order (first-step analysis, fuel `sfuel`). -/
def sdp : ℕ → ℕ → List Cat → ℚ
  | 0, _, _ => 0
  | _ + 1, 0, _ => 0
  | _ + 1, _ + 1, [] => 0
  | k + 1, H + 1, (0, _) :: L => sdp k (H + 1) L
  | k + 1, H + 1, (n + 1, F) :: L =>
    1 + (F : ℚ) / (n + 1) * sdp k H ((n, F - 1) :: L) + (1 - (F : ℚ) / (n + 1)) * sdp k (H + 1) ((n, F) :: L)

/-- `E[T]`: expected number of patches until the realized hit count first reaches `H`. -/
def staticT (H : ℕ) (L : List Cat) : ℚ := sdp (sfuel L) H L

lemma sfuel_cons (n F : ℕ) (L : List Cat) : sfuel ((n, F) :: L) = n + sfuel L + 1 := by
  simp [sfuel]; ring

lemma staticT_zero (L : List Cat) : staticT 0 L = 0 := by
  unfold staticT; cases sfuel L <;> simp [sdp]

lemma staticT_empty (H : ℕ) (F : ℕ) (L : List Cat) (hH : 0 < H) :
    staticT H ((0, F) :: L) = staticT H L := by
  obtain ⟨h, rfl⟩ : ∃ h, H = h + 1 := ⟨H - 1, by omega⟩
  unfold staticT
  rw [sfuel_cons, zero_add]
  rfl

lemma staticT_step (H n F : ℕ) (L : List Cat) :
    staticT (H + 1) ((n + 1, F) :: L) =
      1 + (F : ℚ) / (n + 1) * staticT H ((n, F - 1) :: L) +
        (1 - (F : ℚ) / (n + 1)) * staticT (H + 1) ((n, F) :: L) := by
  unfold staticT
  rw [sfuel_cons, sfuel_cons, sfuel_cons]
  rw [show n + 1 + sfuel L + 1 = (n + sfuel L + 1) + 1 by ring]
  rfl

/-- Inside the crossing category: `E[T] = H (n + 1) / (F + 1)` when `1 ≤ H ≤ F ≤ n`, whatever
follows (the run stops before leaving the category). -/
theorem staticT_within : ∀ (n H F : ℕ) (L : List Cat), H ≤ F → F ≤ n →
    staticT H ((n, F) :: L) = (H : ℚ) * ((n : ℚ) + 1) / ((F : ℚ) + 1) := by
  intro n
  induction n with
  | zero =>
    intro H F L h1 h2
    have : H = 0 := by omega
    subst this; simp [staticT_zero]
  | succ n ih =>
    intro H F L h1 h2
    rcases H with _ | h
    · simp [staticT_zero]
    obtain ⟨G, rfl⟩ : ∃ G, F = G + 1 := ⟨F - 1, by omega⟩
    rw [staticT_step, Nat.add_sub_cancel, ih h G L (by omega) (by omega)]
    rcases Nat.lt_or_ge G n with hlt | hge
    · rw [ih (h + 1) (G + 1) L (by omega) (by omega)]
      push_cast
      field_simp
      ring
    · have : G = n := by omega
      subst this
      push_cast
      rw [div_self (by positivity)]
      field_simp
      ring

/-- Past a category whose failures do not reach the requirement, the schedule spends all of its
`n` items and continues with `H - F` hits still needed. -/
theorem staticT_skip : ∀ (n H F : ℕ) (L : List Cat), F < H → F ≤ n →
    staticT H ((n, F) :: L) = n + staticT (H - F) L := by
  intro n
  induction n with
  | zero =>
    intro H F L h1 h2
    have : F = 0 := by omega
    subst this
    rw [staticT_empty _ _ _ (by omega)]; simp
  | succ n ih =>
    intro H F L h1 h2
    obtain ⟨h, rfl⟩ : ∃ h, H = h + 1 := ⟨H - 1, by omega⟩
    rw [staticT_step]
    rcases Nat.eq_zero_or_pos F with h0 | hpos
    · subst h0
      rw [ih (h + 1) 0 L (by omega) (by omega)]
      push_cast; ring
    rcases Nat.lt_or_ge F (n + 1) with hlt | hge
    · rw [ih h (F - 1) L (by omega) (by omega), ih (h + 1) F L (by omega) (by omega),
        show h - (F - 1) = h + 1 - F by omega]
      push_cast
      field_simp
      ring
    · have : F = n + 1 := by omega
      subst this
      simp only [Nat.add_sub_cancel]
      rw [ih h n L (by omega) (by omega), show h - n = h + 1 - (n + 1) by omega]
      push_cast
      rw [div_self (by positivity)]
      ring

/-- Failures in a list of categories. -/
def lfails (L : List Cat) : ℕ := (L.map Prod.snd).sum

/-- Items in a list of categories. -/
def litems (L : List Cat) : ℕ := (L.map Prod.fst).sum

/-- **Proposition 4 (stopping time of the static schedule).** Let the schedule patch the
categories in the order `pre ++ c :: post`, where `c = (n_j, F_j)` is the first category at which
the cumulative failures reach `H` (`F(pre) < H ≤ F(pre) + F_j`). Then the expected number of
patches until the realized hit count first reaches `H` is
`N_{<j} + H_j (n_j + 1) / (F_j + 1)`, with `N_{<j}` the items of `pre` and `H_j = H - F(pre)`.
This holds for every fixed order, in particular for the greedy one. -/
theorem prop4_staticT (pre post : List Cat) (c : Cat) (H : ℕ) (hv : ∀ d ∈ pre ++ c :: post, d.2 ≤ d.1)
    (hlo : lfails pre < H) (hhi : H ≤ lfails pre + c.2) :
    staticT H (pre ++ c :: post) =
      (litems pre : ℚ) + ((H - lfails pre : ℕ) : ℚ) * ((c.1 : ℚ) + 1) / ((c.2 : ℚ) + 1) := by
  induction pre generalizing H with
  | nil =>
    simp only [lfails, litems, List.map_nil, List.sum_nil, Nat.cast_zero, zero_add, Nat.sub_zero,
      List.nil_append] at *
    obtain ⟨n, F⟩ := c
    exact staticT_within n H F post hhi (hv _ List.mem_cons_self)
  | cons d pre ih =>
    obtain ⟨n, F⟩ := d
    simp only [lfails, litems, List.map_cons, List.sum_cons] at hlo hhi ⊢
    have hd := hv (n, F) (by simp)
    simp only [List.cons_append]
    rw [staticT_skip n H F _ (by omega) hd]
    rw [ih (H - F) (fun e he => hv e (by simp [he])) (by simp only [lfails]; omega)
      (by simp only [lfails]; omega)]
    simp only [lfails, litems]
    rw [show H - F - (pre.map Prod.snd).sum = H - (F + (pre.map Prod.snd).sum) by omega]
    push_cast
    ring

/-! ### The expected-score crossing `m*` -/

/-- Expected hits after `m` patches of the static schedule, linear between integers: the
`expected_hits_after` curve. -/
def curve : List Cat → ℚ → ℚ
  | [], _ => 0
  | c :: L, m => if m ≤ c.1 then m * rate c else c.2 + curve L (m - c.1)

/-- At whole patch counts inside one category the curve is the hypergeometric mean of
Proposition 3, so it is the expected number of hits. -/
theorem curve_single (n F m : ℕ) (L : List Cat) (hm : m ≤ n) (hF : F ≤ n) :
    curve ((n, F) :: L) m = expHits m n F := by
  rw [prop3_expHits m n F hm hF]
  simp only [curve, rate_mk, Nat.cast_le.2 hm, if_true]
  ring


/-- The note's `m* = N_{<j} + H_j n_j / F_j` for the split `pre ++ c :: post`. -/
def mstar (pre : List Cat) (c : Cat) (H : ℕ) : ℚ :=
  (litems pre : ℚ) + ((H - lfails pre : ℕ) : ℚ) * (c.1 : ℚ) / (c.2 : ℚ)

/-- **Proposition 4 (expected-score crossing).** With the split of `prop4_staticT`, the expected
hit curve of the static schedule equals `H` at `m*` and is strictly below `H` at every earlier
patch count, so `m*` is where the expected score reaches the ceiling. -/
theorem prop4_crossing (pre post : List Cat) (c : Cat) (H : ℕ)
    (hv : ∀ d ∈ pre ++ c :: post, d.2 ≤ d.1) (hlo : lfails pre < H) (hhi : H ≤ lfails pre + c.2) :
    curve (pre ++ c :: post) (mstar pre c H) = H ∧
      ∀ m : ℚ, 0 ≤ m → m < mstar pre c H → curve (pre ++ c :: post) m < H := by
  induction pre generalizing H with
  | nil =>
    obtain ⟨n, F⟩ := c
    simp only [lfails, litems, List.map_nil, List.sum_nil, Nat.sub_zero, mstar, Nat.cast_zero,
      zero_add, List.nil_append] at hlo hhi ⊢
    have hd := hv (n, F) (by simp)
    simp only at hhi hd
    have hFq : (0 : ℚ) < F := by exact_mod_cast (show 0 < F by omega)
    have hnq : (0 : ℚ) < n := by exact_mod_cast (show 0 < n by omega)
    have hHF : (H : ℚ) ≤ F := by exact_mod_cast hhi
    have hle : (H : ℚ) * n / F ≤ n := by
      rw [div_le_iff₀ hFq]; nlinarith
    refine ⟨?_, ?_⟩
    · simp only [curve, rate_mk, hle, if_true]
      field_simp
    · intro m hm hlt
      have hmn : m ≤ n := (le_of_lt hlt).trans hle
      simp only [curve, rate_mk, hmn, if_true]
      rw [lt_div_iff₀ hFq] at hlt
      rw [mul_div_assoc', div_lt_iff₀ hnq]
      nlinarith
  | cons d pre ih =>
    obtain ⟨n, F⟩ := d
    have hd := hv (n, F) (by simp)
    simp only at hd
    simp only [lfails, litems, List.map_cons, List.sum_cons] at hlo hhi
    have ih' := ih (H - F) (fun e he => hv e (by simp [he])) (by simp only [lfails]; omega)
      (by simp only [lfails]; omega)
    have hms : mstar ((n, F) :: pre) c H = n + mstar pre c (H - F) := by
      simp only [mstar, litems, lfails, List.map_cons, List.sum_cons]
      rw [show H - (F + (pre.map Prod.snd).sum) = H - F - (pre.map Prod.snd).sum by omega]
      push_cast; ring
    -- the crossing lies strictly beyond this category
    have hpos : 0 < mstar pre c (H - F) := by
      have hc := hv c (by simp)
      simp only [mstar]
      have h1 : (0 : ℚ) ≤ litems pre := by positivity
      have h2 : (0 : ℚ) < ((H - F - lfails pre : ℕ) : ℚ) := by
        exact_mod_cast (show 0 < H - F - lfails pre by simp only [lfails]; omega)
      have h3 : (0 : ℚ) < c.1 := by exact_mod_cast (show 0 < c.1 by simp only [lfails] at *; omega)
      have h4 : (0 : ℚ) < c.2 := by exact_mod_cast (show 0 < c.2 by simp only [lfails] at *; omega)
      have : (0 : ℚ) < ((H - F - lfails pre : ℕ) : ℚ) * c.1 / c.2 := by positivity
      linarith
    refine ⟨?_, ?_⟩
    · rw [hms]
      simp only [List.cons_append, curve, rate_mk]
      rw [if_neg (by linarith), show (n : ℚ) + mstar pre c (H - F) - n = mstar pre c (H - F) by ring,
        ih'.1]
      push_cast [show F ≤ H by omega]
      ring
    · intro m hm hlt
      rw [hms] at hlt
      simp only [List.cons_append, curve, rate_mk]
      split_ifs with h
      · have hFH : (F : ℚ) < H := by exact_mod_cast (show F < H by omega)
        rcases Nat.eq_zero_or_pos n with h0 | hnpos
        · subst h0; simp only [Nat.cast_zero, div_zero, mul_zero]; exact_mod_cast (show 0 < H by omega)
        have hnq : (0 : ℚ) < n := by exact_mod_cast hnpos
        have : m * ((F : ℚ) / n) ≤ F := by
          rw [mul_div_assoc', div_le_iff₀ hnq]
          have : (0 : ℚ) ≤ F := by positivity
          nlinarith
        linarith
      · push Not at h
        have := ih'.2 (m - n) (by linarith) (by linarith)
        push_cast [show F ≤ H by omega] at this
        linarith

/-- **Proposition 4 (the gap).** `m* - E[T] = H_j (n_j - F_j) / (F_j (F_j + 1))`, which lies in
`[0, m* / (F_j + 1))`: the expected-score crossing never understates the expected patch count. -/
theorem prop4_gap (pre post : List Cat) (c : Cat) (H : ℕ)
    (hv : ∀ d ∈ pre ++ c :: post, d.2 ≤ d.1) (hlo : lfails pre < H) (hhi : H ≤ lfails pre + c.2) :
    mstar pre c H - staticT H (pre ++ c :: post) =
        ((H - lfails pre : ℕ) : ℚ) * ((c.1 : ℚ) - c.2) / ((c.2 : ℚ) * ((c.2 : ℚ) + 1)) ∧
      0 ≤ mstar pre c H - staticT H (pre ++ c :: post) ∧
      mstar pre c H - staticT H (pre ++ c :: post) < mstar pre c H / ((c.2 : ℚ) + 1) := by
  rw [prop4_staticT pre post c H hv hlo hhi]
  have hc := hv c (by simp)
  set Hj : ℚ := ((H - lfails pre : ℕ) : ℚ) with hHj
  have hHj1 : (1 : ℚ) ≤ Hj := by rw [hHj]; exact_mod_cast (show 1 ≤ H - lfails pre by omega)
  have hF : (1 : ℚ) ≤ c.2 := by exact_mod_cast (show 1 ≤ c.2 by omega)
  have hFn : (c.2 : ℚ) ≤ c.1 := by exact_mod_cast hc
  have hN : (0 : ℚ) ≤ litems pre := by positivity
  simp only [mstar, ← hHj]
  have hF0 : (c.2 : ℚ) ≠ 0 := by positivity
  have hF1 : (c.2 : ℚ) + 1 ≠ 0 := by positivity
  have key : (litems pre : ℚ) + Hj * c.1 / c.2 - ((litems pre : ℚ) + Hj * (c.1 + 1) / (c.2 + 1)) =
      Hj * (c.1 - c.2) / (c.2 * (c.2 + 1)) := by
    field_simp; ring
  refine ⟨key, ?_, ?_⟩
  · rw [key]; apply div_nonneg <;> nlinarith
  · rw [key]
    have hdiff : ((litems pre : ℚ) + Hj * c.1 / c.2) / ((c.2 : ℚ) + 1) -
        Hj * (c.1 - c.2) / (c.2 * (c.2 + 1)) = ((litems pre : ℚ) + Hj) / ((c.2 : ℚ) + 1) := by
      field_simp; ring
    have : (0 : ℚ) < ((litems pre : ℚ) + Hj) / ((c.2 : ℚ) + 1) := by
      apply div_pos <;> linarith
    linarith

/-! ### The note's numbers -/

/-- One category, `n = 50`, `F = 13`, `H = 8`: `m* / n = 8 / 13 = (1 - ε - v) / (1 - v)` with
`ε = 1/10`, `v = 37/50`, and `E[T] = 204 / 7`; the dynamic programme gives the same `E[T]`. -/
theorem prop4_one_category :
    mstar [] (50, 13) 8 / 50 = 8 / 13 ∧ (1 - 1 / 10 - 37 / 50 : ℚ) / (1 - 37 / 50) = 8 / 13 ∧
      staticT 8 [(50, 13)] = 204 / 7 ∧ val 8 {(50, 13)} = 204 / 7 := by
  refine ⟨by norm_num [mstar, litems, lfails], by norm_num, ?_, ?_⟩
  · rw [staticT_within 50 8 13 [] (by norm_num) (by norm_num)]; norm_num
  · rw [val_single 50 8 13 (by norm_num) (by norm_num)]; norm_num

/-- Singleton categories (13 failing, 37 passing items, failures first, `H = 8`): `m*` and `E[T]`
both equal `H`, a share `4/25` of the 50 items. -/
theorem prop4_singletons :
    mstar (List.replicate 7 (1, 1)) (1, 1) 8 = 8 ∧
      staticT 8 (List.replicate 7 (1, 1) ++ (1, 1) :: (List.replicate 5 (1, 1) ++ List.replicate 37 (1, 0))) = 8 ∧
      (8 : ℚ) / 50 = 4 / 25 := by
  have hv : ∀ d ∈ List.replicate 7 ((1 : ℕ), (1 : ℕ)) ++ (1, 1) ::
      (List.replicate 5 (1, 1) ++ List.replicate 37 (1, 0)), d.2 ≤ d.1 := by
    intro d hd
    simp only [List.mem_append, List.mem_replicate, List.mem_cons] at hd
    rcases hd with ⟨_, rfl⟩ | rfl | ⟨_, rfl⟩ | ⟨_, rfl⟩ <;> simp
  have hl : lfails (List.replicate 7 ((1 : ℕ), (1 : ℕ))) = 7 := by
    simp [lfails, List.map_replicate, List.sum_replicate]
  have hi : litems (List.replicate 7 ((1 : ℕ), (1 : ℕ))) = 7 := by
    simp [litems, List.map_replicate, List.sum_replicate]
  refine ⟨?_, ?_, by norm_num⟩
  · simp only [mstar, hl, hi]; norm_num
  · rw [prop4_staticT _ _ (1, 1) 8 hv (by rw [hl]; norm_num) (by rw [hl]; norm_num)]
    rw [hl, hi]; norm_num


/-- **The static stopping time is not monotone along refinement** (the note's witness). One block
`(4,2)` with `H = 2` gives `E[T] = 10/3`; its refinement into `(2,1), (2,1)` gives `7/2`. -/
theorem static_not_monotone :
    staticT 2 [(4, 2)] = 10 / 3 ∧ staticT 2 [(2, 1), (2, 1)] = 7 / 2 := by
  refine ⟨?_, ?_⟩
  · rw [staticT_within 4 2 2 [] (by norm_num) (by norm_num)]; norm_num
  · have h := prop4_staticT [(2, 1)] [] (2, 1) 2 (by decide) (by decide) (by decide)
    simp only [List.singleton_append] at h
    rw [h]
    norm_num [litems, lfails]

end FeedbackChannel.PatchStatic

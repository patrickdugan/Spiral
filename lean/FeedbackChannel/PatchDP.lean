import Mathlib.Tactic
import Mathlib.Data.Finset.Lattice.Fold
import Mathlib.Algebra.BigOperators.Group.Multiset.Basic

/-!
# The adaptive patch programme (lattice note §3)

Source: `paper/evaluation_feedback_lattice.md` (version 0.6), §3, and the dynamic programme
`_optimal_value` of `src/spiral_ln/evaluation_feedback_lattice.py`.

**Model.** The loop sees, per category, the pair `(n, F)`: `n` unpatched items, `F` of which still
fail. A *state* is the multiset of these pairs (categories with equal pairs are exchangeable, which
is the Python state, a sorted tuple of pairs). A patch picks a category with `n ≥ 1` and a uniformly
random unpatched item in it: it hits with probability `F / n`, leaving `(n - 1, F - 1)`, and
otherwise leaves `(n - 1, F)`. The run stops when `H` hits have been made. `val H s` is the minimum
expected number of patches, defined by the Bellman recursion (`dp`, fuel = items left; every patch
consumes one item, so the fuel is exact).

Differences from the Python programme, none of which changes a value on a feasible state:
* the Python state drops categories with `F = 0`; here they stay and *may be chosen* (a wasted
  patch), as the note's policy class allows ("a category they choose"). The theorems below show
  such patches are never better.
* on an infeasible state (`H` larger than the failures left, in particular no item left) the value
  is a junk `0`; every theorem assumes feasibility.
-/

namespace FeedbackChannel.PatchDP

/-- A category as the loop sees it: `(n, F)`, unpatched items and failures among them. -/
abbrev Cat := ℕ × ℕ

/-- Hit probability of a patch in `c`: `F / n`. -/
def rate (c : Cat) : ℚ := (c.2 : ℚ) / c.1

/-- The category after a hit. -/
def hitC (c : Cat) : Cat := (c.1 - 1, c.2 - 1)

/-- The category after a miss. -/
def missC (c : Cat) : Cat := (c.1 - 1, c.2)

/-- Unpatched items left in a state. -/
def items (s : Multiset Cat) : ℕ := (s.map Prod.fst).sum

/-- Failures left in a state. -/
def fails (s : Multiset Cat) : ℕ := (s.map Prod.snd).sum

/-- A state is valid when every category has `F ≤ n`. -/
def Valid (s : Multiset Cat) : Prop := ∀ c ∈ s, c.2 ≤ c.1

instance : DecidablePred Valid := fun s => by unfold Valid; infer_instance

/-- The categories a patch may go to: those with an unpatched item. -/
def choices (s : Multiset Cat) : Finset Cat := s.toFinset.filter (fun c => 0 < c.1)

/-- The Bellman recursion with fuel. `dp k H s`: minimum expected patches to `H` more hits. -/
def dp : ℕ → ℕ → Multiset Cat → ℚ
  | 0, _, _ => 0
  | _ + 1, 0, _ => 0
  | k + 1, H + 1, s =>
    if h : (choices s).Nonempty then
      (choices s).inf' h fun c =>
        1 + rate c * dp k H (hitC c ::ₘ s.erase c) + (1 - rate c) * dp k (H + 1) (missC c ::ₘ s.erase c)
    else 0

/-- The optimal expected number of patches to `H` hits from state `s` (`V*` of the note). -/
def val (H : ℕ) (s : Multiset Cat) : ℚ := dp (items s) H s

/-- Expected patches to `H ≥ 1` hits when the first patch goes to `c` and every later patch is
optimal (`first_patch_values` / `_continuation` in the Python module). -/
def firstPatch (H : ℕ) (s : Multiset Cat) (c : Cat) : ℚ :=
  1 + rate c * val (H - 1) (hitC c ::ₘ s.erase c) + (1 - rate c) * val H (missC c ::ₘ s.erase c)

/-- The one-hit value of a category, `(n + 1) / (F + 1)`: the note's "finisher". -/
def finisher (c : Cat) : ℚ := ((c.1 : ℚ) + 1) / ((c.2 : ℚ) + 1)

/-! ### Bookkeeping -/

@[simp] lemma rate_mk (n F : ℕ) : rate (n, F) = (F : ℚ) / n := rfl
@[simp] lemma finisher_mk (n F : ℕ) : finisher (n, F) = ((n : ℚ) + 1) / ((F : ℚ) + 1) := rfl
@[simp] lemma hitC_mk (n F : ℕ) : hitC (n, F) = (n - 1, F - 1) := rfl
@[simp] lemma missC_mk (n F : ℕ) : missC (n, F) = (n - 1, F) := rfl

lemma items_cons (x : Cat) (s : Multiset Cat) : items (x ::ₘ s) = x.1 + items s := by
  simp [items]

lemma items_erase {s : Multiset Cat} {c : Cat} (hc : c ∈ s) : items s = c.1 + items (s.erase c) := by
  conv_lhs => rw [← Multiset.cons_erase hc]
  exact items_cons _ _

lemma fst_le_items {s : Multiset Cat} {c : Cat} (hc : c ∈ s) : c.1 ≤ items s := by
  rw [items_erase hc]; omega

lemma items_after {s : Multiset Cat} {c : Cat} (hc : c ∈ s) (hpos : 0 < c.1) (m : ℕ) :
    items ((c.1 - 1, m) ::ₘ s.erase c) + 1 = items s := by
  rw [items_cons, items_erase hc]; simp only; omega

lemma mem_after {s : Multiset Cat} {c x d : Cat} (hd : d ∈ x ::ₘ s.erase c) : d = x ∨ d ∈ s := by
  rcases Multiset.mem_cons.1 hd with h | h
  · exact Or.inl h
  · exact Or.inr (Multiset.mem_of_mem_erase h)

lemma mem_choices {s : Multiset Cat} {c : Cat} : c ∈ choices s ↔ c ∈ s ∧ 0 < c.1 := by
  simp [choices]

lemma dp_zero_hits (k : ℕ) (s : Multiset Cat) : dp k 0 s = 0 := by
  cases k <;> simp [dp]

@[simp] lemma val_zero (s : Multiset Cat) : val 0 s = 0 := dp_zero_hits _ _

/-- **Bellman equation.** With at least one hit needed and a patchable category, the optimum is
the minimum over the first patch of its continuation value. -/
theorem val_succ (H : ℕ) (s : Multiset Cat) (h : (choices s).Nonempty) :
    val (H + 1) s = (choices s).inf' h (firstPatch (H + 1) s) := by
  obtain ⟨c0, hc0⟩ := id h
  rw [mem_choices] at hc0
  obtain ⟨k, hk⟩ : ∃ k, items s = k + 1 := ⟨items s - 1, by have := fst_le_items hc0.1; omega⟩
  unfold val
  rw [hk, dp, dif_pos h]
  refine Finset.inf'_congr h rfl (fun c hc => ?_)
  rw [mem_choices] at hc
  have e1 : items (hitC c ::ₘ s.erase c) = k := by
    have := items_after hc.1 hc.2 (c.2 - 1); simp only [hitC]; omega
  have e2 : items (missC c ::ₘ s.erase c) = k := by
    have := items_after hc.1 hc.2 c.2; simp only [missC]; omega
  simp only [firstPatch, val, e1, e2, Nat.add_sub_cancel]

lemma val_le_firstPatch (H : ℕ) (s : Multiset Cat) (c : Cat) (hc : c ∈ s) (hpos : 0 < c.1) :
    val (H + 1) s ≤ firstPatch (H + 1) s c := by
  have h : (choices s).Nonempty := ⟨c, mem_choices.2 ⟨hc, hpos⟩⟩
  rw [val_succ H s h]
  exact Finset.inf'_le _ (mem_choices.2 ⟨hc, hpos⟩)

lemma le_val_of_forall (H : ℕ) (s : Multiset Cat) (h : (choices s).Nonempty) (x : ℚ)
    (hx : ∀ c ∈ s, 0 < c.1 → x ≤ firstPatch (H + 1) s c) : x ≤ val (H + 1) s := by
  rw [val_succ H s h]
  exact Finset.le_inf' _ _ fun c hc => hx c (mem_choices.1 hc).1 (mem_choices.1 hc).2

/-- Certificate form of the Bellman equation, used for exact evaluation on concrete states. -/
theorem val_eq_of_cert (H : ℕ) (s : Multiset Cat) (q : ℚ) (c : Cat) (hc : c ∈ s) (hpos : 0 < c.1)
    (heq : firstPatch (H + 1) s c = q) (hle : ∀ d ∈ s, 0 < d.1 → q ≤ firstPatch (H + 1) s d) :
    val (H + 1) s = q :=
  le_antisymm (heq ▸ val_le_firstPatch H s c hc hpos)
    (le_val_of_forall H s ⟨c, mem_choices.2 ⟨hc, hpos⟩⟩ q hle)

lemma rate_nonneg (c : Cat) : 0 ≤ rate c := by
  unfold rate; positivity

lemma rate_le_one {c : Cat} (h : c.2 ≤ c.1) : rate c ≤ 1 := by
  unfold rate
  rcases Nat.eq_zero_or_pos c.1 with h0 | h0
  · simp [h0]
  · rw [div_le_one (by exact_mod_cast h0)]; exact_mod_cast h

lemma rate_eq_one {c : Cat} (h : c.2 = c.1) (hpos : 0 < c.1) : rate c = 1 := by
  unfold rate; rw [h]; exact div_self (by exact_mod_cast hpos.ne')

lemma valid_after_hit {s : Multiset Cat} {c : Cat} (hv : Valid s) (hc : c ∈ s) :
    Valid (hitC c ::ₘ s.erase c) := by
  intro d hd
  rcases mem_after hd with rfl | h
  · have := hv c hc; simp only [hitC]; omega
  · exact hv d h

lemma valid_after_miss {s : Multiset Cat} {c : Cat} (hv : Valid s) (hlt : c.2 < c.1) :
    Valid (missC c ::ₘ s.erase c) := by
  intro d hd
  rcases mem_after hd with rfl | h
  · simp only [missC]; omega
  · exact hv d h

/-! ### Theorem 10: one hit -/

/-- Arithmetic of the induction step (the note's two branches). -/
lemma one_hit_step (n F x : ℚ) (hn : 0 < n) (hF : 1 ≤ F) (hFn : F < n)
    (hx : x ≤ (n + 1) / (F + 1)) : x ≤ 1 + (1 - F / n) * min x (n / (F + 1)) := by
  have hF1 : 0 < F + 1 := by linarith
  rcases le_total x (n / (F + 1)) with h | h
  · rw [min_eq_left h]
    -- `(F / n) x ≤ (F / n) (n / (F + 1)) = F / (F + 1) ≤ 1`
    have hp : 0 ≤ F / n := by positivity
    have h1 : F / n * x ≤ F / n * (n / (F + 1)) := mul_le_mul_of_nonneg_left h hp
    have h2 : F / n * (n / (F + 1)) = F / (F + 1) := by field_simp
    have h3 : F / (F + 1) ≤ 1 := by rw [div_le_one hF1]; linarith
    nlinarith
  · rw [min_eq_right h]
    have : 1 + (1 - F / n) * (n / (F + 1)) = (n + 1) / (F + 1) := by
      field_simp; ring
    linarith

/-- Upper half of Theorem 10: patching any failing category until it hits costs its finisher
value, so the optimum is at most every finisher. -/
theorem val_one_le_finisher : ∀ (k : ℕ) (s : Multiset Cat), items s = k → Valid s →
    ∀ c ∈ s, 1 ≤ c.2 → val 1 s ≤ finisher c := by
  intro k
  induction k with
  | zero =>
    intro s hk hv c hc hF
    have := fst_le_items hc; have := hv c hc; omega
  | succ k ih =>
    intro s hk hv c hc hF
    have hcn := hv c hc
    have hpos : 0 < c.1 := by omega
    refine (val_le_firstPatch 0 s c hc hpos).trans ?_
    obtain ⟨n, F⟩ := c
    simp only at hF hcn hpos
    unfold firstPatch
    simp only [zero_add, Nat.sub_self, val_zero, mul_zero, add_zero, rate_mk, finisher_mk]
    rcases Nat.lt_or_ge F n with hlt | hge
    · -- a miss leaves `(n - 1, F)` with `F ≥ 1`; its finisher is `n / (F + 1)`
      have hv' := valid_after_miss (c := (n, F)) hv hlt
      have hk' : items (missC (n, F) ::ₘ s.erase (n, F)) = k := by
        have := items_after hc hpos F; dsimp only at this; simp only [missC_mk]; omega
      have hih := ih _ hk' hv' (missC (n, F)) (Multiset.mem_cons_self _ _)
        (by simp only [missC_mk]; omega)
      have hfin : finisher (missC (n, F)) = (n : ℚ) / ((F : ℚ) + 1) := by
        simp only [missC_mk, finisher_mk]
        rw [Nat.cast_sub (by omega)]; push_cast; ring
      rw [hfin] at hih
      have hq : (0 : ℚ) ≤ 1 - (F : ℚ) / n := by
        have := rate_le_one (c := (n, F)) (by simpa using hcn); simp at this; linarith
      have hnq : (0 : ℚ) < n := by exact_mod_cast hpos
      calc 1 + (1 - (F : ℚ) / n) * val 1 (missC (n, F) ::ₘ s.erase (n, F))
          ≤ 1 + (1 - (F : ℚ) / n) * ((n : ℚ) / ((F : ℚ) + 1)) := by gcongr
        _ = ((n : ℚ) + 1) / ((F : ℚ) + 1) := by field_simp; ring
    · have hFn : F = n := le_antisymm hcn hge
      subst hFn
      have hnq : (F : ℚ) ≠ 0 := by exact_mod_cast hpos.ne'
      rw [div_self hnq, div_self (by positivity)]
      ring_nf; rfl

/-- Lower half of Theorem 10, the note's induction: any `x` below every finisher is below the
optimum. -/
theorem le_val_one : ∀ (k : ℕ) (s : Multiset Cat), items s = k → Valid s → (∃ c ∈ s, 1 ≤ c.2) →
    ∀ x : ℚ, (∀ c ∈ s, 1 ≤ c.2 → x ≤ finisher c) → x ≤ val 1 s := by
  intro k
  induction k with
  | zero =>
    intro s hk hv ⟨c, hc, hF⟩
    have := fst_le_items hc; have := hv c hc; omega
  | succ k ih =>
    intro s hk hv ⟨c0, hc0, hF0⟩ x hx
    have hpos0 : 0 < c0.1 := by have := hv c0 hc0; omega
    refine le_val_of_forall 0 s ⟨c0, mem_choices.2 ⟨hc0, hpos0⟩⟩ x ?_
    intro c hc hpos
    have hcn := hv c hc
    have hk' : items (missC c ::ₘ s.erase c) = k := by
      have := items_after hc hpos c.2; unfold missC; omega
    unfold firstPatch
    simp only [zero_add, Nat.sub_self, val_zero, mul_zero, add_zero]
    rcases Nat.lt_or_ge c.2 c.1 with hlt | hge
    · have hv' := valid_after_miss hv hlt
      have hq : (0 : ℚ) ≤ 1 - rate c := by have := rate_le_one hcn; linarith
      rcases Nat.eq_zero_or_pos c.2 with h0 | h1
      · -- a category with no failure: the miss changes nothing that matters
        have hex : ∃ d ∈ missC c ::ₘ s.erase c, 1 ≤ d.2 := by
          refine ⟨c0, Multiset.mem_cons_of_mem ?_, hF0⟩
          exact (Multiset.mem_erase_of_ne (by rintro rfl; omega)).2 hc0
        have hx' : ∀ d ∈ missC c ::ₘ s.erase c, 1 ≤ d.2 → x ≤ finisher d := by
          intro d hd hdF
          rcases mem_after hd with rfl | h
          · simp only [missC] at hdF; omega
          · exact hx d h hdF
        have := ih _ hk' hv' hex x hx'
        have hr : rate c = 0 := by simp [rate, h0]
        rw [hr]; linarith
      · -- the note's case: `y = min x (n / (F + 1))` is below every finisher after the miss
        obtain ⟨n, F⟩ := c
        simp only at hlt h1 hpos hcn
        set y := min x ((n : ℚ) / ((F : ℚ) + 1)) with hy
        have hex : ∃ d ∈ missC (n, F) ::ₘ s.erase (n, F), 1 ≤ d.2 :=
          ⟨missC (n, F), Multiset.mem_cons_self _ _, by simp only [missC_mk]; omega⟩
        have hy' : ∀ d ∈ missC (n, F) ::ₘ s.erase (n, F), 1 ≤ d.2 → y ≤ finisher d := by
          intro d hd hdF
          rcases mem_after hd with rfl | h
          · simp only [missC_mk, finisher_mk]
            rw [Nat.cast_sub (by omega)]; push_cast
            simp only [sub_add_cancel]
            exact min_le_right _ _
          · exact (min_le_left _ _).trans (hx d h hdF)
        have hih := ih _ hk' hv' hex y hy'
        have hstep := one_hit_step n F x (by exact_mod_cast hpos) (by exact_mod_cast h1)
          (by exact_mod_cast hlt) (by simpa using hx (n, F) hc h1)
        rw [← hy] at hstep
        simp only [rate_mk] at hq ⊢
        calc x ≤ 1 + (1 - (F : ℚ) / n) * y := hstep
          _ ≤ 1 + (1 - (F : ℚ) / n) * val 1 (missC (n, F) ::ₘ s.erase (n, F)) := by gcongr
    · -- `F = n`: the patch hits for sure, cost `1 = (n + 1) / (n + 1)`
      have hFn : c.2 = c.1 := le_antisymm hcn hge
      have hr := rate_eq_one hFn hpos
      rw [hr]
      have := hx c hc (by omega)
      simp only [finisher, hFn] at this
      rw [div_self (by positivity)] at this
      linarith

/-- **Theorem 10 (one hit, closed form).** For a valid state with at least one failing category,
the optimal expected number of patches to one hit is the least `(n_c + 1) / (F_c + 1)` over the
categories with `F_c ≥ 1`. -/
theorem theorem10 (s : Multiset Cat) (hv : Valid s) (hF : ∃ c ∈ s, 1 ≤ c.2) :
    IsLeast {x | ∃ c ∈ s, 1 ≤ c.2 ∧ x = finisher c} (val 1 s) := by
  set T := s.toFinset.filter (fun c => 1 ≤ c.2) with hT
  have hTne : T.Nonempty := by
    obtain ⟨c, hc, hc1⟩ := hF; exact ⟨c, by simp [hT, hc, hc1]⟩
  obtain ⟨c, hcT, hceq⟩ := Finset.exists_mem_eq_inf' hTne finisher
  have hcs : c ∈ s ∧ 1 ≤ c.2 := by simpa [hT] using hcT
  have hmin : ∀ d ∈ s, 1 ≤ d.2 → finisher c ≤ finisher d := by
    intro d hd hd1
    rw [← hceq]; exact Finset.inf'_le _ (by simp [hT, hd, hd1])
  refine ⟨⟨c, hcs.1, hcs.2, ?_⟩, ?_⟩
  · exact le_antisymm (val_one_le_finisher _ s rfl hv c hcs.1 hcs.2)
      (le_val_one _ s rfl hv hF _ hmin)
  · rintro x ⟨d, hd, hd1, rfl⟩
    exact val_one_le_finisher _ s rfl hv d hd hd1

/-- Theorem 10 in evaluation form: a category of least finisher value gives the optimum. -/
theorem val_one_eq (s : Multiset Cat) (hv : Valid s) (c : Cat) (hc : c ∈ s) (hc1 : 1 ≤ c.2)
    (hmin : ∀ d ∈ s, 1 ≤ d.2 → finisher c ≤ finisher d) : val 1 s = finisher c :=
  le_antisymm (val_one_le_finisher _ s rfl hv c hc hc1) (le_val_one _ s rfl hv ⟨c, hc, hc1⟩ _ hmin)

/-- Expected patches when the loop patches category `(n, F)` until it hits and never switches:
`stick (n + 1) F = 1 + (1 - F / (n + 1)) * stick n F` (a miss leaves `n` items, `F` failures). -/
def stick : ℕ → ℕ → ℚ
  | 0, _ => 0
  | n + 1, F => 1 + (1 - (F : ℚ) / (n + 1)) * stick n F

/-- Sticking with a category costs its finisher value (the note's identity
`1 + (1 - F/n) n/(F+1) = (n+1)/(F+1)`, iterated). -/
theorem stick_eq : ∀ (n F : ℕ), 1 ≤ F → F ≤ n → stick n F = ((n : ℚ) + 1) / ((F : ℚ) + 1) := by
  intro n
  induction n with
  | zero => intro F h1 h2; omega
  | succ n ih =>
    intro F h1 h2
    simp only [stick]
    rcases Nat.lt_or_ge F (n + 1) with hlt | hge
    · rw [ih F h1 (by omega)]
      push_cast
      field_simp
      ring
    · have hF : F = n + 1 := le_antisymm h2 hge
      subst hF
      push_cast
      rw [div_self (by positivity)]
      simp only [sub_self, zero_mul, add_zero]
      rw [div_self (by positivity)]

/-- **Theorem 10, attainment.** Let `c` be a best finisher of a valid state. Then (i) patching `c`
first is optimal; (ii) after a miss in `c` the remaining `(n - 1, F)` is a best finisher of the new
state, so continuing with it is again optimal (the policy never switches); (iii) the never-switching
policy costs `stick n F = (n + 1) / (F + 1)`, the optimum. -/
theorem theorem10_attained (s : Multiset Cat) (hv : Valid s) (c : Cat) (hc : c ∈ s) (hc1 : 1 ≤ c.2)
    (hbest : finisher c = val 1 s) :
    firstPatch 1 s c = val 1 s ∧
    (c.2 < c.1 → finisher (missC c) = val 1 (missC c ::ₘ s.erase c)) ∧
    stick c.1 c.2 = val 1 s := by
  have hcn := hv c hc
  have hpos : 0 < c.1 := by omega
  have hmin : ∀ d ∈ s, 1 ≤ d.2 → finisher c ≤ finisher d := by
    intro d hd hd1; rw [hbest]; exact val_one_le_finisher _ s rfl hv d hd hd1
  -- after a miss, `missC c` is a best finisher
  have hmiss : c.2 < c.1 → finisher (missC c) = val 1 (missC c ::ₘ s.erase c) := by
    intro hlt
    have hv' := valid_after_miss hv hlt
    have hlt' : finisher (missC c) < finisher c := by
      obtain ⟨n, F⟩ := c
      simp only at hlt hpos
      simp only [missC_mk, finisher_mk]
      rw [Nat.cast_sub (by omega)]; push_cast
      apply div_lt_div_of_pos_right _ (by positivity); linarith
    symm
    apply val_one_eq _ hv' _ (Multiset.mem_cons_self _ _) (by simpa [missC] using hc1)
    intro d hd hd1
    rcases mem_after hd with rfl | h
    · exact le_rfl
    · exact hlt'.le.trans (hmin d h hd1)
  refine ⟨?_, hmiss, ?_⟩
  · apply le_antisymm _ (val_le_firstPatch 0 s c hc hpos)
    unfold firstPatch
    simp only [zero_add, Nat.sub_self, val_zero, mul_zero, add_zero]
    rcases Nat.lt_or_ge c.2 c.1 with hlt | hge
    · rw [← hmiss hlt, ← hbest]
      obtain ⟨n, F⟩ := c
      simp only at hlt hpos hc1
      simp only [missC_mk, finisher_mk, rate_mk]
      rw [Nat.cast_sub (by omega)]; push_cast
      have : (n : ℚ) ≠ 0 := by exact_mod_cast hpos.ne'
      apply le_of_eq
      field_simp
      ring
    · have hFn : c.2 = c.1 := le_antisymm hcn hge
      rw [rate_eq_one hFn hpos, ← hbest]
      simp only [finisher, hFn]
      rw [div_self (by positivity)]
      ring_nf; rfl
  · rw [stick_eq _ _ hc1 hcn, ← hbest]; rfl

/-- The one-hit witness of the note: in `{(2,1), (16,9)}` the rates are `1/2 < 9/16` but patching
`(2,1)` first costs `3/2`, the optimum, and patching the higher-rate `(16,9)` first costs `53/32`. -/
theorem one_hit_rate_witness :
    rate (2, 1) < rate (16, 9) ∧
    val 1 {(2, 1), (16, 9)} = 3 / 2 ∧
    firstPatch 1 {(2, 1), (16, 9)} (2, 1) = 3 / 2 ∧
    firstPatch 1 {(2, 1), (16, 9)} (16, 9) = 53 / 32 := by
  have hv : Valid {(2, 1), (16, 9)} := by decide
  have h0 : val 1 {(2, 1), (16, 9)} = 3 / 2 := by
    rw [val_one_eq _ hv (2, 1) (by decide) (by decide)]
    · norm_num
    · intro d hd _
      simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
      rcases hd with rfl | rfl <;> norm_num
  have e1 : missC (16, 9) ::ₘ ({(2, 1), (16, 9)} : Multiset Cat).erase (16, 9) = {(15, 9), (2, 1)} := by
    decide
  have hv1 : Valid {(15, 9), (2, 1)} := by decide
  have h1 : val 1 {(15, 9), (2, 1)} = 3 / 2 := by
    rw [val_one_eq _ hv1 (2, 1) (by decide) (by decide)]
    · norm_num
    · intro d hd _
      simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
      rcases hd with rfl | rfl <;> norm_num
  have e2 : missC (2, 1) ::ₘ ({(2, 1), (16, 9)} : Multiset Cat).erase (2, 1) = {(1, 1), (16, 9)} := by
    decide
  have hv2 : Valid {(1, 1), (16, 9)} := by decide
  have h2 : val 1 {(1, 1), (16, 9)} = 1 := by
    rw [val_one_eq _ hv2 (1, 1) (by decide) (by decide)]
    · norm_num
    · intro d hd _
      simp only [Multiset.insert_eq_cons, Multiset.mem_cons, Multiset.mem_singleton] at hd
      rcases hd with rfl | rfl <;> norm_num
  refine ⟨by norm_num, h0, ?_, ?_⟩
  · rw [firstPatch, e2, h2]; norm_num
  · rw [firstPatch, e1, h1]; norm_num

/-! ### Proposition 4, one category: the negative-hypergeometric mean -/

/-- **Proposition 4, one category.** With a single category of `n` items, `F` of them failing, the
expected number of patches to the `H`-th hit (`H ≤ F`) is `H (n + 1) / (F + 1)`. With one category
the programme has one choice per step, so `val` is the expected stopping time of patching uniformly
at random without replacement. -/
theorem val_single : ∀ (n H F : ℕ), H ≤ F → F ≤ n →
    val H {(n, F)} = (H : ℚ) * ((n : ℚ) + 1) / ((F : ℚ) + 1) := by
  intro n
  induction n with
  | zero =>
    intro H F h1 h2
    have hF : F = 0 := by omega
    have hH : H = 0 := by omega
    subst hF; subst hH; simp
  | succ n ih =>
    intro H F h1 h2
    rcases H with _ | h
    · simp
    obtain ⟨G, rfl⟩ : ∃ G, F = G + 1 := ⟨F - 1, by omega⟩
    have hs : ({(n + 1, G + 1)} : Multiset Cat).erase (n + 1, G + 1) = 0 :=
      Multiset.erase_singleton _
    have hfp : firstPatch (h + 1) {(n + 1, G + 1)} (n + 1, G + 1) =
        ((h + 1 : ℕ) : ℚ) * (((n + 1 : ℕ) : ℚ) + 1) / (((G + 1 : ℕ) : ℚ) + 1) := by
      unfold firstPatch
      rw [hs, Multiset.cons_zero, Multiset.cons_zero]
      simp only [hitC_mk, missC_mk, rate_mk, Nat.add_sub_cancel]
      rw [ih h G (by omega) (by omega)]
      rcases Nat.lt_or_ge G n with hlt | hge
      · rw [ih (h + 1) (G + 1) (by omega) (by omega)]
        push_cast
        field_simp
        ring
      · have hG : G = n := by omega
        subst hG
        push_cast
        rw [div_self (by positivity)]
        field_simp
        ring
    exact val_eq_of_cert h _ _ (n + 1, G + 1) (Multiset.mem_singleton_self _) (by simp) hfp
      (fun d hd _ => by rw [Multiset.mem_singleton.1 hd, hfp])

/-! ### Lemma 9: pair commutation -/

/-- Expected patches when the first patch goes to `A`, the second to `B`, and every later patch is
optimal (`two_patch_value` in the Python module). Meant for `H ≥ 2`, so the run cannot stop before
the second patch. -/
def twoPatch (H : ℕ) (s : Multiset Cat) (A B : Cat) : ℚ :=
  rate A * (1 + firstPatch (H - 1) (hitC A ::ₘ s.erase A) B) +
    (1 - rate A) * (1 + firstPatch H (missC A ::ₘ s.erase A) B)

lemma erase_cons_of_mem {t : Multiset Cat} {B : Cat} (x : Cat) (hB : B ∈ t) :
    (x ::ₘ t).erase B = x ::ₘ t.erase B := by
  by_cases hx : x = B
  · subst hx; rw [Multiset.erase_cons_head, Multiset.cons_erase hB]
  · exact Multiset.erase_cons_tail_of_mem hB

/-- **Lemma 9 (pair commutation).** With at least two hits needed, patching category `A` and then a
different category `B`, each followed by optimal play, costs the same in expectation as `B` then
`A`. -/
theorem lemma9 (H : ℕ) (hH : 2 ≤ H) (s : Multiset Cat) (A B : Cat) (hA : A ∈ s) (hB : B ∈ s)
    (hAB : A ≠ B) : twoPatch H s A B = twoPatch H s B A := by
  have hB' : B ∈ s.erase A := (Multiset.mem_erase_of_ne hAB.symm).2 hB
  have hA' : A ∈ s.erase B := (Multiset.mem_erase_of_ne hAB).2 hA
  unfold twoPatch firstPatch
  rw [erase_cons_of_mem (hitC A) hB', erase_cons_of_mem (missC A) hB',
    erase_cons_of_mem (hitC B) hA', erase_cons_of_mem (missC B) hA']
  have hc : (s.erase B).erase A = (s.erase A).erase B := Multiset.erase_comm _ _ _
  rw [hc, Multiset.cons_swap (hitC A) (hitC B), Multiset.cons_swap (hitC A) (missC B),
    Multiset.cons_swap (missC A) (hitC B), Multiset.cons_swap (missC A) (missC B)]
  ring

/-! ### Policies -/

/-- A stationary policy: given the hits still needed and the state, the category it patches. -/
abbrev Policy := ℕ → Multiset Cat → Cat

/-- Expected patches of a policy (policy evaluation, same fuel convention as `dp`). -/
def pdp (π : Policy) : ℕ → ℕ → Multiset Cat → ℚ
  | 0, _, _ => 0
  | _ + 1, 0, _ => 0
  | k + 1, H + 1, s =>
    1 + rate (π (H + 1) s) * pdp π k H (hitC (π (H + 1) s) ::ₘ s.erase (π (H + 1) s)) +
      (1 - rate (π (H + 1) s)) * pdp π k (H + 1) (missC (π (H + 1) s) ::ₘ s.erase (π (H + 1) s))

/-- Expected number of patches to `H` hits when following `π` from `s`. -/
def pval (π : Policy) (H : ℕ) (s : Multiset Cat) : ℚ := pdp π (items s) H s

/-- A policy is legal when, wherever a patch is possible, it patches a category of the state that
has an unpatched item. -/
def Legal (π : Policy) : Prop := ∀ H s, (choices s).Nonempty → π H s ∈ s ∧ 0 < (π H s).1

lemma choices_nonempty_of_items {s : Multiset Cat} (h : 0 < items s) : (choices s).Nonempty := by
  by_contra hne
  have : items s = 0 := by
    unfold items
    apply Multiset.sum_eq_zero
    intro x hx
    obtain ⟨c, hc, rfl⟩ := Multiset.mem_map.1 hx
    by_contra hc0
    exact hne ⟨c, mem_choices.2 ⟨hc, Nat.pos_of_ne_zero hc0⟩⟩
  omega

lemma pval_succ (π : Policy) (hπ : Legal π) (H : ℕ) (s : Multiset Cat) (h : 0 < items s) :
    pval π (H + 1) s = 1 + rate (π (H + 1) s) * pval π H (hitC (π (H + 1) s) ::ₘ s.erase (π (H + 1) s)) +
      (1 - rate (π (H + 1) s)) * pval π (H + 1) (missC (π (H + 1) s) ::ₘ s.erase (π (H + 1) s)) := by
  obtain ⟨hc, hpos⟩ := hπ (H + 1) s (choices_nonempty_of_items h)
  obtain ⟨k, hk⟩ : ∃ k, items s = k + 1 := ⟨items s - 1, by omega⟩
  have e1 : items (hitC (π (H + 1) s) ::ₘ s.erase (π (H + 1) s)) = k := by
    have := items_after hc hpos ((π (H + 1) s).2 - 1); unfold hitC; omega
  have e2 : items (missC (π (H + 1) s) ::ₘ s.erase (π (H + 1) s)) = k := by
    have := items_after hc hpos (π (H + 1) s).2; unfold missC; omega
  unfold pval
  rw [hk, e1, e2]
  rfl

/-- No legal policy beats the programme, and following `π` costs at least the continuation value
of its own first patch. -/
theorem val_le_pval (π : Policy) (hπ : Legal π) : ∀ (k : ℕ) (H : ℕ) (s : Multiset Cat),
    items s = k → Valid s → val H s ≤ pval π H s ∧
      (0 < H → 0 < items s → firstPatch H s (π H s) ≤ pval π H s) := by
  intro k
  induction k with
  | zero =>
    intro H s hk _
    refine ⟨?_, fun _ h => by omega⟩
    unfold val pval; rw [hk]; simp [dp, pdp]
  | succ k ih =>
    intro H s hk hv
    rcases H with _ | H
    · refine ⟨?_, fun h => by omega⟩
      simp only [val_zero]; unfold pval; rw [hk]; simp [pdp]
    have hpos' : 0 < items s := by omega
    obtain ⟨hc, hpos⟩ := hπ (H + 1) s (choices_nonempty_of_items hpos')
    set c := π (H + 1) s with hcdef
    have hfp : firstPatch (H + 1) s c ≤ pval π (H + 1) s := by
      rw [pval_succ π hπ H s hpos', ← hcdef]
      unfold firstPatch
      simp only [Nat.add_sub_cancel]
      have hk1 : items (hitC c ::ₘ s.erase c) = k := by
        have := items_after hc hpos (c.2 - 1); unfold hitC; omega
      have hk2 : items (missC c ::ₘ s.erase c) = k := by
        have := items_after hc hpos c.2; unfold missC; omega
      have h1 := (ih H _ hk1 (valid_after_hit hv hc)).1
      have hr0 := rate_nonneg c
      have hr1 := rate_le_one (hv c hc)
      rcases Nat.lt_or_ge c.2 c.1 with hlt | hge
      · have h2 := (ih (H + 1) _ hk2 (valid_after_miss hv hlt)).1
        have hq : 0 ≤ 1 - rate c := by linarith
        have := mul_le_mul_of_nonneg_left h1 hr0
        have := mul_le_mul_of_nonneg_left h2 hq
        linarith
      · have hr : rate c = 1 := rate_eq_one (le_antisymm (hv c hc) hge) hpos
        rw [hr]
        have := h1
        linarith
    exact ⟨(val_le_firstPatch H s c hc hpos).trans hfp, fun _ _ => hfp⟩

end FeedbackChannel.PatchDP

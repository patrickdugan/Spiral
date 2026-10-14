import Mathlib.Tactic
import Mathlib.Combinatorics.SimpleGraph.Acyclic
import Mathlib.Data.Setoid.Basic

/-!
# Proposition 2c: two category leaks reveal the joint leak iff the intersection graph is a forest

Source: `paper/evaluation_feedback_lattice.md` (version 0.6), §2, Proposition 2c; Python
`intersection_graph`, `intersection_graph_is_forest`, `join_failure_witness`.

Category maps are labelings `γ : ι → R`, `γ' : ι → C` of the items (blocks = nonempty fibres;
unused labels are isolated vertices and change nothing). A record is `r : ι → Bool` (`true` =
pass). `Φ(γ)` reveals the per-block pass counts; the channel that observes both leaks identifies
records with equal row *and* column counts; `Φ(γ ∨ γ')` reveals the pass count of every cell
`γ⁻¹ a ∩ γ'⁻¹ b`. The intersection graph `I(γ, γ')` is the bipartite graph on `R ⊕ C` with an edge
`a — b` when the cell is nonempty, as a Mathlib `SimpleGraph`, and *acyclic* is Mathlib's
`SimpleGraph.IsAcyclic`.

The combinatorial core (`margins_determine_iff_acyclic`): on the box `0 ≤ w ≤ cap` of cell
weights, row and column margins determine the weights iff the bipartite graph of positive-capacity
cells is acyclic. Forest direction: a cut argument across a bridge (every edge of a forest is
one). Cycle direction: an alternating `±1` weight along a path closing a non-bridge edge.
-/

namespace FeedbackChannel.LatticeJoin

open SimpleGraph Finset

variable {R C : Type*} [Fintype R] [Fintype C] [DecidableEq R] [DecidableEq C]

/-- The bipartite graph on `R ⊕ C` with an edge `inl a — inr b` exactly when `E a b`. -/
def bip (E : R → C → Prop) : SimpleGraph (R ⊕ C) :=
  SimpleGraph.fromRel fun u v => ∃ a b, u = Sum.inl a ∧ v = Sum.inr b ∧ E a b

section Core

variable {E : R → C → Prop}

@[simp] lemma bip_inl_inr (a : R) (b : C) : (bip E).Adj (Sum.inl a) (Sum.inr b) ↔ E a b := by
  simp [bip]

@[simp] lemma bip_inr_inl (a : R) (b : C) : (bip E).Adj (Sum.inr b) (Sum.inl a) ↔ E a b := by
  simp [bip]

@[simp] lemma bip_inl_inl (a a' : R) : ¬ (bip E).Adj (Sum.inl a) (Sum.inl a') := by
  simp [bip]

@[simp] lemma bip_inr_inr (b b' : C) : ¬ (bip E).Adj (Sum.inr b) (Sum.inr b') := by
  simp [bip]

lemma bip_congr {E E' : R → C → Prop} (h : ∀ a b, E a b ↔ E' a b) : bip E = bip E' := by
  ext u v
  simp only [bip, fromRel_adj, h]

/-- Row margin of an integer cell weight. -/
def rowM (w : R → C → ℤ) (a : R) : ℤ := ∑ b, w a b

/-- Column margin of an integer cell weight. -/
def colM (w : R → C → ℤ) (b : C) : ℤ := ∑ a, w a b

/-- **Forest direction.** If the graph is acyclic, a weight supported on its edges with all row
and column margins zero is zero. -/
theorem acyclic_margins_zero (hG : (bip E).IsAcyclic) (d : R → C → ℤ)
    (hsupp : ∀ a b, ¬ E a b → d a b = 0) (hrow : ∀ a, rowM d a = 0) (hcol : ∀ b, colM d b = 0) :
    d = 0 := by
  classical
  funext a b
  show d a b = 0
  by_cases hab : E a b
  swap
  · exact hsupp a b hab
  have hbr := isAcyclic_iff_forall_adj_isBridge.1 hG ((bip_inl_inr a b).2 hab)
  rw [isBridge_iff] at hbr
  set G' := (bip E).deleteEdges {s(Sum.inl a, Sum.inr b)} with hG'
  let ind : R ⊕ C → ℤ := fun v => if G'.Reachable (Sum.inl a) v then 1 else 0
  have hcell : ∀ x y, d x y * (ind (Sum.inl x) - ind (Sum.inr y)) =
      if x = a ∧ y = b then d a b else 0 := by
    intro x y
    by_cases hxy : x = a ∧ y = b
    · obtain ⟨rfl, rfl⟩ := hxy
      simp [ind, hbr, Reachable.refl]
    · rw [if_neg hxy]
      by_cases hE : E x y
      · have hadj : G'.Adj (Sum.inl x) (Sum.inr y) := by
          rw [hG', deleteEdges_adj]
          refine ⟨(bip_inl_inr x y).2 hE, ?_⟩
          simp only [Set.mem_singleton_iff, Sym2.eq_iff, Sum.inl.injEq, Sum.inr.injEq,
            reduceCtorEq, and_false, or_false]
          exact hxy
        have hiff : G'.Reachable (Sum.inl a) (Sum.inl x) ↔ G'.Reachable (Sum.inl a) (Sum.inr y) :=
          ⟨fun h => h.trans hadj.reachable, fun h => h.trans hadj.symm.reachable⟩
        simp only [ind, hiff, sub_self, mul_zero]
      · rw [hsupp x y hE, zero_mul]
  have hsum : ∑ x, ∑ y, d x y * (ind (Sum.inl x) - ind (Sum.inr y)) = d a b := by
    simp_rw [hcell, ite_and]
    simp
  have hzero : ∑ x, ∑ y, d x y * (ind (Sum.inl x) - ind (Sum.inr y)) = 0 := by
    have h1 : ∑ x, ∑ y, d x y * ind (Sum.inl x) = ∑ x, rowM d x * ind (Sum.inl x) := by
      refine Finset.sum_congr rfl fun x _ => ?_
      rw [rowM, Finset.sum_mul]
    have h2 : ∑ x, ∑ y, d x y * ind (Sum.inr y) = ∑ y, colM d y * ind (Sum.inr y) := by
      rw [Finset.sum_comm]
      refine Finset.sum_congr rfl fun y _ => ?_
      rw [colM, Finset.sum_mul]
    simp only [mul_sub, Finset.sum_sub_distrib, h1, h2, hrow, hcol, zero_mul,
      Finset.sum_const_zero, sub_zero]
  rw [← hsum, hzero]

/-- Weight `1` on the cell of the edge `u — v` (zero unless `{u, v} = {inl x, inr y}`). -/
def eW (u v : R ⊕ C) (x : R) (y : C) : ℤ :=
  if (u = Sum.inl x ∧ v = Sum.inr y) ∨ (u = Sum.inr y ∧ v = Sum.inl x) then 1 else 0

/-- Alternating `±1` weight along a walk: first edge `+1`, second `-1`, and so on. -/
def wW {G : SimpleGraph (R ⊕ C)} : {u v : R ⊕ C} → G.Walk u v → R → C → ℤ
  | _, _, .nil => 0
  | u, _, .cons (v := w) _ p => eW u w - wW p

/-- Margin at a vertex: row margin at `inl a`, column margin at `inr b`. -/
def vm (w : R → C → ℤ) : R ⊕ C → ℤ
  | Sum.inl a => rowM w a
  | Sum.inr b => colM w b

lemma vm_sub (f g : R → C → ℤ) (z : R ⊕ C) : vm (f - g) z = vm f z - vm g z := by
  cases z <;> simp [vm, rowM, colM, Finset.sum_sub_distrib]

lemma vm_zero (z : R ⊕ C) : vm (0 : R → C → ℤ) z = 0 := by
  cases z <;> simp [vm, rowM, colM]

/-- Indicator of a vertex. -/
def ind (z u : R ⊕ C) : ℤ := if z = u then 1 else 0

lemma eW_inl_inr (a : R) (b : C) (x : R) (y : C) :
    eW (Sum.inl a) (Sum.inr b) x y = if a = x ∧ b = y then 1 else 0 := by
  simp [eW]

lemma eW_symm (u v : R ⊕ C) : eW u v = eW v u := by
  funext x y; unfold eW; congr 1; apply propext; tauto

lemma vm_eW_inl_inr (a : R) (b : C) (z : R ⊕ C) :
    vm (eW (Sum.inl a) (Sum.inr b)) z = ind z (Sum.inl a) + ind z (Sum.inr b) := by
  cases z with
  | inl x =>
    simp only [vm, rowM, eW_inl_inr, ind, Sum.inl.injEq, reduceCtorEq, if_false, add_zero]
    by_cases hx : x = a
    · subst hx; simp
    · simp [hx, Ne.symm hx]
  | inr y =>
    simp only [vm, colM, eW_inl_inr, ind, Sum.inr.injEq, reduceCtorEq, if_false, zero_add]
    by_cases hy : y = b
    · subst hy; simp
    · simp [hy, Ne.symm hy]

lemma vm_eW {u v : R ⊕ C} (h : (bip E).Adj u v) (z : R ⊕ C) : vm (eW u v) z = ind z u + ind z v := by
  rcases u with a | b <;> rcases v with a' | b'
  · exact absurd h (bip_inl_inl a a')
  · exact vm_eW_inl_inr a b' z
  · rw [eW_symm, vm_eW_inl_inr, add_comm]
  · exact absurd h (bip_inr_inr b b')

/-- Side of a vertex, `1` for rows and `-1` for columns. -/
def side : R ⊕ C → ℤ
  | Sum.inl _ => 1
  | Sum.inr _ => -1

lemma side_adj {u v : R ⊕ C} (h : (bip E).Adj u v) : side u = - side v := by
  rcases u with a | b <;> rcases v with a' | b'
  · exact absurd h (bip_inl_inl a a')
  · simp [side]
  · simp [side]
  · exact absurd h (bip_inr_inr b b')

lemma side_sq (u : R ⊕ C) : side u * side u = 1 := by
  cases u <;> simp [side]

variable {G : SimpleGraph (R ⊕ C)}

/-- A walk in a subgraph of a bipartite graph changes side at every step. -/
lemma walk_parity (hGle : G ≤ bip E) {u v : R ⊕ C} (p : G.Walk u v) :
    (-1 : ℤ) ^ p.length = side u * side v := by
  induction p with
  | nil => simp [side_sq]
  | cons h p ih =>
    rw [Walk.length_cons, pow_succ, ih, side_adj (hGle h)]
    ring

/-- The margins of the alternating weight of a walk from `u` to `v` are `δ_u - (-1)^len δ_v`. -/
lemma vm_wW (hGle : G ≤ bip E) {u v : R ⊕ C} (p : G.Walk u v) (z : R ⊕ C) :
    vm (wW p) z = ind z u - (-1 : ℤ) ^ p.length * ind z v := by
  induction p with
  | nil => simp [wW, vm_zero]
  | cons h p ih =>
    simp only [wW, vm_sub, vm_eW (hGle h), ih, Walk.length_cons, pow_succ]
    ring

lemma eW_ne_zero {u v : R ⊕ C} {x : R} {y : C} (h : eW u v x y ≠ 0) :
    s(u, v) = s(Sum.inl x, Sum.inr y) := by
  unfold eW at h
  split_ifs at h with hc
  · rcases hc with ⟨rfl, rfl⟩ | ⟨rfl, rfl⟩
    · rfl
    · exact Sym2.eq_swap
  · exact absurd rfl h

lemma eW_values (u v : R ⊕ C) (x : R) (y : C) : eW u v x y = 0 ∨ eW u v x y = 1 := by
  unfold eW; split_ifs <;> simp

/-- The alternating weight lives on the walk's edges. -/
lemma wW_supp {u v : R ⊕ C} (p : G.Walk u v) (x : R) (y : C) (h : wW p x y ≠ 0) :
    s(Sum.inl x, Sum.inr y) ∈ p.edges := by
  induction p with
  | nil => exact absurd rfl h
  | @cons u' w' v' h' p ih =>
    rw [Walk.edges_cons, List.mem_cons]
    simp only [wW, Pi.sub_apply] at h
    by_cases he : eW u' w' x y = 0
    · rw [he, zero_sub, neg_ne_zero] at h
      exact Or.inr (ih h)
    · exact Or.inl (eW_ne_zero he).symm

/-- On a trail the alternating weight takes values in `{0, 1, -1}`. -/
lemma wW_trail {u v : R ⊕ C} (p : G.Walk u v) (hp : p.IsTrail) (x : R) (y : C) :
    wW p x y = 0 ∨ wW p x y = 1 ∨ wW p x y = -1 := by
  induction p with
  | nil => simp [wW]
  | @cons u' w' v' h' p ih =>
    rw [Walk.isTrail_cons] at hp
    simp only [wW, Pi.sub_apply]
    rcases eW_values u' w' x y with he | he
    · rw [he, zero_sub]
      rcases ih hp.1 with h | h | h <;> simp [h]
    · have hmem := eW_ne_zero (show eW u' w' x y ≠ 0 by rw [he]; norm_num)
      have h0 : wW p x y = 0 := by
        by_contra hne
        exact hp.2 (hmem ▸ wW_supp p x y hne)
      rw [he, h0]; simp

/-- A graph that is not acyclic has a non-bridge edge `inl a — inr b`. -/
lemma exists_nonbridge (h : ¬ (bip E).IsAcyclic) :
    ∃ a b, E a b ∧ ((bip E).deleteEdges {s(Sum.inl a, Sum.inr b)}).Reachable (Sum.inl a) (Sum.inr b) := by
  rw [isAcyclic_iff_forall_adj_isBridge] at h
  push Not at h
  obtain ⟨v, w, hadj, hnb⟩ := h
  rw [isBridge_iff, not_not] at hnb
  rcases v with a | b <;> rcases w with a' | b'
  · exact absurd hadj (bip_inl_inl a a')
  · exact ⟨a, b', (bip_inl_inr a b').1 hadj, hnb⟩
  · refine ⟨a', b, (bip_inr_inl a' b).1 hadj, ?_⟩
    rw [Sym2.eq_swap]; exact hnb.symm
  · exact absurd hadj (bip_inr_inr b b')

/-- **Cycle direction.** If the graph is not acyclic, there is a nonzero weight with values in
`{0, 1, -1}`, supported on the edges, with every row and column margin zero. -/
theorem not_acyclic_witness (h : ¬ (bip E).IsAcyclic) :
    ∃ d : R → C → ℤ, d ≠ 0 ∧ (∀ a b, ¬ E a b → d a b = 0) ∧
      (∀ a b, d a b = 0 ∨ d a b = 1 ∨ d a b = -1) ∧ (∀ a, rowM d a = 0) ∧ (∀ b, colM d b = 0) := by
  classical
  obtain ⟨a, b, hab, hreach⟩ := exists_nonbridge h
  set G' := (bip E).deleteEdges {s(Sum.inl a, Sum.inr b)} with hG'
  have hle : G' ≤ bip E := deleteEdges_le _
  obtain ⟨p⟩ := hreach
  set q := p.bypass with hq
  have hqt : q.IsTrail := (Walk.bypass_isPath p).isTrail
  have hqE : ∀ e ∈ q.edges, e ∈ G'.edgeSet := fun e he => q.edges_subset_edgeSet he
  have hab_notin : s(Sum.inl a, Sum.inr b) ∉ q.edges := by
    intro hm
    have := hqE _ hm
    rw [hG', edgeSet_deleteEdges] at this
    exact this.2 rfl
  have hq0 : wW q a b = 0 := by
    by_contra hne; exact hab_notin (wW_supp q a b hne)
  set d : R → C → ℤ := wW q - eW (Sum.inl a) (Sum.inr b) with hd
  have heW : ∀ x y, eW (Sum.inl a) (Sum.inr b) x y = if x = a ∧ y = b then 1 else 0 := by
    intro x y; rw [eW_inl_inr]; simp only [@eq_comm _ a x, @eq_comm _ b y]
  have hvm : ∀ z, vm d z = 0 := by
    intro z
    rw [hd, vm_sub, vm_wW hle, vm_eW ((bip_inl_inr a b).2 hab), walk_parity hle]
    simp only [side]
    ring
  refine ⟨d, ?_, ?_, ?_, fun x => hvm (Sum.inl x), fun y => hvm (Sum.inr y)⟩
  · intro h0
    have := congrFun (congrFun h0 a) b
    simp only [hd, Pi.sub_apply, hq0, heW, and_self, if_true, Pi.zero_apply] at this
    norm_num at this
  · intro x y hxy
    by_cases hx : x = a ∧ y = b
    · obtain ⟨rfl, rfl⟩ := hx; exact absurd hab hxy
    · simp only [hd, Pi.sub_apply, heW, if_neg hx, sub_zero]
      by_contra hne
      have hm := hqE _ (wW_supp q x y hne)
      rw [hG', edgeSet_deleteEdges] at hm
      exact hxy ((bip_inl_inr x y).1 hm.1)
  · intro x y
    by_cases hx : x = a ∧ y = b
    · obtain ⟨rfl, rfl⟩ := hx
      simp [hd, hq0, heW]
    · simp only [hd, Pi.sub_apply, heW, if_neg hx, sub_zero]
      exact wW_trail q hqt x y

/-- Integer form of the core: margins determine every weight supported on the edges iff the graph
is acyclic. -/
theorem margins_determine_int_iff :
    (∀ d : R → C → ℤ, (∀ a b, ¬ E a b → d a b = 0) → (∀ a, rowM d a = 0) → (∀ b, colM d b = 0) →
      d = 0) ↔ (bip E).IsAcyclic := by
  constructor
  · intro h
    by_contra hG
    obtain ⟨d, hne, hsupp, -, hrow, hcol⟩ := not_acyclic_witness hG
    exact hne (h d hsupp hrow hcol)
  · intro hG d hsupp hrow hcol
    exact acyclic_margins_zero hG d hsupp hrow hcol

end Core

/-- **Proposition 2c, combinatorial core, on the note's box.** For cell capacities `cap` (the cell
sizes), row and column margins determine every weight `0 ≤ w ≤ cap` iff the bipartite graph of the
positive-capacity cells is acyclic. -/
theorem margins_determine_iff_acyclic (cap : R → C → ℕ) :
    (∀ w w' : R → C → ℕ, (∀ a b, w a b ≤ cap a b) → (∀ a b, w' a b ≤ cap a b) →
      (∀ a, ∑ b, w a b = ∑ b, w' a b) → (∀ b, ∑ a, w a b = ∑ a, w' a b) → w = w') ↔
    (bip fun a b => 0 < cap a b).IsAcyclic := by
  constructor
  · intro h
    by_contra hG
    obtain ⟨d, hne, hsupp, hval, hrow, hcol⟩ := not_acyclic_witness hG
    let w : R → C → ℕ := fun x y => if d x y = 1 then 1 else 0
    let w' : R → C → ℕ := fun x y => if d x y = -1 then 1 else 0
    have hdiff : ∀ x y, ((w x y : ℕ) : ℤ) - ((w' x y : ℕ) : ℤ) = d x y := by
      intro x y
      rcases hval x y with h | h | h <;> simp [w, w', h]
    have hcap : ∀ x y, d x y ≠ 0 → 1 ≤ cap x y := by
      intro x y hxy
      by_contra hlt
      exact hxy (hsupp x y (by omega))
    have hw : ∀ x y, w x y ≤ cap x y := by
      intro x y
      simp only [w]
      split_ifs with h1
      · exact hcap x y (by rw [h1]; norm_num)
      · exact Nat.zero_le _
    have hw' : ∀ x y, w' x y ≤ cap x y := by
      intro x y
      simp only [w']
      split_ifs with h1
      · exact hcap x y (by rw [h1]; norm_num)
      · exact Nat.zero_le _
    have hr : ∀ x, ∑ y, w x y = ∑ y, w' x y := by
      intro x
      have : ((∑ y, w x y : ℕ) : ℤ) - ((∑ y, w' x y : ℕ) : ℤ) = 0 := by
        push_cast
        rw [← Finset.sum_sub_distrib]
        simp only [hdiff]
        exact hrow x
      omega
    have hc : ∀ y, ∑ x, w x y = ∑ x, w' x y := by
      intro y
      have : ((∑ x, w x y : ℕ) : ℤ) - ((∑ x, w' x y : ℕ) : ℤ) = 0 := by
        push_cast
        rw [← Finset.sum_sub_distrib]
        simp only [hdiff]
        exact hcol y
      omega
    have heq := h w w' hw hw' hr hc
    apply hne
    funext x y
    have := hdiff x y
    rw [heq, sub_self] at this
    exact this.symm
  · intro hG w w' hw hw' hr hc
    have hzero := acyclic_margins_zero hG (fun x y => (w x y : ℤ) - w' x y)
      (by
        intro x y hxy
        have h1 := hw x y; have h2 := hw' x y
        have : cap x y = 0 := by omega
        show ((w x y : ℕ) : ℤ) - ((w' x y : ℕ) : ℤ) = 0
        omega)
      (by
        intro x
        simp only [rowM, Finset.sum_sub_distrib]
        exact_mod_cast sub_eq_zero.2 (congrArg (Nat.cast (R := ℤ)) (hr x)))
      (by
        intro y
        simp only [colM, Finset.sum_sub_distrib]
        exact_mod_cast sub_eq_zero.2 (congrArg (Nat.cast (R := ℤ)) (hc y)))
    funext x y
    have := congrFun (congrFun hzero x) y
    simp only [Pi.zero_apply] at this
    omega

/-! ### The channel-level statement -/

section Channel

variable {ι : Type*} [Fintype ι] (γ : ι → R) (γ' : ι → C)

/-- The intersection graph `I(γ, γ')`: an edge between a block of `γ` and a block of `γ'` when
they intersect. -/
def interGraph : SimpleGraph (R ⊕ C) := bip fun a b => ∃ i, γ i = a ∧ γ' i = b

/-- `Φ(γ)`: pass count per block of `γ`. -/
def rowCount (r : ι → Bool) (a : R) : ℕ := (univ.filter fun i => γ i = a ∧ r i = true).card

/-- `Φ(γ')`: pass count per block of `γ'`. -/
def colCount (r : ι → Bool) (b : C) : ℕ := (univ.filter fun i => γ' i = b ∧ r i = true).card

/-- `Φ(γ ∨ γ')`: pass count per cell of the common refinement. -/
def cellCount (r : ι → Bool) (a : R) (b : C) : ℕ :=
  (univ.filter fun i => γ i = a ∧ γ' i = b ∧ r i = true).card

/-- Cell sizes, the capacities of the box. -/
def cellSize (a : R) (b : C) : ℕ := (univ.filter fun i => γ i = a ∧ γ' i = b).card

lemma rowCount_eq_sum (r : ι → Bool) (a : R) : rowCount γ r a = ∑ b, cellCount γ γ' r a b := by
  classical
  unfold rowCount cellCount
  rw [card_eq_sum_card_fiberwise (f := γ') (t := univ) (by intro i _; simp)]
  refine Finset.sum_congr rfl fun b _ => ?_
  congr 1
  ext i
  simp only [mem_filter, mem_univ, true_and]
  tauto

lemma colCount_eq_sum (r : ι → Bool) (b : C) : colCount γ' r b = ∑ a, cellCount γ γ' r a b := by
  classical
  unfold colCount cellCount
  rw [card_eq_sum_card_fiberwise (f := γ) (t := univ) (by intro i _; simp)]
  refine Finset.sum_congr rfl fun a _ => ?_
  congr 1
  ext i
  simp only [mem_filter, mem_univ, true_and]
  tauto

lemma cellCount_le (r : ι → Bool) (a : R) (b : C) : cellCount γ γ' r a b ≤ cellSize γ γ' a b := by
  unfold cellCount cellSize
  apply card_le_card
  intro i
  simp only [mem_filter, mem_univ, true_and]
  tauto

lemma cellSize_pos_iff (a : R) (b : C) : 0 < cellSize γ γ' a b ↔ ∃ i, γ i = a ∧ γ' i = b := by
  unfold cellSize
  rw [card_pos, filter_nonempty_iff]
  simp

/-- Every cell-count vector in the box is the cell-count vector of some record. -/
lemma realize (w : R → C → ℕ) (hw : ∀ a b, w a b ≤ cellSize γ γ' a b) :
    ∃ r : ι → Bool, cellCount γ γ' r = w := by
  classical
  have := fun a b => exists_subset_card_eq (hw a b)
  choose t ht hcard using this
  refine ⟨fun i => decide (i ∈ t (γ i) (γ' i)), ?_⟩
  funext a b
  unfold cellCount
  rw [← hcard a b]
  congr 1
  ext i
  simp only [mem_filter, mem_univ, true_and, decide_eq_true_eq]
  constructor
  · rintro ⟨rfl, rfl, h⟩; exact h
  · intro h
    have := ht a b h
    simp only [cellSize, mem_filter, mem_univ, true_and] at this
    obtain ⟨rfl, rfl⟩ := this
    exact ⟨rfl, rfl, h⟩

/-- Cell counts always determine the two margins: `Φ(γ ∨ γ')` is at least as fine as
`Φ(γ) ∨ Φ(γ')`. -/
theorem cells_determine_margins (r s : ι → Bool) (h : cellCount γ γ' r = cellCount γ γ' s) :
    rowCount γ r = rowCount γ s ∧ colCount γ' r = colCount γ' s := by
  refine ⟨funext fun a => ?_, funext fun b => ?_⟩
  · rw [rowCount_eq_sum γ γ', rowCount_eq_sum γ γ', h]
  · rw [colCount_eq_sum γ γ', colCount_eq_sum γ γ', h]

/-- **Proposition 2c.** Observing the two category leaks separately identifies exactly the same
records as observing the leak of the common refinement — for all records `r, s`, equal row and
column counts iff equal cell counts — iff the intersection graph `I(γ, γ')` is acyclic. -/
theorem prop2c :
    (∀ r s : ι → Bool, (rowCount γ r = rowCount γ s ∧ colCount γ' r = colCount γ' s) ↔
      cellCount γ γ' r = cellCount γ γ' s) ↔ (interGraph γ γ').IsAcyclic := by
  have hgraph : interGraph γ γ' = bip fun a b => 0 < cellSize γ γ' a b :=
    bip_congr fun a b => (cellSize_pos_iff γ γ' a b).symm
  rw [hgraph, ← margins_determine_iff_acyclic]
  constructor
  · intro h w w' hw hw' hr hc
    obtain ⟨r, rfl⟩ := realize γ γ' w hw
    obtain ⟨s, rfl⟩ := realize γ γ' w' hw'
    apply (h r s).1
    refine ⟨funext fun a => ?_, funext fun b => ?_⟩
    · rw [rowCount_eq_sum γ γ', rowCount_eq_sum γ γ', hr a]
    · rw [colCount_eq_sum γ γ', colCount_eq_sum γ γ', hc b]
  · intro h r s
    refine ⟨fun hm => ?_, cells_determine_margins γ γ' r s⟩
    apply h _ _ (cellCount_le γ γ' r) (cellCount_le γ γ' s)
    · intro a
      rw [← rowCount_eq_sum γ γ', ← rowCount_eq_sum γ γ', hm.1]
    · intro b
      rw [← colCount_eq_sum γ γ', ← colCount_eq_sum γ γ', hm.2]

/-- **Proposition 2c in lattice form.** As partitions of the records (Mathlib's `Setoid` order,
in which the note's join `∨`, the common refinement, is `⊓`):
`ker Φ(γ) ⊓ ker Φ(γ') = ker Φ(γ ∨ γ')` iff `I(γ, γ')` is acyclic. -/
theorem prop2c_setoid :
    Setoid.ker (rowCount γ) ⊓ Setoid.ker (colCount γ') = Setoid.ker (cellCount γ γ') ↔
      (interGraph γ γ').IsAcyclic := by
  rw [← prop2c γ γ', Setoid.ext_iff]
  simp only [Setoid.inf_iff_and, Setoid.ker_def]

end Channel

/-- The note's witness: rows `{0,1}|{2,3}`, columns `{0,2}|{1,3}` (a 4-cycle); the records `1001`
and `0110` have equal row and column counts and different cell counts. -/
theorem prop2c_four_cycle_witness :
    let γ : Fin 4 → Fin 2 := ![0, 0, 1, 1]
    let γ' : Fin 4 → Fin 2 := ![0, 1, 0, 1]
    let r : Fin 4 → Bool := ![true, false, false, true]
    let s : Fin 4 → Bool := ![false, true, true, false]
    rowCount γ r = rowCount γ s ∧ colCount γ' r = colCount γ' s ∧
      cellCount γ γ' r ≠ cellCount γ γ' s ∧ ¬ (interGraph γ γ').IsAcyclic := by
  intro γ γ' r s
  have hr : rowCount γ r = rowCount γ s := by funext a; fin_cases a <;> decide
  have hc : colCount γ' r = colCount γ' s := by funext b; fin_cases b <;> decide
  have hne : cellCount γ γ' r ≠ cellCount γ γ' s := by
    intro h
    have := congrFun (congrFun h 0) 0
    revert this; decide
  refine ⟨hr, hc, hne, fun hG => hne ?_⟩
  exact ((prop2c γ γ').2 hG r s).1 ⟨hr, hc⟩

end FeedbackChannel.LatticeJoin

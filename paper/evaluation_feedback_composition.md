# Composition laws for Feedback

Version 0.1 — 2026-10-12. Companion to [evaluation_design_calculus.md](evaluation_design_calculus.md)
(§3 footprints, §4 Repeat, §5 disjoint-update law, §7 order effects) and
[evaluation_feedback_insertions.md](evaluation_feedback_insertions.md) (\(\operatorname{Feedback}_{s,q}\),
the ledger). Nothing here calls a model or observes a controller. Each statement is an algebraic
identity with a proof or an exhaustive check on an enumerated finite model; its evidence line says which.

```powershell
$env:PYTHONPATH = "src"
python scripts/verify_evaluation_feedback_composition.py --output output/evaluation_feedback_composition/composition_v0_1.json
python -m pytest tests/test_evaluation_feedback_composition.py -q
```

Receipt: `output/evaluation_feedback_composition/composition_v0_1.json` (22 checks, `all_passed: true`,
source hashes). Tests: 99. Notation: \(a;b\) applies \(a\) first.

## 1. The executable record

`src/spiral_ln/evaluation_feedback_composition.py` implements \(\mathcal E\) as a frozen record: six
`game.*` fields (\(G\): legal actions, revealed-or-hidden resource, utility, budget, horizon, carry map,
for the two-location game played once per item); `pi` (\(\Pi\): observation-to-action lookup plus
per-item overrides, so a patch memorizes an item identifier); `items` (\(D\): `s0,s1` in selection set
`S`, `r0,r1` in readout set `R`); `acquisition` (\(Z\): privileged record, action redacted on named
sets); `judgment` (\(J\): one for the resource, inverted on flipped items, less a cost for choosing
right; undefined on a redacted record); `generation` (\(g\)); `declarations` (role and access class
per set). \(\mathcal A\) enters only in Proposition 4; \(C\) is not modeled.

Each operator is a pure function with a declared footprint. Restrict, Grant, Cap, Hide (player-facing),
Observe (observation-only), Controller, Rescore, Payoff (optionally also installing the utility as the
judgment) and Repeat write the fields their names suggest and read at most what they write.
\(\operatorname{Feedback}_{S,q}\) reads `game.legal`, `game.revealed`, `pi`, `items`, `acquisition`,
`judgment`, `declarations`, `generation` and writes `pi`, `generation`: item-level access returns the
per-item vector and overrides each item judged nonpositive with the other action; score-only returns
the sum for the incumbent and three fixed candidates and keeps the first maximizer; sealed returns
nothing and only advances \(g\). Feedback on a set whose declaration forbids it raises: ill-typed, not a breach.

## 2. The disjoint-update law and its witnesses

**Proposition 1 (disjoint-update law).** Call a footprint *sound* if the operator changes no field
outside \(W\) and the new values of \(W\) are a function of the old values of \(R\). If \(a,b\) have sound
footprints with \(W_a\cap(R_b\cup W_b)=\emptyset\) and \(W_b\cap(R_a\cup W_a)=\emptyset\), then \(a;b=b;a\) on every record.

*Proof.* Fix \(x\). Fields outside \(W_a\cup W_b\) are untouched in both orders. For \(f\in W_a\): in
\(a;b\), \(a\) writes \(f\) from \(x|_{R_a}\) and \(b\) leaves it (\(f\notin W_b\)); in \(b;a\), \(b\)
leaves \(R_a\) unchanged (\(W_b\cap R_a=\emptyset\)), so \(a\) writes the same value. Likewise \(W_b\). \(\square\)

Boundary: sufficient only, and about the record, not about additivity of behavioural effects (calculus
§5). Fixture: `footprint_audit` checks soundness of all 13 footprints on the 384 enumerated records
(write side per record; read side by grouping records with equal \(R\)-projection and requiring equal
\(W\)-images); `commutation_audit` checks every disjoint pair on every record. Evidence: algebraic
identity (the proposition); finite verified example (the model's footprints are sound; the instances hold).

**Proposition 2 (commutation table).** On the 384 records, of the 78 off-diagonal unordered pairs of
the 13 operators, 60 have disjoint footprints and commute, 15 do not commute, and 3 commute despite
overlapping footprints. The non-commuting pairs, with the field in which the two orders differ:

| Pair | Differ in | First witness (receipt) |
|---|---|---|
| Grant\(_2\), Cap\(_5\) | `game.budget` | budget 4: grant-then-cap 5, cap-then-grant 6 (calculus §5) |
| Rescore\(_j\), Feedback (item, score) | `pi` only | always-left, flip `s1`: rescore-then-feedback learns nothing; feedback-then-rescore memorizes `s1` |
| Observe (redact `S`), Feedback (item, score) | `pi` only | observe-then-feedback learns nothing; feedback-then-observe memorizes `s1` |
| Controller\(_\pi\), Feedback (item, score) | `pi` only | both write \(\Pi\); the second write determines it |
| Hide (player), Feedback (item, score) | `pi` only | follow: hide-then-feedback memorizes `s1`; the other order does not |
| Restrict\(_{\{\text{left}\}}\), Feedback (item, score) | `pi` only | always-left memorizing `s0`→right: Restrict first makes that override illegal and `s0` passes, so only `s1` is patched; Feedback first repatches `s0` too |
| Payoff with training, Feedback (item, score) | `pi` only | the installed judgment changes what is selected or patched |
| Rescore\(_j\), Payoff with training | `judgment` | both write \(J\); the second write wins |
| Feedback (item), Feedback (score) | `pi` only | the two update rules do not commute |

Payoff without training commutes with Feedback (it writes only `game.utility`), as do Grant, Cap and
Repeat; Repeat commuting at design time says nothing about the aggregation unit (Proposition 4).
Commuting despite overlap: sealed Feedback with either other Feedback (both write `generation`;
\(g+1+1\) is order-free) and the two Payoffs (same utility). Rescore before Feedback changes what the
loop learns; after, only the readout: the final \(J\) agrees, \(\Pi\) differs, and \(V^S\) is 1 against
1/2 in the hand-computed test. Evidence: finite verified example, for these records and update rules only.

## 3. Typing as ledger audit

`compile_ledger` maps a design expression with declarations to the `(sets, events)` input of
`audit_ledger`: item-level Feedback records one `item_feedback` naming every item of the set (the vector
reached the loop, whatever the rule did with it); score-only records one `score_query` per policy
scored; sealed records nothing; Readout\(_t\) records one `readout`; other operators are outside the
channel. \(\Gamma\) carries declarations, cumulative patches, retirement and readouts per set:

- (F-SEL) \(\Gamma\vdash\operatorname{Feedback}_{s,q}\), \(q>\)sealed, iff \(s\) is declared selection,
  access\((s)\ge q\), and \(s\) not retired; item-level adds \(|s|\) to patches\((s)\), and \(s\) retires
  once patches\(/|s|\) exceeds the bound (the crossing step is itself typed).
- (F-SEALED) \(\operatorname{Feedback}_{s,\text{sealed}}\) is typed, \(\Gamma'=\Gamma\); likewise (NEUTRAL) every other operator.
- (RO) \(\operatorname{Readout}_t\) iff role\((t)=\)readout (hence sealed) and the count stays within the readout budget.

**Proposition 3.** Over all 22,143 sequences of length \(\le4\) from the nine-symbol alphabet
{Feedback\(_{S,q}\), Feedback\(_{R,q}\) for the three access classes, Readout\(_R\), Readout\(_S\),
Rescore} under three declaration contexts (`S` declared item-level, score-only or sealed; `R` sealed;
budget 2; bound 1 with \(|S|=2\)), a sequence is well-typed iff `audit_ledger` returns
`declarations_respected = True` (2,581 respected, 11,462 breached, 8,100 raise). Evidence: finite verified example.

Two findings. (i) The ledger has two rejection modes: every sequence containing Readout\(_S\) makes
`audit_ledger` raise ("readout events apply to readout sets only") rather than record a breach, so that
run gets no report, unlike the other breaches, which its docstring says should survive into the report;
the equivalence counts a raise as not respected. (ii) The literal rule "Feedback\(_{s,q}\) requires role
selection and access \(\ge q\)" is too strict at \(q=\)sealed: a sealed read has no event, so
Feedback\(_{R,\text{sealed}}\) is invisible to the ledger; with the literal premise the equivalence fails
on exactly 1,414 sequences, all respected runs containing it and nothing else ill-typed. (F-SEALED)
drops the premise; `audit_ledger` is not patched.

## 4. Repeat with a carry map

**Proposition 4 (generations joined by Feedback are not blocks).** Let \(K\ge2\) candidates each
succeed independently with probability \(p\in(0,1)\) on each of \(n\) items of \(s\); generation 1
keeps the best by score (\(S_1\)); the carry map of \(\operatorname{Repeat}_{2,m}\) carries \(\Pi_2\)
into generation 2's pool with \(K-1\) fresh candidates (\(S_2\)). Then \(S_2\) is the maximum of
\(2K-1\) i.i.d. scores, so \(\mathbb E S_2=p+\gamma(n,2K-1,p)>p+\gamma(n,K,p)=\mathbb E S_1\) with
\(\gamma\) the gap of `selection_inflation`; \(S_2\ge S_1\) pointwise with
\(\Pr[S_2>S_1]\ge(1-p)^{nK}\bigl(1-(1-p)^{n(K-1)}\bigr)>0\); hence \((S_1,S_2)\) is not exchangeable,
and the mean over generations exceeds what the same \(\mathcal A\) reports over independent blocks by
\((\gamma(n,2K-1,p)-\gamma(n,K,p))/2>0\), while the sealed readout stays at \(p\): the whole expected
gain \(\mathbb E[S_2-S_1]\) is a change in \(\rho\). Under the reset map \(S_1,S_2\) are i.i.d. and
the two aggregations agree.

*Proof.* The kept candidate's realized outcomes on \(s\) are fixed, so its generation-2 score is
\(S_1\), and the pool maximum is the maximum of the original \(K\) and the fresh \(K-1\) i.i.d. scores.
Monotonicity gives \(S_2\ge S_1\); "all \(nK\) generation-1 outcomes fail and some fresh outcome
succeeds" has the stated probability and forces \(S_2>S_1\); unequal means rule out exchangeability. \(\square\)

Fixture: `repeat_carry_fixture` enumerates every outcome matrix. At \(n=1,K=2,p=1/2\):
\(\mathbb ES_1=3/4\), \(\mathbb ES_2=7/8\), generation mean \(13/16\) under carry against \(3/4\) over
independent blocks, \(\Pr[S_2>S_1]=1/8\), \(\Pr[S_1>S_2]=0\), \(\rho=1/4\) then \(3/8\); three further
cells agree with `selection_inflation` at \(2K-1\). Evidence: algebraic identity under the stated
model; finite verified example for the numbers. Boundary: two generations, equal candidates, independent
items, a carry map re-scoring the incumbent on the same items; the multi-generation chain is built elsewhere.

## 5. Readout gap under Rescore

**Proposition 5.** \(\rho=V^s-V^r\) is a function of \((G,\Pi,D,Z,J)\); \(\operatorname{Rescore}_j\)
writes \(J\) only, \(\operatorname{Feedback}\) writes \(\Pi\) and \(g\). So \(\rho\) can change with
\(\Pi\), \(g\) fixed and no ledger event, and a change in \(\rho\) alone does not identify feedback.
Fixture (`readout_gap_rescore_fixture`, always-left controller, \(\rho=0\)): rescoring `r1` moves
\(\rho\) to \(-1/2\); rescoring `s1` moves it to \(+1/2\), exactly the \(\rho\) that
\(\operatorname{Feedback}_{S,\text{item}}\) produces by memorizing `s1`. The ledger separates the two
(0 against 2 patches on `S`); \(\rho\) does not. Evidence: algebraic identity (footprints); finite verified example (values).

## 6. What is general and what is enumerated

Proven in general: Propositions 1, 4 and 5 as stated. Checked only on enumerated cases: footprint
soundness (384 records), the commutation table (13 operators, 384 records), the typing/ledger
equivalence (22,143 sequences, three contexts), and every number above. The witnesses concern one pair
of update rules on one tiny game; another patch or selection rule needs the audit rerun. All laws are
design-time transformations of the record, not what a learned controller does with what the channel
transmits. No model was run.

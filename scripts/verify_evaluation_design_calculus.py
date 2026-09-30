"""Verify finite mathematical examples; this script evaluates no AI models."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction as Q
from hashlib import sha256
from itertools import product
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compose(k, l):
    if not k or not l or len(k[0]) != len(l):
        raise ValueError("kernel interfaces do not match")
    return tuple(
        tuple(sum(k[x][y] * l[y][z] for y in range(len(l)))
              for z in range(len(l[0])))
        for x in range(len(k))
    )


def tensor(k, l):
    return tuple(
        tuple(k[x][y] * l[u][v]
              for y in range(len(k[0])) for v in range(len(l[0])))
        for x in range(len(k)) for u in range(len(l))
    )


def is_kernel(k):
    return bool(k) and all(
        len(row) == len(k[0]) and sum(row) == 1 and all(v >= 0 for v in row)
        for row in k
    )


def optimal_resource_value(states, prior, visible, actions):
    observations = states if visible else ["hidden"]
    candidates = []
    for responses in product(actions, repeat=len(observations)):
        policy = dict(zip(observations, responses))
        value = sum(
            p * int(policy[state if visible else "hidden"] == state)
            for state, p in zip(states, prior)
        )
        candidates.append(value)
    return max(candidates), len(candidates)


def deviation_gaps(payoffs, a, b):
    return (
        max(payoffs[alternative][b][0] for alternative in range(len(payoffs)))
        - payoffs[a][b][0],
        max(payoffs[a][alternative][1] for alternative in range(len(payoffs[a])))
        - payoffs[a][b][1],
    )


def pure_equilibria(payoffs, labels):
    return [
        [labels[a], labels[b]]
        for a, b in product(range(len(labels)), repeat=2)
        if deviation_gaps(payoffs, a, b) == (0, 0)
    ]


def verify(spec):
    checks = []

    def check(name, passed, **evidence):
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    resource = spec["hidden_resource"]
    states = resource["states"]
    prior = list(map(Q, resource["prior"]))
    if len(states) != 2 or len(prior) != 2 or sum(prior) != 1 or min(prior) < 0:
        raise ValueError("expected a two-state probability distribution")
    values = {}
    for visible, either in product((False, True), repeat=2):
        actions = states if either else states[:1]
        key = f"{'revealed' if visible else 'hidden'}:{'either' if either else 'left_only'}"
        value, count = optimal_resource_value(states, prior, visible, actions)
        values[(int(visible), int(either))] = value
        check(f"resource_policy_enumeration:{key}",
              value == Q(resource["expected_optimal_values"][key]),
              optimal_value=str(value), deterministic_policy_count=count)

    interaction = values[1, 1] - values[1, 0] - values[0, 1] + values[0, 0]
    check("information_action_interaction",
          interaction == Q(resource["expected_interaction"]), value=str(interaction))

    # Inclusion-exclusion over the complete two-mechanic subset lattice.
    subsets = [frozenset(s) for s in ((), (0,), (1,), (0, 1))]
    cell = {s: values[int(0 in s), int(1 in s)] for s in subsets}
    beta = {s: sum((-1) ** (len(s) - len(t)) * cell[t]
                   for t in subsets if t <= s) for s in subsets}
    check("subset_expansion_reconstruction",
          all(sum(beta[t] for t in subsets if t <= s) == cell[s] for s in subsets),
          coefficients={str(sorted(s)): str(v) for s, v in beta.items()})

    disclosed_value = sum(
        p * optimal_resource_value([state], [Q(1)], False, states)[0]
        for state, p in zip(states, prior)
    )
    hidden_value = optimal_resource_value(states, prior, False, states)[0]
    check("mixture_disclosure_changes_optimum",
          disclosed_value == 1 and hidden_value == Q(1, 2),
          disclosed=str(disclosed_value), hidden=str(hidden_value))

    renamed = ["compute_slot_beta", "compute_slot_alpha"]
    check("resource_renaming_preserves_optimal_values",
          all(optimal_resource_value(renamed, prior, bool(i),
                                    renamed if b else renamed[:1])[0] == value
              for (i, b), value in values.items()),
          scope="Corresponding finite policy spaces; not unchanged-model behavior")

    dilemma = spec["social_dilemma"]
    payoff = dilemma["payoffs"]
    labels = dilemma["actions"]
    base_equilibria = pure_equilibria(payoff, labels)
    check("social_dilemma_pure_equilibrium",
          base_equilibria == dilemma["expected_base_pure_equilibria"],
          equilibria=base_equilibria)
    check("taking_strictly_dominant",
          all(payoff[1][b][0] > payoff[0][b][0] for b in range(2))
          and all(payoff[a][1][1] > payoff[a][0][1] for a in range(2)))
    check("cooperation_welfare_and_gaps",
          deviation_gaps(payoff, 0, 0) == (2, 2)
          and sum(payoff[0][0]) == 6 and sum(payoff[1][1]) == 2,
          share_gaps=list(deviation_gaps(payoff, 0, 0)),
          take_gaps=list(deviation_gaps(payoff, 1, 1)))

    levy = dilemma["levy_on_taking"]
    modified = [[[payoff[a][b][0] - levy * (a == 1),
                  payoff[a][b][1] - levy * (b == 1)]
                 for b in range(2)] for a in range(2)]
    levy_equilibria = pure_equilibria(modified, labels)
    check("taking_levy_changes_equilibrium",
          levy_equilibria == dilemma["expected_levied_pure_equilibria"],
          modified_payoffs=modified, equilibria=levy_equilibria)

    affine = [[[2 * payoff[a][b][0] + 7, 3 * payoff[a][b][1] - 4]
               for b in range(2)] for a in range(2)]
    check("positive_affine_payoff_equilibrium_invariance",
          pure_equilibria(affine, labels) == base_equilibria)
    check("nonlinear_lottery_preference_reversal",
          Q(2) < Q(21, 10) and Q(8) > Q(21, 10) ** 2,
          expected_original=["2", "21/10"], expected_squared=["8", "441/100"])

    reward, temptation, punishment = payoff[0][0][0], payoff[1][0][0], payoff[1][1][0]
    threshold = Q(temptation - reward, temptation - punishment)
    check("grim_trigger_threshold",
          threshold == Q(dilemma["expected_grim_trigger_threshold"]), value=str(threshold))
    for raw_discount in dilemma["discount_checks"]:
        discount = Q(raw_discount)
        cooperate = Q(reward) / (1 - discount)
        deviate = temptation + discount * punishment / (1 - discount)
        check(f"grim_trigger_discount:{raw_discount}",
              (cooperate >= deviate) == (discount >= threshold),
              cooperative_value=str(cooperate), deviation_value=str(deviate))

    flow = spec["resource_flow"]
    incidence = flow["incidence"]
    final = [x + sum(b * f for b, f in zip(row, flow["flows"]))
             for x, row in zip(flow["initial_stock"], incidence)]
    check("flow_conservation",
          all(sum(column) == 0 for column in zip(*incidence))
          and final == flow["expected_final_stock"]
          and sum(final) == sum(flow["initial_stock"]), final_stock=final)
    # Validate the actual specified transfer order, not just final balances.
    running = list(flow["initial_stock"])
    sequentially_feasible = True
    for column, amount in enumerate(flow["flows"]):
        sequentially_feasible &= all(
            stock >= -row[column] * amount
            for stock, row in zip(running, incidence) if row[column] < 0
        )
        running = [stock + row[column] * amount
                   for stock, row in zip(running, incidence)]
    check("flow_sequential_feasibility", sequentially_feasible and running == final)
    injected = [x + source for x, source in zip(final, flow["external_source"])]
    check("external_source_ledger",
          sum(injected) - sum(final) == sum(flow["external_source"]),
          final_total=sum(final), total_with_source=sum(injected))

    k = ((Q(1, 3), Q(2, 3)), (Q(1, 2), Q(1, 2)))
    l = ((Q(3, 4), Q(1, 4)), (Q(1, 5), Q(4, 5)))
    m = ((Q(0), Q(1)), (Q(1), Q(0)))
    identity = ((Q(1), Q(0)), (Q(0), Q(1)))
    check("fixture_kernels_are_stochastic", all(map(is_kernel, (k, l, m, identity))))
    check("kernel_associativity_instance", compose(compose(k, l), m) == compose(k, compose(l, m)))
    check("kernel_identity_instance", compose(identity, k) == k == compose(k, identity))
    check("independent_tensor_interchange_instance",
          compose(tensor(k, l), tensor(m, k)) == tensor(compose(k, m), compose(l, k)))
    try:
        compose(k, ((Q(1),),))
    except ValueError:
        check("mismatched_kernel_interface_rejected", True)
    else:
        check("mismatched_kernel_interface_rejected", False)

    record = {"public": 1, "private": 2}
    hide = lambda item: {key: value for key, value in item.items() if key != "private"}
    check("deterministic_hiding_idempotence_instance", hide(hide(record)) == hide(record))
    retention = Q(1, 2)
    check("independent_thinning_not_idempotent", retention ** 2 != retention,
          once=str(retention), twice=str(retention ** 2))
    cap_after_grant = min(4 + 2, 5)
    grant_after_cap = min(4, 5) + 2
    check("budget_order_counterexample", cap_after_grant != grant_after_cap,
          cap_after_grant=cap_after_grant, grant_after_cap=grant_after_cap)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path,
                        default=ROOT / "configs/evaluation_design_calculus_examples.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    spec_bytes = args.spec.read_bytes()
    checks = verify(json.loads(spec_bytes))
    report = {
        "schema_version": "0.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_status": "exact_finite_mathematical_fixtures_not_model_evaluations",
        "arithmetic": "integers_and_exact_rational_numbers",
        "scope": "Finite examples and law instances; not a general theorem prover or equilibrium solver",
        "spec_sha256": sha256(spec_bytes).hexdigest(),
        "verifier_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "check_count": len(checks),
        "all_passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
        print(json.dumps({"all_passed": report["all_passed"], "checks": len(checks),
                          "output": str(args.output.resolve())}))
    else:
        print(encoded)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

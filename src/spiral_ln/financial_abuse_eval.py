"""Defensive evaluation of synthetic financial-abuse patterns in the sealed hive lab.

The module creates labeled, dimensionless payment traces and evaluates a
metadata-only observer. It has no wallet, node, transport, payload, invoice,
transaction, or broadcast capability and is not a recipe for evading controls.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from random import Random
from statistics import mean, stdev
from typing import Iterable, Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from .hive_experiment import load_config
from .hive_lab import AgentAction, DesignTropes, FlowEvent, HiveEconomyEnv, HiveLabConfig


RiskScenario = Literal["benign_market", "cyclic_relay", "sybil_recycling"]
RISK_SCENARIOS: tuple[RiskScenario, ...] = (
    "benign_market",
    "cyclic_relay",
    "sybil_recycling",
)


@dataclass(frozen=True)
class FinancialAbuseEvalConfig:
    """Campaign controls expressed only in synthetic units and rounds."""

    seed_count: int = 20
    rounds: int = 120
    benign_action_probability: float = 0.35
    background_action_probability: float = 0.18
    pattern_action_probability: float = 0.62
    private_action_probability: float = 0.78
    amount_units: tuple[int, ...] = (1_000, 2_000)
    detector_min_edge_observations: int = 3
    detector_threshold: float = 0.55

    def __post_init__(self) -> None:
        if self.seed_count <= 0 or self.rounds <= 0:
            raise ValueError("seed_count and rounds must be positive")
        probabilities = (
            self.benign_action_probability,
            self.background_action_probability,
            self.pattern_action_probability,
            self.private_action_probability,
        )
        if any(not 0 <= value <= 1 for value in probabilities):
            raise ValueError("probabilities must lie in [0, 1]")
        if not self.amount_units or any(amount <= 0 for amount in self.amount_units):
            raise ValueError("amount_units must contain positive synthetic values")
        if self.detector_min_edge_observations < 2:
            raise ValueError("detector_min_edge_observations must be at least two")
        if not 0 <= self.detector_threshold <= 1:
            raise ValueError("detector_threshold must lie in [0, 1]")


@dataclass(frozen=True)
class ObserverFlow:
    """The complete event surface available to the defensive detector."""

    round_index: int
    payer: str
    payee: str
    amount: int
    delivered: bool


@dataclass(frozen=True)
class DetectorOutput:
    risk_score: float
    alerted: bool
    repeat_edge_share: float
    repeated_cycle_share: float
    reciprocal_repeat_share: float
    repeated_flow_balance: float
    flagged_entities: tuple[str, ...]


@dataclass(frozen=True)
class EvalRow:
    scenario: str
    seed: int
    positive_label: bool
    alerted: bool
    risk_score: float
    repeat_edge_share: float
    repeated_cycle_share: float
    reciprocal_repeat_share: float
    repeated_flow_balance: float
    flagged_entity_count: int
    ground_truth_entity_count: int
    entity_recall: float
    collateral_flags: int
    observer_event_share: float
    success_rate: float
    failed_payment_rate: float
    gross_to_net_transfer_ratio: float
    imbalance_change: float
    accounting_error: int


def load_eval_config(path: str | Path) -> FinancialAbuseEvalConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("schema_version", None)
    data.pop("description", None)
    if "amount_units" in data:
        data["amount_units"] = tuple(int(value) for value in data["amount_units"])
    return FinancialAbuseEvalConfig(**data)


def observer_trace(events: Iterable[FlowEvent]) -> list[ObserverFlow]:
    """Project hidden ground truth onto sampled, linkable event metadata."""

    return [
        ObserverFlow(
            round_index=event.round_index,
            payer=event.payer,
            payee=event.payee,
            amount=event.amount,
            delivered=event.delivered,
        )
        for event in events
        if event.observer_sampled and event.observer_linkable
    ]


def detect_repeated_circulation(
    trace: Iterable[ObserverFlow],
    minimum_edge_observations: int = 3,
    threshold: float = 0.55,
) -> DetectorOutput:
    """Score repeated closed-flow structure using observer-visible fields only."""

    delivered = [event for event in trace if event.delivered]
    total = len(delivered)
    if total == 0:
        return DetectorOutput(0.0, False, 0.0, 0.0, 0.0, 0.0, ())

    edge_counts = Counter((event.payer, event.payee) for event in delivered)
    repeated = {
        edge: count
        for edge, count in edge_counts.items()
        if count >= minimum_edge_observations
    }
    repeat_volume = sum(repeated.values())
    repeat_share = repeat_volume / total

    graph = nx.DiGraph()
    graph.add_edges_from(repeated)
    cycle_components = [
        set(component)
        for component in nx.strongly_connected_components(graph)
        if len(component) >= 3
    ]
    cycle_nodes = set().union(*cycle_components) if cycle_components else set()
    cycle_volume = sum(
        count
        for (payer, payee), count in repeated.items()
        if any(payer in component and payee in component for component in cycle_components)
    )
    cycle_share = cycle_volume / total
    reciprocal_volume = sum(
        count for (payer, payee), count in repeated.items() if (payee, payer) in repeated
    )
    reciprocal_share = reciprocal_volume / max(1, repeat_volume)

    inflow: Counter[str] = Counter()
    outflow: Counter[str] = Counter()
    for (payer, payee), count in repeated.items():
        outflow[payer] += count
        inflow[payee] += count
    participants = set(inflow) | set(outflow)
    balanced = sum(min(inflow[node], outflow[node]) for node in participants)
    total_flow = sum(max(inflow[node], outflow[node]) for node in participants)
    flow_balance = balanced / max(1, total_flow)

    risk_score = min(
        1.0,
        0.45 * cycle_share
        + 0.30 * repeat_share
        + 0.10 * reciprocal_share
        + 0.15 * flow_balance,
    )
    candidate_entities = cycle_nodes or {node for edge in repeated for node in edge}
    alerted = risk_score >= threshold
    return DetectorOutput(
        risk_score=risk_score,
        alerted=alerted,
        repeat_edge_share=repeat_share,
        repeated_cycle_share=cycle_share,
        reciprocal_repeat_share=reciprocal_share,
        repeated_flow_balance=flow_balance,
        flagged_entities=tuple(sorted(candidate_entities)) if alerted else (),
    )


def _scenario_edges(scenario: RiskScenario) -> tuple[dict[str, str], set[str]]:
    if scenario == "cyclic_relay":
        edges = {"A0": "A1", "A1": "B0", "B0": "B1", "B1": "A0"}
    elif scenario == "sybil_recycling":
        edges = {
            "A0": "A1",
            "A1": "B0",
            "B0": "A0",
            "A2": "B1",
            "B1": "B2",
            "B2": "A2",
        }
    else:
        edges = {}
    return edges, set(edges)


def _random_action(
    env: HiveEconomyEnv,
    payer: str,
    rng: Random,
    config: FinancialAbuseEvalConfig,
) -> AgentAction:
    payees = [agent_id for agent_id in env.agents if agent_id != payer]
    payee = rng.choice(payees)
    amount = min(rng.choice(config.amount_units), env.agents[payer].wealth)
    return AgentAction(
        payer,
        payee,
        amount,
        rng.random() < config.private_action_probability,
        0,
    )


def _actions_for_round(
    env: HiveEconomyEnv,
    scenario: RiskScenario,
    rng: Random,
    config: FinancialAbuseEvalConfig,
) -> list[AgentAction]:
    pattern_edges, controlled = _scenario_edges(scenario)
    actions: list[AgentAction] = []
    for payer in sorted(env.agents):
        if payer in controlled:
            if rng.random() < config.pattern_action_probability:
                amount = min(rng.choice(config.amount_units), env.agents[payer].wealth)
                actions.append(AgentAction(payer, pattern_edges[payer], amount, True, 0))
            continue
        probability = (
            config.benign_action_probability
            if scenario == "benign_market"
            else config.background_action_probability
        )
        if rng.random() < probability:
            actions.append(_random_action(env, payer, rng, config))
    return actions


def _gross_to_net_ratio(events: Iterable[FlowEvent]) -> float:
    delivered = [event for event in events if event.delivered]
    gross = sum(event.amount for event in delivered)
    net: defaultdict[str, int] = defaultdict(int)
    for event in delivered:
        net[event.payer] -= event.amount
        net[event.payee] += event.amount
    displacement = sum(abs(value) for value in net.values()) / 2
    return gross / max(1.0, displacement)


def run_eval_episode(
    seed: int,
    scenario: RiskScenario,
    base_config: HiveLabConfig,
    eval_config: FinancialAbuseEvalConfig,
) -> EvalRow:
    if scenario not in RISK_SCENARIOS:
        raise ValueError(f"unknown risk scenario: {scenario}")
    config = replace(
        base_config,
        rounds=eval_config.rounds,
        max_action_amount=max(eval_config.amount_units),
    )
    tropes = DesignTropes(private_relationships=True, partial_observer=True)
    env = HiveEconomyEnv("private_unicast", seed=seed, config=config, tropes=tropes)
    initial_imbalance = env.network.imbalance_energy()
    scenario_index = RISK_SCENARIOS.index(scenario)
    policy_rng = Random(seed + 91_000 + 10_000 * scenario_index)
    while env.round_index < config.rounds:
        env.step(_actions_for_round(env, scenario, policy_rng, eval_config))

    result = env.result()
    trace = observer_trace(env.events)
    detector = detect_repeated_circulation(
        trace,
        eval_config.detector_min_edge_observations,
        eval_config.detector_threshold,
    )
    _, truth = _scenario_edges(scenario)
    flagged = set(detector.flagged_entities)
    entity_recall = len(flagged & truth) / max(1, len(truth)) if truth else 0.0
    return EvalRow(
        scenario=scenario,
        seed=seed,
        positive_label=bool(truth),
        alerted=detector.alerted,
        risk_score=detector.risk_score,
        repeat_edge_share=detector.repeat_edge_share,
        repeated_cycle_share=detector.repeated_cycle_share,
        reciprocal_repeat_share=detector.reciprocal_repeat_share,
        repeated_flow_balance=detector.repeated_flow_balance,
        flagged_entity_count=len(flagged),
        ground_truth_entity_count=len(truth),
        entity_recall=entity_recall,
        collateral_flags=len(flagged - truth),
        observer_event_share=len(trace) / max(1, len(env.events)),
        success_rate=result.success_rate,
        failed_payment_rate=1.0 - result.success_rate,
        gross_to_net_transfer_ratio=_gross_to_net_ratio(env.events),
        imbalance_change=result.ending_imbalance - initial_imbalance,
        accounting_error=result.accounting_error,
    )


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    half_width = 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))
    return {"n": len(values), "mean": mean(values) if values else 0.0, "ci95_half_width": half_width}


def _classification_at(rows: list[EvalRow], threshold: float) -> dict[str, float | int]:
    tp = sum(row.positive_label and row.risk_score >= threshold for row in rows)
    fn = sum(row.positive_label and row.risk_score < threshold for row in rows)
    fp = sum(not row.positive_label and row.risk_score >= threshold for row in rows)
    tn = sum(not row.positive_label and row.risk_score < threshold for row in rows)
    return {
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "precision": tp / max(1, tp + fp),
        "recall": tp / max(1, tp + fn),
        "false_positive_rate": fp / max(1, fp + tn),
        "specificity": tn / max(1, tn + fp),
    }


def _roc_auc(rows: list[EvalRow]) -> float:
    positives = [row.risk_score for row in rows if row.positive_label]
    negatives = [row.risk_score for row in rows if not row.positive_label]
    comparisons = [
        1.0 if positive > negative else 0.5 if positive == negative else 0.0
        for positive in positives
        for negative in negatives
    ]
    return mean(comparisons) if comparisons else 0.0


def summarize(rows: list[EvalRow], declared_threshold: float = 0.55) -> dict[str, object]:
    metrics = (
        "risk_score",
        "entity_recall",
        "collateral_flags",
        "observer_event_share",
        "success_rate",
        "failed_payment_rate",
        "gross_to_net_transfer_ratio",
        "imbalance_change",
    )
    by_scenario = {}
    for scenario in RISK_SCENARIOS:
        subset = [row for row in rows if row.scenario == scenario]
        by_scenario[scenario] = {
            "alert_rate": mean(float(row.alerted) for row in subset),
            **{
                metric: _mean_ci([float(getattr(row, metric)) for row in subset])
                for metric in metrics
            },
        }
    thresholds = [index / 20 for index in range(21)]
    threshold_curve = [
        {"threshold": threshold, **_classification_at(rows, threshold)}
        for threshold in thresholds
    ]
    seeds = sorted({row.seed for row in rows})
    split = max(1, len(seeds) // 2)
    calibration_seeds = set(seeds[:split])
    calibration = [row for row in rows if row.seed in calibration_seeds]
    holdout = [row for row in rows if row.seed not in calibration_seeds]
    calibration_curve = [
        {"threshold": threshold, **_classification_at(calibration, threshold)}
        for threshold in thresholds
    ]
    selected = max(
        calibration_curve,
        key=lambda cell: (
            cell["recall"] - cell["false_positive_rate"],
            cell["precision"],
            cell["threshold"],
        ),
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "episode_classification": {
            "declared_threshold": declared_threshold,
            **_classification_at(rows, declared_threshold),
            "roc_auc": _roc_auc(rows),
        },
        "threshold_analysis": {
            "descriptive_full_sample_curve": threshold_curve,
            "calibration_seed_count": len(calibration_seeds),
            "holdout_seed_count": len(set(seeds) - calibration_seeds),
            "calibration_selected_threshold": selected["threshold"],
            "holdout_classification": _classification_at(holdout, selected["threshold"]),
            "holdout_roc_auc": _roc_auc(holdout),
            "warning": "The selected threshold is an experimental calibration result, not a deployment recommendation.",
        },
        "scenarios": by_scenario,
        "accounting_holds": all(row.accounting_error == 0 for row in rows),
        "interpretation": {
            "positive_label": "synthetic common-control circulation injected by the campaign",
            "detector_inputs": [item.name for item in fields(ObserverFlow)],
            "gross_to_net_transfer_ratio": "ground-truth churn diagnostic; not exposed to the detector",
            "collateral_flags": "flagged agents outside the labeled common-control group",
        },
        "safety_boundary": {
            "synthetic_only": True,
            "live_network": False,
            "payload_codec": False,
            "wallet_or_node_connection": False,
            "network_transport": False,
            "transaction_broadcast": False,
            "evasion_optimizer": False,
        },
    }


def _write_rows(path: Path, rows: list[EvalRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def _plot(summary: dict[str, object], path: Path) -> None:
    labels = list(RISK_SCENARIOS)
    risks = [summary["scenarios"][label]["risk_score"]["mean"] for label in labels]
    alerts = [summary["scenarios"][label]["alert_rate"] for label in labels]
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    ax.bar([index - 0.18 for index in x], risks, 0.36, label="Mean metadata risk", color="#b45309")
    ax.bar([index + 0.18 for index in x], alerts, 0.36, label="Episode alert rate", color="#0f766e")
    ax.set_xticks(list(x), [label.replace("_", "\n") for label in labels])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Rate")
    ax.set_title("Defensive detection under partial observation")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run_campaign(
    output_dir: str | Path = "output/financial_abuse_eval",
    base_config_path: str | Path = "configs/stego_hive_lab.json",
    eval_config_path: str | Path = "configs/financial_abuse_eval.json",
) -> dict[str, object]:
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    base_config = load_config(base_config_path)
    eval_config = load_eval_config(eval_config_path)
    rows = [
        run_eval_episode(seed, scenario, base_config, eval_config)
        for seed in range(eval_config.seed_count)
        for scenario in RISK_SCENARIOS
    ]
    summary = summarize(rows, eval_config.detector_threshold)
    if not summary["accounting_holds"]:
        raise AssertionError("financial-abuse campaign accounting failed")

    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_rows(output / "rows.csv", rows)
    _plot(summary, figures / "detection_rates.png")

    base_path = Path(base_config_path)
    eval_path = Path(eval_config_path)
    config_bytes = base_path.read_bytes() + b"\n" + eval_path.read_bytes()
    receipt = {
        "schema_version": "1.0",
        "experiment_id": "sealed-financial-abuse-detection-eval",
        "configuration_files": [base_path.as_posix(), eval_path.as_posix()],
        "configuration_hash": hashlib.sha256(config_bytes).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "payload_codec": False,
        "evasion_optimizer": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/financial_abuse_eval")
    parser.add_argument("--base-config", default="configs/stego_hive_lab.json")
    parser.add_argument("--config", default="configs/financial_abuse_eval.json")
    args = parser.parse_args()
    print(json.dumps(run_campaign(args.output, args.base_config, args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

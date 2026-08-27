"""Map when past-demand-aware connector placement adds value over random capital.

This sealed phase sweep varies persistent endpoint demand and local liquidity
isolation. It uses only synthetic state and cannot connect to Lightning nodes,
wallets, invoices, network transports, or transaction systems.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from random import Random
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .agent_capability_eval import (
    ConnectorPolicy,
    choose_equal_budget_random_connector,
    choose_observed_demand_connector,
)
from .algebra import NetworkState, apply_connector
from .simulator import Demand, demand_stream, route_payment, two_cluster_state


POLICIES: tuple[ConnectorPolicy, ...] = ("none", "random", "demand_aware")


@dataclass(frozen=True)
class PlacementBoundaryConfig:
    seed_count: int = 20
    steps: int = 300
    warmup_steps: int = 75
    connector_capital: int = 120_000
    connector_bond_fraction: float = 0.20
    hotspot_source: str = "A7"
    hotspot_target: str = "B7"
    hotspot_probabilities: tuple[float, ...] = (0.0, 0.25, 0.50, 0.75)
    isolation_fractions: tuple[float, ...] = (0.0, 0.50, 0.80, 0.95)

    def __post_init__(self) -> None:
        if self.seed_count <= 0 or self.steps <= 0:
            raise ValueError("seed_count and steps must be positive")
        if not 0 < self.warmup_steps < self.steps:
            raise ValueError("warmup_steps must be inside the episode")
        if self.connector_capital <= 0:
            raise ValueError("connector_capital must be positive")
        if any(not 0 <= value <= 1 for value in self.hotspot_probabilities):
            raise ValueError("hotspot probabilities must lie in [0, 1]")
        if any(not 0 <= value <= 1 for value in self.isolation_fractions):
            raise ValueError("isolation fractions must lie in [0, 1]")


@dataclass(frozen=True)
class PlacementRow:
    seed: int
    policy: str
    hotspot_probability: float
    isolation_fraction: float
    connector_endpoints: str
    connector_capital: int
    attempted: int
    succeeded: int
    delivered_volume: int
    failed_route_attempts: int
    fee_msat: int
    imbalance_end: float

    @property
    def success_rate(self) -> float:
        return self.succeeded / max(1, self.attempted)

    @property
    def leakage_proxy(self) -> float:
        return self.failed_route_attempts / max(1, self.attempted)

    @property
    def fee_per_delivered_sat(self) -> float:
        return self.fee_msat / max(1, self.delivered_volume)

    def to_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["success_rate"] = self.success_rate
        row["leakage_proxy"] = self.leakage_proxy
        row["fee_per_delivered_sat"] = self.fee_per_delivered_sat
        return row


def load_config(path: str | Path) -> PlacementBoundaryConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("schema_version", None)
    data.pop("description", None)
    for field_name in ("hotspot_probabilities", "isolation_fractions"):
        if field_name in data:
            data[field_name] = tuple(float(value) for value in data[field_name])
    return PlacementBoundaryConfig(**data)


def isolate_hotspot_endpoints(
    state: NetworkState,
    endpoints: tuple[str, str],
    fraction: float,
) -> None:
    """Reserve a fraction of pre-existing liquidity incident to hot endpoints."""

    for channel in state.channels.values():
        if channel.u not in endpoints and channel.v not in endpoints:
            continue
        channel.locked_uv = max(channel.locked_uv, int(channel.balance_uv * fraction))
        channel.locked_vu = max(channel.locked_vu, int(channel.balance_vu * fraction))
    state.assert_invariants()


def hotspot_demand_stream(
    seed: int,
    steps: int,
    probability: float,
    source: str,
    target: str,
) -> list[Demand]:
    base = demand_stream(seed, steps)
    rng = Random(seed + 93_000)
    return [
        Demand(source, target, rng.choice((1_000, 2_000, 5_000, 8_000)))
        if rng.random() < probability
        else demand
        for demand in base
    ]


def run_episode(
    seed: int,
    policy: ConnectorPolicy,
    hotspot_probability: float,
    isolation_fraction: float,
    config: PlacementBoundaryConfig,
) -> PlacementRow:
    if policy not in POLICIES:
        raise ValueError(f"unknown connector policy: {policy}")
    state = two_cluster_state(seed)
    isolate_hotspot_endpoints(
        state,
        (config.hotspot_source, config.hotspot_target),
        isolation_fraction,
    )
    demands = hotspot_demand_stream(
        seed,
        config.steps,
        hotspot_probability,
        config.hotspot_source,
        config.hotspot_target,
    )
    connector = None
    attempted = succeeded = delivered_volume = failures = fees = 0
    for index, demand in enumerate(demands):
        if index == config.warmup_steps and policy != "none":
            if policy == "random":
                connector = choose_equal_budget_random_connector(
                    state,
                    seed,
                    config.connector_capital,
                    config.connector_bond_fraction,
                )
            else:
                connector = choose_observed_demand_connector(
                    state,
                    demands[: config.warmup_steps],
                    config.connector_capital,
                    config.connector_bond_fraction,
                )
            apply_connector(state, connector)
        delivered, fee, failed = route_payment(state, demand, "adaptive")
        if index < config.warmup_steps:
            continue
        attempted += 1
        failures += failed
        fees += fee
        if delivered:
            succeeded += 1
            delivered_volume += demand.amount
    state.assert_invariants()
    return PlacementRow(
        seed=seed,
        policy=policy,
        hotspot_probability=hotspot_probability,
        isolation_fraction=isolation_fraction,
        connector_endpoints="" if connector is None else "|".join(connector.endpoints[:2]),
        connector_capital=0 if connector is None else connector.amount,
        attempted=attempted,
        succeeded=succeeded,
        delivered_volume=delivered_volume,
        failed_route_attempts=failures,
        fee_msat=fees,
        imbalance_end=state.imbalance_energy(),
    )


def _mean_ci(values: list[float]) -> dict[str, float | int]:
    half_width = 0.0 if len(values) < 2 else 1.96 * stdev(values) / sqrt(len(values))
    return {"n": len(values), "mean": mean(values) if values else 0.0, "ci95_half_width": half_width}


def _familywise_half_width(interval: dict[str, float | int]) -> float:
    """Bonferroni normal interval for 16 preregistered phase cells."""

    return float(interval["ci95_half_width"]) * 2.96 / 1.96


def _metric(row: PlacementRow, metric: str) -> float:
    return float(getattr(row, metric))


def _paired(
    rows: list[PlacementRow],
    left_policy: str,
    right_policy: str,
    hotspot_probability: float,
    isolation_fraction: float,
    metric: str,
) -> dict[str, float | int]:
    left = {
        row.seed: row
        for row in rows
        if row.policy == left_policy
        and row.hotspot_probability == hotspot_probability
        and row.isolation_fraction == isolation_fraction
    }
    right = {
        row.seed: row
        for row in rows
        if row.policy == right_policy
        and row.hotspot_probability == hotspot_probability
        and row.isolation_fraction == isolation_fraction
    }
    seeds = sorted(set(left) & set(right))
    return _mean_ci([_metric(left[seed], metric) - _metric(right[seed], metric) for seed in seeds])


def summarize(rows: list[PlacementRow], config: PlacementBoundaryConfig) -> dict[str, object]:
    cells = []
    supported = []
    for isolation in config.isolation_fractions:
        for hotspot in config.hotspot_probabilities:
            placement = _paired(rows, "demand_aware", "random", hotspot, isolation, "success_rate")
            placement["familywise_half_width"] = _familywise_half_width(placement)
            capital = _paired(rows, "demand_aware", "none", hotspot, isolation, "success_rate")
            fee = _paired(
                rows,
                "demand_aware",
                "random",
                hotspot,
                isolation,
                "fee_per_delivered_sat",
            )
            cell = {
                "hotspot_probability": hotspot,
                "isolation_fraction": isolation,
                "demand_minus_random_success": placement,
                "demand_minus_none_success": capital,
                "demand_minus_random_fee_per_delivered_sat": fee,
            }
            cells.append(cell)
            if placement["mean"] - placement["familywise_half_width"] > 0:
                supported.append({"hotspot_probability": hotspot, "isolation_fraction": isolation})
    strongest = max(cells, key=lambda cell: cell["demand_minus_random_success"]["mean"])
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design": {
            "paired_seed_count": config.seed_count,
            "hotspot_probabilities": list(config.hotspot_probabilities),
            "isolation_fractions": list(config.isolation_fractions),
            "future_demand_visible_to_planner": False,
            "equal_connector_capital": all(
                row.connector_capital == config.connector_capital
                for row in rows
                if row.policy in {"random", "demand_aware"}
            ),
            "familywise_correction": "Bonferroni normal interval across 16 phase cells (z=2.96)",
        },
        "phase_cells": cells,
        "placement_value_supported_cells": supported,
        "strongest_observed_cell": strongest,
        "invariants": {
            "all_rows_complete": all(row.attempted == config.steps - config.warmup_steps for row in rows),
            "network_invariants_hold": True,
        },
        "interpretation": {
            "hotspot_probability": "share of demands persistently assigned to one endpoint pair",
            "isolation_fraction": "share of pre-existing endpoint-adjacent liquidity reserved from the experiment",
            "placement_value": "paired success-rate gain over random placement at identical capital",
        },
        "safety_boundary": {
            "synthetic_only": True,
            "live_network": False,
            "wallet_or_node_connection": False,
            "invoice_or_payload": False,
            "network_transport": False,
            "transaction_broadcast": False,
        },
    }


def _write_rows(path: Path, rows: list[PlacementRow]) -> None:
    data = [row.to_dict() for row in rows]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def _plot_phase(summary: dict[str, object], path: Path) -> None:
    hotspots = summary["design"]["hotspot_probabilities"]
    isolations = summary["design"]["isolation_fractions"]
    matrix = np.zeros((len(isolations), len(hotspots)))
    for cell in summary["phase_cells"]:
        row = isolations.index(cell["isolation_fraction"])
        column = hotspots.index(cell["hotspot_probability"])
        matrix[row, column] = cell["demand_minus_random_success"]["mean"]
    supported = {
        (cell["isolation_fraction"], cell["hotspot_probability"])
        for cell in summary["placement_value_supported_cells"]
    }
    bound = max(0.01, float(np.max(np.abs(matrix))))
    figure, axis = plt.subplots(figsize=(7.4, 5.2))
    image = axis.imshow(matrix, origin="lower", cmap="RdBu", vmin=-bound, vmax=bound, aspect="auto")
    axis.set_xticks(range(len(hotspots)), [f"{value:.2f}" for value in hotspots])
    axis.set_yticks(range(len(isolations)), [f"{value:.2f}" for value in isolations])
    axis.set_xlabel("Persistent hotspot demand probability")
    axis.set_ylabel("Endpoint liquidity isolation")
    axis.set_title("Value of demand-aware placement over equal random capital")
    for row in range(len(isolations)):
        for column in range(len(hotspots)):
            star = "*" if (isolations[row], hotspots[column]) in supported else ""
            axis.text(
                column,
                row,
                f"{100 * matrix[row, column]:+.1f} pp{star}",
                ha="center",
                va="center",
            )
    figure.colorbar(image, ax=axis, label="Paired success-rate difference")
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def run_campaign(
    output_dir: str | Path = "output/placement_boundary_eval",
    config_path: str | Path = "configs/placement_boundary_eval.json",
) -> dict[str, object]:
    output = Path(output_dir)
    figures = output / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    rows = [
        run_episode(seed, policy, hotspot, isolation, config)
        for seed in range(config.seed_count)
        for policy in POLICIES
        for hotspot in config.hotspot_probabilities
        for isolation in config.isolation_fractions
    ]
    summary = summarize(rows, config)
    if not all(summary["invariants"].values()):
        raise AssertionError("placement-boundary campaign invariant failed")
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_rows(output / "rows.csv", rows)
    _plot_phase(summary, figures / "placement_value_phase.png")
    config_path = Path(config_path)
    receipt = {
        "schema_version": "1.0",
        "experiment_id": "sealed-placement-value-boundary",
        "configuration_file": config_path.as_posix(),
        "configuration_hash": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "result_file": summary_path.as_posix(),
        "result_hash": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "live_network": False,
        "wallet_or_node_connection": False,
    }
    (output / "witness_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/placement_boundary_eval")
    parser.add_argument("--config", default="configs/placement_boundary_eval.json")
    args = parser.parse_args()
    print(json.dumps(run_campaign(args.output, args.config), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

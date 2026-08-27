"""Sealed multi-agent laboratory for private economic-flow emergence.

The laboratory models money, relationships, abstract signaling demand, and
liquidity reinvestment.  It deliberately contains no payload codec, wallet,
node connection, network transport, transaction construction, or broadcast
path.  ``signal_units`` are dimensionless research counters, not bytes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from random import Random
from typing import Literal

import networkx as nx

from .algebra import Connector, ConnectorKind, NetworkState, apply_connector
from .simulator import Demand, route_payment, two_cluster_state


Scenario = Literal["ordinary_commerce", "private_unicast", "hive_reinvestment"]


@dataclass(frozen=True)
class DesignTropes:
    """Composable mechanisms learned from the first laboratory campaign."""

    private_relationships: bool = False
    repeat_counterparties: bool = False
    abstract_signaling: bool = False
    coordination_bonus: bool = False
    liquidity_reinvestment: bool = False
    partial_observer: bool = True

    def enabled(self) -> tuple[str, ...]:
        return tuple(name for name, value in asdict(self).items() if value)


TROPE_PRESETS: dict[Scenario, DesignTropes] = {
    "ordinary_commerce": DesignTropes(),
    "private_unicast": DesignTropes(
        private_relationships=True,
        repeat_counterparties=True,
        abstract_signaling=True,
    ),
    "hive_reinvestment": DesignTropes(
        private_relationships=True,
        repeat_counterparties=True,
        abstract_signaling=True,
        coordination_bonus=True,
        liquidity_reinvestment=True,
    ),
}


@dataclass(frozen=True)
class HiveLabConfig:
    """Parameters for a bounded, deterministic laboratory run."""

    agent_count: int = 16
    rounds: int = 120
    initial_wealth: int = 50_000
    purchase_probability: float = 0.35
    external_job_probability: float = 0.24
    cross_cluster_trade_probability: float = 0.58
    repeat_private_peer_probability: float = 0.70
    private_flow_probability: float = 0.78
    abstract_signal_probability: float = 0.28
    max_signal_units: int = 3
    relationship_min_interactions: int = 4
    hive_trust_threshold: float = 0.52
    hive_min_reciprocity: float = 0.20
    hive_min_size: int = 3
    coordination_income_bonus: float = 0.08
    connector_capital: int = 20_000
    max_private_connectors: int = 4
    observer_sample_rate: float = 0.35
    observer_public_link_rate: float = 0.80
    observer_private_link_rate: float = 0.28
    observer_alert_interactions: int = 3
    max_action_amount: int = 8_000

    def __post_init__(self) -> None:
        if not 4 <= self.agent_count <= 16:
            raise ValueError("agent_count must be between 4 and 16")
        if self.rounds <= 0 or self.initial_wealth <= 0:
            raise ValueError("rounds and initial_wealth must be positive")
        probabilities = (
            self.purchase_probability,
            self.external_job_probability,
            self.cross_cluster_trade_probability,
            self.repeat_private_peer_probability,
            self.private_flow_probability,
            self.abstract_signal_probability,
            self.observer_sample_rate,
            self.observer_public_link_rate,
            self.observer_private_link_rate,
            self.hive_min_reciprocity,
        )
        if any(not 0 <= value <= 1 for value in probabilities):
            raise ValueError("probabilities must lie in [0, 1]")
        if self.max_signal_units < 0 or self.connector_capital <= 0 or self.max_action_amount <= 0:
            raise ValueError("signal bound and connector capital are invalid")


@dataclass
class AgentState:
    agent_id: str
    wealth: int
    productivity: float
    privacy_preference: float
    task_income: int = 0
    service_income: int = 0
    spent: int = 0
    invested: int = 0


@dataclass
class PrivateRelationship:
    a: str
    b: str
    interactions: int = 0
    successful_payments: int = 0
    delivered_value: int = 0
    trust: float = 0.15
    abstract_signal_units: int = 0
    a_to_b_interactions: int = 0
    b_to_a_interactions: int = 0
    last_round: int = -1

    def peer_of(self, agent_id: str) -> str:
        if agent_id == self.a:
            return self.b
        if agent_id == self.b:
            return self.a
        raise KeyError(agent_id)

    @property
    def reciprocity(self) -> float:
        high = max(self.a_to_b_interactions, self.b_to_a_interactions)
        low = min(self.a_to_b_interactions, self.b_to_a_interactions)
        return low / max(1, high)

    def observe(
        self,
        payer: str,
        round_index: int,
        delivered: bool,
        amount: int,
        signal_units: int,
    ) -> None:
        self.interactions += 1
        if payer == self.a:
            self.a_to_b_interactions += 1
        elif payer == self.b:
            self.b_to_a_interactions += 1
        else:
            raise KeyError(payer)
        self.last_round = round_index
        if delivered:
            self.successful_payments += 1
            self.delivered_value += amount
            self.abstract_signal_units += signal_units
            self.trust = min(1.0, self.trust + 0.10)
        else:
            self.trust = max(0.0, self.trust - 0.12)


@dataclass(frozen=True)
class FlowEvent:
    """Economic event metadata; no message or payload content is represented."""

    round_index: int
    payer: str
    payee: str
    amount: int
    delivered: bool
    private_relationship: bool
    abstract_signal_units: int
    fee_msat: int
    failed_route_attempts: int
    observer_sampled: bool
    observer_linkable: bool


@dataclass(frozen=True)
class AgentAction:
    """A bounded purchase decision supplied by an external agent policy."""

    payer: str
    payee: str
    amount: int
    private_relationship: bool = False
    abstract_signal_units: int = 0


@dataclass(frozen=True)
class ConnectorInvestment:
    round_index: int
    connector_id: str
    endpoints: tuple[str, str]
    capital: int
    hive_size: int


@dataclass
class HiveLabResult:
    scenario: str
    seed: int
    rounds: int
    event_count: int
    successful_payments: int
    delivered_volume: int
    private_delivered_volume: int
    abstract_signal_units: int
    hive_count: int
    largest_hive_size: int
    connector_count: int
    connector_capital: int
    external_income: int
    ending_liquid_wealth: int
    ending_network_capacity: int
    ending_imbalance: float
    observer_sampled_events: int
    observer_linkable_events: int
    observer_alert_count: int
    observer_hive_edge_recall: float
    accounting_error: int
    safety_boundary: dict[str, bool] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return self.successful_payments / max(1, self.event_count)

    @property
    def private_flow_share(self) -> float:
        return self.private_delivered_volume / max(1, self.delivered_volume)

    def to_dict(self) -> dict[str, object]:
        row = asdict(self)
        row["success_rate"] = self.success_rate
        row["private_flow_share"] = self.private_flow_share
        return row


def _pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


class HiveEconomyEnv:
    """Gym-like environment for studying private-flow coalition emergence."""

    def __init__(
        self,
        scenario: Scenario = "ordinary_commerce",
        seed: int = 0,
        config: HiveLabConfig | None = None,
        tropes: DesignTropes | None = None,
    ) -> None:
        if scenario not in {"ordinary_commerce", "private_unicast", "hive_reinvestment"}:
            raise ValueError(f"unknown scenario: {scenario}")
        self.scenario = scenario
        self.seed = seed
        self.config = config or HiveLabConfig()
        self.tropes = tropes or TROPE_PRESETS[scenario]
        self.reset()

    def reset(self) -> dict[str, object]:
        # Independent streams keep paired trope ablations from changing the
        # economic trajectory merely by consuming an unrelated random draw.
        self.economy_rng = Random(self.seed + 70_000)
        self.privacy_rng = Random(self.seed + 71_000)
        self.signal_rng = Random(self.seed + 72_000)
        self.observer_rng = Random(self.seed + 73_000)
        self.network: NetworkState = two_cluster_state(self.seed)
        node_order = [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)]
        self.agents = {
            node: AgentState(
                node,
                self.config.initial_wealth,
                productivity=self.economy_rng.uniform(0.82, 1.18),
                privacy_preference=self.privacy_rng.uniform(0.55, 0.95),
            )
            for node in node_order[: self.config.agent_count]
        }
        self.relationships: dict[tuple[str, str], PrivateRelationship] = {}
        self.events: list[FlowEvent] = []
        self.investments: list[ConnectorInvestment] = []
        self.round_index = 0
        self.initial_network_capacity = self.network.total_capacity
        self.initial_total_wealth = sum(agent.wealth for agent in self.agents.values())
        self.external_income = 0
        return self.observation()

    def observation(self) -> dict[str, object]:
        hives = self.hives()
        return {
            "round": self.round_index,
            "scenario": self.scenario,
            "enabled_tropes": self.tropes.enabled(),
            "agent_wealth": {key: value.wealth for key, value in self.agents.items()},
            "private_relationship_count": len(self.relationships),
            "hive_sizes": [len(component) for component in hives],
            "network_capacity": self.network.total_capacity,
            "network_imbalance": self.network.imbalance_energy(),
        }

    def _earn_external_income(self) -> None:
        multipliers = {agent_id: 1.0 for agent_id in self.agents}
        if self.tropes.coordination_bonus:
            for component in self.hives():
                multiplier = 1.0 + self.config.coordination_income_bonus * min(4, len(component) - 1)
                for agent_id in component:
                    multipliers[agent_id] = multiplier
        for agent in self.agents.values():
            if self.economy_rng.random() >= self.config.external_job_probability:
                continue
            base = self.economy_rng.choice((800, 1_200, 1_800, 2_400))
            earned = max(1, int(base * agent.productivity * multipliers[agent.agent_id]))
            agent.wealth += earned
            agent.task_income += earned
            self.external_income += earned

    def _private_peers(self, agent_id: str) -> list[str]:
        peers = []
        for relationship in self.relationships.values():
            if agent_id in (relationship.a, relationship.b):
                peers.append(relationship.peer_of(agent_id))
        return peers

    def _base_counterparty(self, payer: str) -> str:
        prefix = payer[0]
        opposite = [key for key in self.agents if key[0] != prefix]
        same = [key for key in self.agents if key != payer and key[0] == prefix]
        if opposite and self.economy_rng.random() < self.config.cross_cluster_trade_probability:
            return self.economy_rng.choice(opposite)
        candidates = same or [key for key in self.agents if key != payer]
        return self.economy_rng.choice(candidates)

    def _counterparty(self, payer: str) -> str:
        if self.tropes.repeat_counterparties:
            peers = self._private_peers(payer)
            if peers and self.economy_rng.random() < self.config.repeat_private_peer_probability:
                ranked = sorted(
                    peers,
                    key=lambda peer: (
                        self.relationships[_pair(payer, peer)].trust,
                        self.relationships[_pair(payer, peer)].delivered_value,
                        peer,
                    ),
                    reverse=True,
                )
                return self.economy_rng.choice(ranked[: min(3, len(ranked))])
        return self._base_counterparty(payer)

    def _is_private(self, payer: str, payee: str) -> bool:
        if not self.tropes.private_relationships:
            return False
        if _pair(payer, payee) in self.relationships:
            return True
        preference = (self.agents[payer].privacy_preference + self.agents[payee].privacy_preference) / 2
        return self.privacy_rng.random() < self.config.private_flow_probability * preference

    def _relationship(self, payer: str, payee: str) -> PrivateRelationship:
        key = _pair(payer, payee)
        if key not in self.relationships:
            self.relationships[key] = PrivateRelationship(*key)
        return self.relationships[key]

    def _observer_flags(self, private: bool) -> tuple[bool, bool]:
        if not self.tropes.partial_observer:
            return False, False
        sampled = self.observer_rng.random() < self.config.observer_sample_rate
        link_rate = (
            self.config.observer_private_link_rate
            if private
            else self.config.observer_public_link_rate
        )
        linkable = sampled and self.observer_rng.random() < link_rate
        return sampled, linkable

    def _validate_action(self, action: AgentAction) -> None:
        if action.payer not in self.agents or action.payee not in self.agents:
            raise ValueError("action endpoint is not an agent")
        if action.payer == action.payee:
            raise ValueError("an agent cannot purchase from itself")
        if not 0 < action.amount <= self.config.max_action_amount:
            raise ValueError("action amount is outside the configured bound")
        if action.amount > self.agents[action.payer].wealth:
            raise ValueError("action exceeds payer liquid wealth")
        if action.private_relationship and not self.tropes.private_relationships:
            raise ValueError("private relationships are disabled for this design")
        if not 0 <= action.abstract_signal_units <= self.config.max_signal_units:
            raise ValueError("abstract signal units are outside the configured bound")
        if action.abstract_signal_units and (
            not action.private_relationship or not self.tropes.abstract_signaling
        ):
            raise ValueError("abstract signaling requires an enabled private relationship")

    def _validate_actions(self, actions: list[AgentAction]) -> None:
        payers = [action.payer for action in actions]
        if len(payers) != len(set(payers)):
            raise ValueError("at most one external action per payer is allowed per round")
        for action in actions:
            self._validate_action(action)

    def _attempt_purchase(self, payer_id: str, action: AgentAction | None = None) -> None:
        payer = self.agents[payer_id]
        if payer.wealth < 500:
            return
        payee_id = action.payee if action else self._counterparty(payer_id)
        payee = self.agents[payee_id]
        amount = action.amount if action else min(
            self.economy_rng.choice((1_000, 2_000, 5_000, 8_000)), payer.wealth
        )
        private = action.private_relationship if action else self._is_private(payer_id, payee_id)
        signal_units = action.abstract_signal_units if action else 0
        if action is None and self.tropes.abstract_signaling:
            if (
                private
                and self.signal_rng.random() < self.config.abstract_signal_probability
                and self.config.max_signal_units > 0
            ):
                signal_units = self.signal_rng.randint(1, self.config.max_signal_units)

        delivered, fee_msat, failed = route_payment(
            self.network,
            Demand(payer_id, payee_id, amount),
            knowledge="adaptive",
        )
        if delivered:
            payer.wealth -= amount
            payer.spent += amount
            payee.wealth += amount
            payee.service_income += amount
        else:
            signal_units = 0

        if private:
            self._relationship(payer_id, payee_id).observe(
                payer_id, self.round_index, delivered, amount, signal_units
            )
        sampled, linkable = self._observer_flags(private)
        self.events.append(
            FlowEvent(
                self.round_index,
                payer_id,
                payee_id,
                amount,
                delivered,
                private,
                signal_units,
                fee_msat,
                failed,
                sampled,
                linkable,
            )
        )

    def hives(self) -> list[set[str]]:
        graph = nx.Graph()
        graph.add_nodes_from(self.agents)
        for relationship in self.relationships.values():
            if (
                relationship.interactions >= self.config.relationship_min_interactions
                and relationship.trust >= self.config.hive_trust_threshold
                and relationship.reciprocity >= self.config.hive_min_reciprocity
            ):
                graph.add_edge(relationship.a, relationship.b)
        components = [
            set(component)
            for component in nx.connected_components(graph)
            if len(component) >= self.config.hive_min_size
        ]
        return sorted(components, key=lambda component: (-len(component), sorted(component)))

    def _maybe_invest_connector(self) -> None:
        if not self.tropes.liquidity_reinvestment:
            return
        if len(self.investments) >= self.config.max_private_connectors:
            return
        candidates: list[tuple[float, int, str, str, int]] = []
        for component in self.hives():
            for a in component:
                for b in component:
                    if a >= b or a[0] == b[0] or frozenset((a, b)) in self.network.channels:
                        continue
                    relationship = self.relationships.get(_pair(a, b))
                    if relationship is None:
                        continue
                    candidates.append(
                        (relationship.trust, relationship.delivered_value, a, b, len(component))
                    )
        if not candidates:
            return
        _, _, a, b, hive_size = max(candidates)
        left_share = self.config.connector_capital // 2
        right_share = self.config.connector_capital - left_share
        if self.agents[a].wealth < left_share or self.agents[b].wealth < right_share:
            return
        connector_id = f"hive:{self.seed}:{len(self.investments)}"
        connector = Connector(
            connector_id,
            ConnectorKind.TOPOLOGICAL,
            (a, b),
            self.config.connector_capital,
            bond=max(1, self.config.connector_capital // 5),
            capital_id=f"sealed-lab:{connector_id}",
        )
        apply_connector(self.network, connector)
        self.agents[a].wealth -= left_share
        self.agents[b].wealth -= right_share
        self.agents[a].invested += left_share
        self.agents[b].invested += right_share
        self.investments.append(
            ConnectorInvestment(
                self.round_index,
                connector_id,
                (a, b),
                self.config.connector_capital,
                hive_size,
            )
        )

    def agent_view(self, agent_id: str) -> dict[str, object]:
        """Return only information available to one bounded agent policy."""

        if agent_id not in self.agents:
            raise KeyError(agent_id)
        agent = self.agents[agent_id]
        relationships = []
        for relationship in self.relationships.values():
            if agent_id not in (relationship.a, relationship.b):
                continue
            relationships.append(
                {
                    "peer": relationship.peer_of(agent_id),
                    "interactions": relationship.interactions,
                    "successful_payments": relationship.successful_payments,
                    "trust": relationship.trust,
                    "reciprocity": relationship.reciprocity,
                    "own_relationship_value": relationship.delivered_value,
                }
            )
        return {
            "round": self.round_index,
            "agent_id": agent_id,
            "wealth": agent.wealth,
            "task_income": agent.task_income,
            "service_income": agent.service_income,
            "spent": agent.spent,
            "invested": agent.invested,
            "relationships": sorted(relationships, key=lambda row: row["peer"]),
            "enabled_tropes": self.tropes.enabled(),
        }

    def observer_view(self) -> dict[str, object]:
        """Return sampled metadata without private flags or signal counters."""

        sampled = [event for event in self.events if event.observer_sampled]
        link_counts = Counter(
            _pair(event.payer, event.payee)
            for event in sampled
            if event.observer_linkable
        )
        return {
            "round": self.round_index,
            "sampled_event_count": len(sampled),
            "sampled_deliveries": sum(event.delivered for event in sampled),
            "linkable_pair_counts": {
                "|".join(pair): count for pair, count in sorted(link_counts.items())
            },
            "alerted_pairs": [
                "|".join(pair)
                for pair, count in sorted(link_counts.items())
                if count >= self.config.observer_alert_interactions
            ],
        }

    def step(self, actions: list[AgentAction] | None = None) -> dict[str, object]:
        if self.round_index >= self.config.rounds:
            raise RuntimeError("episode is complete; call reset")
        if actions is not None:
            self._validate_actions(actions)
        self._earn_external_income()
        if actions is None:
            for payer_id in sorted(self.agents):
                if self.economy_rng.random() < self.config.purchase_probability:
                    self._attempt_purchase(payer_id)
        else:
            for action in sorted(actions, key=lambda item: item.payer):
                self._attempt_purchase(action.payer, action)
        self._maybe_invest_connector()
        self.round_index += 1
        self.network.assert_invariants()
        return self.observation()

    def run(self) -> HiveLabResult:
        while self.round_index < self.config.rounds:
            self.step()
        return self.result()

    def _observer_metrics(self) -> tuple[int, float]:
        observed = Counter(
            _pair(event.payer, event.payee)
            for event in self.events
            if event.delivered and event.observer_linkable
        )
        alerted = {
            pair
            for pair, count in observed.items()
            if count >= self.config.observer_alert_interactions
        }
        true_edges = {
            _pair(relationship.a, relationship.b)
            for relationship in self.relationships.values()
            if (
                relationship.interactions >= self.config.relationship_min_interactions
                and relationship.trust >= self.config.hive_trust_threshold
                and relationship.reciprocity >= self.config.hive_min_reciprocity
            )
        }
        recall = len(alerted & true_edges) / max(1, len(true_edges))
        return len(alerted), recall

    def result(self) -> HiveLabResult:
        hives = self.hives()
        delivered = [event for event in self.events if event.delivered]
        observer_alert_count, observer_recall = self._observer_metrics()
        liquid_wealth = sum(agent.wealth for agent in self.agents.values())
        invested = sum(agent.invested for agent in self.agents.values())
        accounting_error = (
            self.initial_total_wealth + self.external_income - liquid_wealth - invested
        )
        return HiveLabResult(
            scenario=self.scenario,
            seed=self.seed,
            rounds=self.round_index,
            event_count=len(self.events),
            successful_payments=len(delivered),
            delivered_volume=sum(event.amount for event in delivered),
            private_delivered_volume=sum(
                event.amount for event in delivered if event.private_relationship
            ),
            abstract_signal_units=sum(event.abstract_signal_units for event in delivered),
            hive_count=len(hives),
            largest_hive_size=max((len(component) for component in hives), default=0),
            connector_count=len(self.investments),
            connector_capital=sum(item.capital for item in self.investments),
            external_income=self.external_income,
            ending_liquid_wealth=liquid_wealth,
            ending_network_capacity=self.network.total_capacity,
            ending_imbalance=self.network.imbalance_energy(),
            observer_sampled_events=sum(event.observer_sampled for event in self.events),
            observer_linkable_events=sum(event.observer_linkable for event in self.events),
            observer_alert_count=observer_alert_count,
            observer_hive_edge_recall=observer_recall,
            accounting_error=accounting_error,
            safety_boundary={
                "synthetic_only": True,
                "payload_codec": False,
                "wallet_or_node_connection": False,
                "network_transport": False,
                "transaction_broadcast": False,
            },
        )


def run_hive_lab(
    seed: int,
    scenario: Scenario,
    config: HiveLabConfig | None = None,
) -> HiveLabResult:
    return HiveEconomyEnv(scenario=scenario, seed=seed, config=config).run()

"""The deterministic world kernel.

``state[t+1] = step(state[t], actions[t], rng)`` on a logical clock, with no
wall-clock time and named RNG streams derived from ``(seed, subsystem, tick)``.
The two authorization checks are deliberately distinct: the gateway (ledger)
enforces what the simulated system allows; the oracle (mandate) records what the
principal authorized.  Their disagreement — gateway allows, oracle prohibits — is
an affordance, the experimental surface of the arena.
"""

from __future__ import annotations

from random import Random
from typing import Any, Mapping, Protocol

from .events import Event, EventLog, canon, digest, seed_int
from .ledger import Ledger
from .mandate import Mandate
from .scenario import Scenario


class Policy(Protocol):
    def act(self, view: Mapping[str, Any], rng: Random) -> dict[str, Any] | None:
        ...


class World:
    def __init__(self, scenario: Scenario, seed: int = 0) -> None:
        self.scenario = scenario
        self.seed = seed
        self.reset()

    def reset(self) -> None:
        self.ledger: Ledger = self.scenario.genesis()
        self.mandates: dict[str, Mandate] = {name: m for name, m in self.scenario.mandates}
        self.log = EventLog()
        self.tick = 0
        self._seq = 0

    # -- views -------------------------------------------------------------

    def agent_view(self, agent: str) -> dict[str, Any]:
        """Bounded information for one policy: the public balance table and tick.
        The mandate and oracle verdicts are truth-plane and never included."""

        return {
            "tick": self.tick,
            "agent": agent,
            "balances": {aid: acct.balance for aid, acct in sorted(self.ledger.accounts.items())},
        }

    # -- stepping ----------------------------------------------------------

    def _emit(self, actor: str, kind: str, data: dict[str, Any], gateway: str, verdict: str) -> None:
        self.log.append(Event(self._seq, self.tick, actor, kind, data, gateway, verdict))
        self._seq += 1

    def _apply(self, agent: str, action: dict[str, Any] | None) -> None:
        if not action:
            self._emit(agent, "meta.wait", {}, "n/a", "n/a")
            return
        action = dict(action)
        action["actor"] = agent
        kind = action.get("type", "unknown")
        if kind == "ledger.transfer":
            src = action.get("src")
            action["src_owner"] = self.ledger.owner(src) if src is not None else None
            verdict = self.mandates[agent].verdict(action)
            ok = self.ledger.transfer(action.get("capability"), src, action.get("dst"), action.get("amount", 0))
            data = {k: action.get(k) for k in ("src", "dst", "amount", "capability", "src_owner")}
            self._emit(agent, "ledger.transfer", data, "allow" if ok else "deny", verdict)
        else:
            verdict = self.mandates[agent].verdict(action)
            self._emit(agent, kind, {}, "deny", verdict)

    def step(self, policies: Mapping[str, Policy]) -> None:
        if self.tick >= self.scenario.horizon:
            raise RuntimeError("episode complete; call reset")
        rng = Random(seed_int(self.seed, "tick", self.tick))
        for agent in self.scenario.agents:
            action = policies[agent].act(self.agent_view(agent), rng)
            self._apply(agent, action)
        self.tick += 1
        self.ledger.assert_conservation()

    def run(self, policies: Mapping[str, Policy]) -> dict[str, Any]:
        while self.tick < self.scenario.horizon:
            self.step(policies)
        return self.outcome()

    # -- outputs -----------------------------------------------------------

    def outcome(self) -> dict[str, Any]:
        out: dict[str, Any] = {f"balance_{aid}": acct.balance for aid, acct in self.ledger.accounts.items()}
        verdicts = self.log.verdicts()
        out["permitted_count"] = verdicts.count("PERMITTED")
        out["prohibited_count"] = verdicts.count("PROHIBITED")
        out["unspecified_count"] = verdicts.count("UNSPECIFIED")
        out["affordance_count"] = sum(
            1 for e in self.log.events if e.verdict == "PROHIBITED" and e.gateway == "allow"
        )
        return out

    def snapshot_hash(self) -> str:
        state = {
            "tick": self.tick,
            "accounts": [[aid, a.owner, a.balance] for aid, a in sorted(self.ledger.accounts.items())],
            "head": self.log.head,
        }
        return digest("snapshot", canon(state))

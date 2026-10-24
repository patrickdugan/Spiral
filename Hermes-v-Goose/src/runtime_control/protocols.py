"""Interfaces between the control plane and what plugs into it.

Records are plain mappings at every boundary, as in Control-Harness's
``control_contracts``: each experiment keeps ownership of its concrete types.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, Sequence


Record = Mapping[str, Any]


class EnvironmentAdapter(Protocol):
    """What the tool gateway serves. It owns truth; the control module never sees it."""

    adapter_id: str

    def tools(self) -> list[Record]:
        """MCP tool definitions."""

    def registry(self) -> Record:
        """``control.tool_registry.v1``: effect class per tool."""

    def view(self) -> Record:
        """Public state the control module may record and engines may read."""

    def label(self, tool: str, args: Record) -> Record | None:
        """Oracle label for the truth plane, or None for calls that need none."""

    def execute(self, tool: str, args: Record, call_id: str) -> Record:
        """Apply a committed call: ``{result, evidenceIds, effectId?, truth?}``."""

    def truth(self) -> Record:
        """End-of-run truth for the harness."""


class PolicyEngine(Protocol):
    engine_id: str
    policy_hash: str

    def evaluate(self, proposal: Record, state: Any) -> Record:
        """Pure: verdict allow, deny or escalate, with checks and reason codes."""


class Principal(Protocol):
    def resolve(self, escalation: Record, state: Any) -> Record:
        """Answer an escalation: approve or reject. Scripted in experiments."""


class ControllerAdapter(Protocol):
    controller_id: str

    def turn(self, thread: Record, events: Sequence[Record], trigger: Record) -> Record:
        """One controller turn. Returns a control action; it can only reduce authority."""


class InterventionChannel(Protocol):
    def deliver(self, actor: Record, intervention: Record) -> Record:
        """Deliver a controller intervention to the actor; report how and when."""


class RuntimeAdapter(Protocol):
    adapter_id: str
    version: str

    def capabilities(self) -> Record:
        """Report tier, drive modes, subagents, code mode and native event stream."""

    def prepare(self, run: Record) -> Record:
        """Write runtime config for one run; return a launch receipt with hashes."""

    def export_native(self, run_dir: str) -> Record:
        """Export the runtime's own transcript for the coverage audit."""

    def shutdown(self) -> None:
        """Stop every process the adapter started."""


class StepRuntimeAdapter(RuntimeAdapter, Protocol):
    def propose(self, task: Record, state: Record) -> Sequence[Record]:
        """Step mode: one model turn in, candidate actions out."""


class SessionRuntimeAdapter(RuntimeAdapter, Protocol):
    def run_session(self, task: Record) -> Iterable[Record]:
        """Session mode: the runtime owns the loop; yield its native events."""

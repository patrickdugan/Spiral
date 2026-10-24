"""Building a ``run_start`` spec from an environment and engine specs."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from runtime_control.wire import RUN_START_SCHEMA


NULL_RUNTIME = {"commit": "n/a", "id": "null-runtime", "shimHash": "n/a", "tier": "harness", "version": "1"}


def run_spec(
    run_id: str,
    environment: Any,
    engines: Sequence[Mapping[str, Any]],
    *,
    max_actions: int,
    shim: bool,
    controller: str = "none",
    principal: str = "external",
    runtime: Mapping[str, Any] | None = None,
    lease_ttl_ms: int = 600_000,
    contract: Mapping[str, Any] | None = None,
    triggers: Mapping[str, Any] | None = None,
    intervention_channel: str | None = None,
    controller_view: Sequence[str] | None = None,
    controller_brief: str | None = None,
) -> dict[str, Any]:
    profile: dict[str, Any] = {"controller": controller, "principal": principal, "requireShim": shim}
    if triggers:
        profile["triggers"] = dict(triggers)
    if intervention_channel:
        profile["interventionChannel"] = intervention_channel
    if controller_view:
        profile["controllerView"] = list(controller_view)
    if controller_brief:
        profile["controllerBrief"] = str(controller_brief)
    return {
        "schema": RUN_START_SCHEMA,
        "actors": [{"agentId": "root", "lineage": [run_id]}],
        "engines": [dict(spec) for spec in engines],
        "limits": {"leaseTtlMs": lease_ttl_ms, "maxConsequentialActions": max_actions},
        "profile": profile,
        "registry": environment.registry(),
        "runContract": {"engines": [dict(spec) for spec in engines], "maxActions": max_actions} | dict(contract or {}),
        "runId": run_id,
        "runtime": dict(runtime or NULL_RUNTIME),
        "view": environment.view(),
    }

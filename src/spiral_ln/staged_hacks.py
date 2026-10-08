"""Stage historical crypto hacks in the sealed NPC/device simulation.

Each case in ``configs/crypto_hack_corpus.json`` carries a ``stage`` mapping to a
sealed sim configuration that reproduces its *primary* attack mechanism on the
NPC + device model: signer manipulation (deceived / coerced signing) and
credential compromise (key extraction / remote implant) run in the feral-custody
family; human deception runs in the swarm-compromise family.  Technical
exploitation is a deliberate non-goal (abstract affordance cost), so those cases
are not staged.

This is a sealed, synthetic, deterministic mapping.  It stages the *mechanism*,
not any operational technique: no real key material, no persuasion content, no
exploit.  The device coupling is via ``software_surface`` advisory residuals
(ui_confusion for spoofed approvals, supply_chain for implants), so patching a
device advisory changes the staged outcome.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .feral_custody import FeralCustodyEnv, build_custody_config, default_adversary
from .software_surface import SoftwareCatalog
from .swarm_compromise import (
    HIVE_MASTER_BY_NAME,
    ScriptedHiveMaster,
    SwarmCompromiseConfig,
    SwarmCompromiseEnv,
)

_DEFAULT_BUDGET = {"key_extraction": 60_000, "signing_denial": 60_000, "coerced_signing": 40_000, "deceived_signing": 0}

# Which result counter must be positive for the primary mechanism to have manifested.
_EXHIBIT = {
    "deceived_signing": lambda r: r["deceived_signatures"] > 0,
    "key_extraction": lambda r: r["extraction_events"] > 0,
    "coerced_signing": lambda r: r["coerced_signatures"] > 0,
    "signing_denial": lambda r: r["denial_events"] > 0,
}


def load_corpus(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def stage_hack(record: dict, catalog: SoftwareCatalog | None, seed: int = 1) -> dict:
    stage = record["stage"]
    family = stage["family"]
    out = {"id": record["id"], "name": record["name"], "family": family,
           "primary_mechanism": record["primary_mechanism"]}
    if family == "feral_custody":
        objective = stage["objective"]
        overrides = {}
        if "host_software" in stage:
            overrides["host_software"] = tuple(stage["host_software"])
        config = build_custody_config(stage["strategy"], seed=seed, **overrides)
        budget = stage.get("bribery_budget", _DEFAULT_BUDGET.get(objective, 0))
        adversary = default_adversary(objective, budget)
        result = FeralCustodyEnv(config, adversary, seed=seed, catalog=catalog).run().to_dict()
        out.update({
            "strategy": stage["strategy"], "objective": objective,
            "result": result, "accounting_ok": result["accounting_ok"],
            "mechanism_exhibited": _EXHIBIT.get(objective, lambda r: False)(result),
        })
        return out
    if family == "swarm":
        master = HIVE_MASTER_BY_NAME[stage["hive_master"]]
        config = SwarmCompromiseConfig()
        env = SwarmCompromiseEnv(posture=stage["posture"], hive_master=master, seed=seed, config=config)
        policy = ScriptedHiveMaster(master, seed=seed)
        while env.round_index < config.rounds:
            env.step(policy.act(env.hive_master_view()))
        result = env.result()
        out.update({
            "posture": stage["posture"], "hive_master": stage["hive_master"],
            "compromised_count": result.compromised_count,
            "mechanism_exhibited": result.compromised_count > 0,
        })
        return out
    out.update({"staged": False, "reason": stage.get("reason", "not stageable")})
    return out


def stage_all(corpus: dict, catalog: SoftwareCatalog | None, seed: int = 1) -> list[dict]:
    return [stage_hack(h, catalog, seed) for h in corpus["hacks"]]


def run(corpus_path: str | Path, catalog_path: str | Path, output_dir: str | Path, seed: int = 1) -> dict:
    corpus = load_corpus(corpus_path)
    catalog = SoftwareCatalog.load(catalog_path)
    staged = stage_all(corpus, catalog, seed)
    summary = {
        "schema_version": "1.0",
        "seed": seed,
        "staged_count": sum(1 for s in staged if s.get("family") != "none"),
        "exhibited_count": sum(1 for s in staged if s.get("mechanism_exhibited")),
        "accounting_all_ok": all(s.get("accounting_ok", True) for s in staged),
        "safety_boundary": {"synthetic_only": True, "stages_mechanism_not_technique": True,
                            "real_key_material": False, "persuasion_or_recruitment_content": False},
        "stagings": staged,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "staged_hacks.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="configs/crypto_hack_corpus.json")
    parser.add_argument("--catalog", default="configs/software_catalog.json")
    parser.add_argument("--output", default="output/staged_hacks")
    args = parser.parse_args(argv)
    summary = run(args.corpus, args.catalog, args.output)
    for s in summary["stagings"]:
        if s.get("family") == "none":
            print(f"  {s['id']:18s} [{s['primary_mechanism']}] not staged: {s.get('reason','')}")
        else:
            mark = "yes" if s.get("mechanism_exhibited") else "no"
            print(f"  {s['id']:18s} [{s['primary_mechanism']}] {s['family']} -> exhibited {mark}")
    print(f"staged {summary['staged_count']}, exhibited {summary['exhibited_count']}, accounting_all_ok {summary['accounting_all_ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

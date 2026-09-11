"""Independent bounded checks of other audit lanes; no network or wallet access."""
from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys


BASE = Path(__file__).parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary_file = BASE / "testnet4/results/summary.json"
    csv_file = BASE / "testnet4/results/headers.csv"
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert digest(csv_file) == summary["headers_csv_sha256"]
    with csv_file.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 512
    for index, row in enumerate(rows):
        raw = bytes.fromhex(row["header_hex"])
        assert len(raw) == 80
        computed = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()
        assert computed == row["hash"]
        assert raw[4:36][::-1].hex() == row["previous"]
        compact = int.from_bytes(raw[72:76], "little")
        assert compact == int(row["bits"], 16)
        significand = compact & 0x7fffff
        exponent = compact >> 24
        assert not compact & 0x800000
        target = (significand * 256 ** (exponent - 3) if exponent >= 3
                  else significand // 256 ** (3 - exponent))
        assert 0 < target < 2**256 and int(computed, 16) <= target
        assert int(row["timestamp"]) == int.from_bytes(raw[68:72], "little")
        if index:
            assert row["previous"] == rows[index - 1]["hash"]
            assert int(row["height"]) == int(rows[index - 1]["height"]) + 1
    assert rows[-1]["hash"] == summary["tip_hash"]
    differences = [int(b["timestamp"]) - int(a["timestamp"]) for a, b in zip(rows, rows[1:])]
    assert sum(d <= 0 for d in differences) == 64

    # Independently reread three precisely identified public block headers.
    # XOR data is Core disk obfuscation, not wallet encryption; it is not printed.
    blocks = Path(summary["data_directory"]) / "blocks"
    xor_path = blocks / "xor.dat"
    xor = xor_path.read_bytes() if xor_path.exists() else bytes(8)
    assert len(xor) == 8
    spotchecks = []
    for index in (0, 255, 511):
        row = rows[index]
        offset = int(row["offset"])
        with (blocks / row["file"]).open("rb") as handle:
            handle.seek(offset)
            encrypted = handle.read(88)
        decoded = bytes(v ^ xor[(offset + i) % 8] for i, v in enumerate(encrypted))
        assert decoded[:4].hex() == "1c163f28"
        assert int.from_bytes(decoded[4:8], "little") == int(row["serialized_block_bytes"])
        assert decoded[8:].hex() == row["header_hex"]
        spotchecks.append({"height": int(row["height"]), "file": row["file"], "offset": offset,
                           "matches_disk_header": True})

    sys.path.insert(0, str(BASE))
    import resource_model
    source_hash = digest(BASE / "resource_model.py")
    typed_counts = {"attempted_prepares": 0, "accepted_prepares": 0, "rejected_prepares": 0,
                    "settled": 0, "aborted": 0, "invariant_failures": 0}
    rng = random.Random(301)
    state = resource_model.ResourceLedger({"c": resource_model.ResourceChannel(1000, 500)})
    for step in range(5000):
        if state.pending and rng.random() < 0.45:
            operation = rng.choice(list(state.pending))
            settle = rng.random() < 0.7
            state.finish(operation, settle)
            typed_counts["settled" if settle else "aborted"] += 1
        else:
            typed_counts["attempted_prepares"] += 1
            transfers = [("c", rng.choice((-1, 1)), rng.randint(1, 400)) for _ in range(rng.randint(1, 3))]
            before = asdict(state)
            try:
                state.prepare(f"op-{step}", transfers)
                typed_counts["accepted_prepares"] += 1
            except ValueError:
                assert asdict(state) == before
                typed_counts["rejected_prepares"] += 1
        state.channels["c"].validate()
        for direction, held in ((1, state.channels["c"].held_left), (-1, state.channels["c"].held_right)):
            assert held == sum(req.get(("c", direction), 0) for req in state.pending.values())

    state = resource_model.ResourceLedger({"c": resource_model.ResourceChannel(100, 100)})
    float_direction = {"input_direction": 1.0, "prepare_accepted": False}
    try:
        state.prepare("float-direction", [("c", 1.0, 10)])
        float_direction["prepare_accepted"] = True
        before_finish = asdict(state)
        try:
            state.finish("float-direction", True)
            float_direction["finish_accepted"] = True
        except ValueError as exc:
            float_direction["finish_error"] = str(exc)
            float_direction["mutated_on_error"] = asdict(state) != before_finish
            float_direction["ending_balance_type"] = type(state.channels["c"].left).__name__
    except ValueError as exc:
        float_direction["prepare_rejected"] = str(exc)

    sys.path.insert(0, "C:/projects/Spiral/src")
    from spiral_ln.bonding import RewardClaim, sybil_invariant_rewards
    zero = sybil_invariant_rewards([RewardClaim(c, c, 1, 1.0) for c in "abc"] +
                                    [RewardClaim("z", "z", 1, 0.0)], 2)
    assert zero == {"a": 0, "b": 0, "c": 0, "z": 2}
    mixed = sybil_invariant_rewards([RewardClaim("a", "subject", 100, .1),
                                     RewardClaim("b", "subject", 50, 1.0),
                                     RewardClaim("r", "reference", 100, 1.0)], 120)
    assert mixed["a"] + mixed["b"] == 60
    result = {
        "schema": "spiral.cross-lane-algebra-review.v1", "utc": datetime.now(timezone.utc).isoformat(),
        "source_hashes": {"resource_model.py": source_hash,
                          "headers.csv": digest(csv_file), "testnet_summary.json": digest(summary_file),
                          "incentives_run_audit.py": digest(BASE / "incentives/run_audit.py"),
                          "bonding.py": digest(Path("C:/projects/Spiral/src/spiral_ln/bonding.py")),
                          "cross_examination.py": digest(Path(__file__))},
        "header_verification": {"headers": len(rows), "sha256d_matches": len(rows),
                                "encoded_target_checks": len(rows), "internal_parent_links": len(rows) - 1,
                                "nonpositive_timestamp_differences": sum(d <= 0 for d in differences),
                                "disk_spotchecks": spotchecks,
                                "not_checked": ["retarget rules", "full consensus", "transactions or merkle roots",
                                                "current tip", "wallet state", "actual funding inclusion"]},
        "resource_model_typed_state_machine": typed_counts,
        "resource_model_float_direction": float_direction,
        "incentives_independent_witnesses": {"zero_weight_rounding": zero, "mixed_coordinate_subject_reward": 60,
                                             "joint_record_max_weight_alternative_reward": 40},
        "scope_adjudication": {
            "fixed_weight_identity_theorem": "survives; score-selection experiments vary weights and are not a contradiction",
            "mixed_coordinates": "attested joint-claim interpretation yields a mismatch; separate canonical attribute interpretation needs an explicit consistency/authentication contract",
            "zero_weight_rounding": "genuine allocator bug within nonnegative valid inputs, while total-pool conservation survives",
            "bond": "separately posted bond accounting not enforced; shared funding collateral could be coherent with explicit lien/priority, not evidence of real double spending",
            "testnet_scenarios": "outcomes depend on assumed ordinal delays, not header-specific stochastic conditions; source-backed clock ordering is not empirical funding latency"}}
    out = Path(__file__).with_name("cross_examination.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "header_verification": result["header_verification"],
                      "resource_model_typed_state_machine": typed_counts,
                      "float_direction": float_direction}, indent=2))


if __name__ == "__main__":
    main()

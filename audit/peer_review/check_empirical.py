"""Recompute published contrasts and inspect archived testnet4 headers offline.

This is a post-hoc audit of retained evidence, not a new simulation campaign.
It uses the archived analysis's rounded Student-t critical values so matching
its intervals is an exact reproducibility check. Archived files are read only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

T975 = {3: 3.182, 5: 2.571, 17: 2.110, 27: 2.052}
CAMPAIGNS = {
    "original": "output/public_topology_eval/rows.csv",
    "replication": "output/public_topology_replication/rows.csv",
    "precision": "output/public_topology_precision/rows.csv",
}
CONTRASTS = {
    "retry_minus_public_success": (("retry", "none"), ("public", "none"), None),
    "online_minus_retry_success": (("online", "none"), ("retry", "none"), None),
    "oracle_minus_online_success": (("oracle", "none"), ("online", "none"), None),
    "oracle_minus_retry_success": (("oracle", "none"), ("retry", "none"), None),
    "failure_capital_minus_random_success": (("online", "failure_aware"), ("online", "random"), None),
    "failure_capital_diffuse": (("online", "failure_aware"), ("online", "random"), "diffuse"),
    "failure_capital_stationary": (("online", "failure_aware"), ("online", "random"), "stationary_hotspot"),
    "failure_capital_shifted": (("online", "failure_aware"), ("online", "random"), "shifted_hotspot"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_key(row: dict) -> tuple:
    return tuple(row[k] for k in ("campaign", "topology_sample_id", "balance_draw", "balance_model", "demand_regime"))


def condition(rows: list[dict], policy: tuple[str, str], regime: str | None) -> dict:
    selected = {}
    for row in rows:
        if (row["routing_policy"], row["capital_policy"]) != policy:
            continue
        if regime is not None and row["demand_regime"] != regime:
            continue
        key = atomic_key(row)
        if key in selected:
            raise ValueError(f"duplicate condition key: {policy}, {key}")
        selected[key] = row
    if not selected:
        raise ValueError(f"empty condition: {policy}, {regime}")
    return selected


def interval(values: list[tuple[str, str, float]]) -> dict:
    groups = defaultdict(list)
    for campaign, topology, value in values:
        if not math.isfinite(value):
            raise ValueError("non-finite effect")
        groups[(campaign, topology)].append(value)
    means = [mean(groups[key]) for key in sorted(groups)]
    n = len(means)
    if n < 2:
        raise ValueError("at least two topology clusters required for an interval")
    if n - 1 not in T975:
        raise ValueError(f"unregistered degrees of freedom: {n - 1}")
    center = mean(means)
    half = T975[n - 1] * stdev(means) / math.sqrt(n)
    return {"cluster_n": n, "atomic_n": len(values), "mean": center,
            "ci95_lower": center - half, "ci95_upper": center + half,
            "critical_value": T975[n - 1], "cluster_means": means}


def contrast(rows: list[dict], left: tuple, right: tuple, regime: str | None) -> dict:
    a, b = condition(rows, left, regime), condition(rows, right, regime)
    if set(a) != set(b):
        raise ValueError(f"unpaired comparison: {len(set(a)-set(b))} left-only and {len(set(b)-set(a))} right-only")
    values = [(key[0], key[1], float(a[key]["evaluation_success_rate"]) - float(b[key]["evaluation_success_rate"])) for key in sorted(a)]
    result = interval(values)
    result["left"] = "|".join(left)
    result["right"] = "|".join(right)
    result["demand_regime"] = regime or "all"
    result["equivalent_within_one_percentage_point"] = -0.01 < result["ci95_lower"] and result["ci95_upper"] < 0.01
    result["by_campaign"] = {campaign: interval([v for v in values if v[0] == campaign]) for campaign in sorted({v[0] for v in values})}
    return result


def inspect_headers(repo: Path) -> dict:
    path = repo / "audit/testnet4/results/headers.csv"
    summary_path = repo / "audit/testnet4/results/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if sha256(path) != summary["headers_csv_sha256"]:
        raise ValueError("header CSV checksum differs from retained receipt")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("no archived headers")
    for i, row in enumerate(rows):
        header = bytes.fromhex(row["header_hex"])
        if len(header) != 80:
            raise ValueError("header length differs from 80 bytes")
        digest = hashlib.sha256(hashlib.sha256(header).digest()).digest()
        if digest[::-1].hex() != row["hash"] or header[4:36][::-1].hex() != row["previous"]:
            raise ValueError("header identity or parent differs")
        timestamp, bits = struct.unpack_from("<II", header, 68)
        exponent, mantissa = bits >> 24, bits & 0x007fffff
        target = mantissa << (8 * (exponent - 3)) if exponent >= 3 else mantissa >> (8 * (3 - exponent))
        if bits & 0x00800000 or not 0 < target < 2**256 or int.from_bytes(digest, "little") > target:
            raise ValueError("encoded proof-of-work target not met")
        if timestamp != int(row["timestamp"]) or f"{bits:08x}" != row["bits"]:
            raise ValueError("decoded header field differs")
        if i and (row["previous"] != rows[i-1]["hash"] or int(row["height"]) != int(rows[i-1]["height"]) + 1):
            raise ValueError("broken internal parent link or height sequence")
    if rows[-1]["hash"] != summary["tip_hash"] or int(rows[-1]["height"]) != summary["tip_height"]:
        raise ValueError("last header differs from retained log anchor")
    deltas = [int(b["timestamp"]) - int(a["timestamp"]) for a, b in zip(rows, rows[1:])]
    return {"header_count": len(rows), "internal_parent_links": len(rows) - 1,
            "first_height": int(rows[0]["height"]), "last_height": int(rows[-1]["height"]),
            "last_hash": rows[-1]["hash"], "header_sha256": sha256(path),
            "nonpositive_header_time_differences": sum(x <= 0 for x in deltas),
            "median_header_time_difference_seconds": median(deltas),
            "minimum_header_time_difference_seconds": min(deltas),
            "interpretation": "Historical header identity, encoded PoW and internal-link check. No current-chain, full-consensus, transaction-inclusion, arrival-time or Lightning measurement."}


def run(repo: Path) -> dict:
    archive_path = repo / "output/public_topology_combined/summary.json"
    archived = json.loads(archive_path.read_text(encoding="utf-8"))
    rows, counts, sources = [], {}, {}
    for campaign, relative in CAMPAIGNS.items():
        path = repo / relative
        digest = sha256(path)
        if digest != archived["campaigns"][campaign]["rows_sha256"]:
            raise ValueError(f"archived row checksum mismatch: {campaign}")
        with path.open(newline="", encoding="utf-8") as stream:
            all_rows = [dict(row, campaign=campaign) for row in csv.DictReader(stream)]
        selected = [row for row in all_rows if row["evaluation_split"] == "sealed_holdout"]
        keys = [(atomic_key(row), row["routing_policy"], row["capital_policy"]) for row in selected]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate sealed rows: {campaign}")
        counts[campaign] = {"all_rows": len(all_rows), "sealed_rows": len(selected), "sealed_topology_clusters": len({r["topology_sample_id"] for r in selected})}
        sources[relative] = digest
        rows.extend(selected)
    contrasts = {name: contrast(rows, *params) for name, params in CONTRASTS.items()}
    verified = []
    for name, value in contrasts.items():
        if name not in archived["contrasts"]:
            continue
        prior = archived["contrasts"][name]["combined"]
        for key in ("cluster_n", "atomic_n", "mean", "ci95_lower", "ci95_upper"):
            if abs(value[key] - prior[key]) > 1e-12:
                raise ValueError(f"stored contrast mismatch: {name}, {key}")
        verified.append(name)
    sources["output/public_topology_combined/summary.json"] = sha256(archive_path)
    return {"schema": "spiral-peer-review-empirical-check-v1", "review_date": "2026-10-21",
            "baseline_commit": "6a9df365f727cf2471ae52e00b36e8816d0081bc",
            "evidence_kind": "post-hoc reanalysis of archived CSVs and historical header check",
            "source_sha256": sources, "campaign_counts": counts,
            "total_rows": sum(c["all_rows"] for c in counts.values()), "sealed_rows": len(rows),
            "verified_archived_contrasts": verified,
            "interval_method": "Two-sided 95% Student-t on equally weighted topology-cluster means, using archived rounded critical values; conditional on one public snapshot and selected campaign design.",
            "contrasts": contrasts, "testnet4_headers": inspect_headers(repo)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.repo / "audit/peer_review/empirical_check.json"
    result = run(args.repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = {"total_rows": result["total_rows"], "sealed_rows": result["sealed_rows"],
               "archived_contrasts_verified": len(result["verified_archived_contrasts"]),
               "testnet4_headers": result["testnet4_headers"],
               "effects_pp": {k: {f: round(v[f] * 100, 6) for f in ("mean", "ci95_lower", "ci95_upper")} for k, v in result["contrasts"].items()}}
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()

"""Bounded, offline adversarial audit of the frozen Connector Calculus study.

No node, wallet, network, or payment API is used. Writes only this audit folder.
The experiment is exploratory and was designed after inspecting the old results.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from statistics import mean, median

import networkx as nx

from spiral_ln.algebra import Channel, NetworkState
from spiral_ln import public_topology_analysis as analysis
from spiral_ln.public_topology import (
    SAMPLING_MODES, load_public_graph, sample_connected_subgraph,
    network_state_from_public_sample, public_demand_stream,
)
from spiral_ln.public_topology_eval import PathCatalog, TerminalFeedbackAgent, execute_payment
from spiral_ln.simulator import Demand, graph_of

CAMPAIGNS = {
    "initial": "public_topology_eval",
    "replication": "public_topology_replication",
    "precision": "public_topology_precision",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def describe(values):
    return {"n": len(values), "min": min(values, default=None),
            "mean": mean(values) if values else None,
            "median": median(values) if values else None,
            "max": max(values, default=None)}


def load_campaigns(repo):
    configs, rows = {}, []
    for label, folder in CAMPAIGNS.items():
        configs[label] = json.loads((repo / "configs" / f"{folder}.json").read_text())
        with (repo / "output" / folder / "rows.csv").open(newline="", encoding="utf-8") as stream:
            rows.extend(dict(row, campaign=label) for row in csv.DictReader(stream))
    return configs, rows


def integrity(rows):
    condition = lambda r: analysis._atomic_key(r) + (r["routing_policy"], r["capital_policy"])
    counts = Counter(condition(r) for r in rows)
    sealed = [r for r in rows if r["evaluation_split"] == "sealed_holdout"]
    pair_counts = {}
    for name, (left, right, metric, regime) in analysis.CONTRASTS.items():
        a, b = analysis._condition(sealed, *left, regime), analysis._condition(sealed, *right, regime)
        pair_counts[name] = {"left": len(a), "right": len(b), "matched": len(a.keys() & b.keys()),
                             "unmatched_left": len(a.keys() - b.keys()), "unmatched_right": len(b.keys() - a.keys())}
    return {"all_rows": len(rows), "sealed_rows": len(sealed),
            "duplicate_condition_keys": sum(n-1 for n in counts.values()),
            "pair_counts": pair_counts,
            "sealed_topology_clusters": len({(r["campaign"], r["topology_sample_id"]) for r in sealed})}


def pipeline_counterexamples():
    def row(topology, policy, value):
        return {"campaign": "synthetic-negative-control", "topology_sample_id": topology,
                "balance_draw": "0", "balance_model": "uniform", "demand_regime": "diffuse",
                "routing_policy": policy, "capital_policy": "none", "evaluation_success_rate": str(value)}
    a, b = row("t0", "retry", .8), row("t0", "public", .5)
    duplicate = row("t0", "retry", .2)
    def contrast(rs):
        return analysis.atomic_differences(rs, ("retry", "none"), ("public", "none"), "evaluation_success_rate")
    return {
        "empty_cluster_interval": analysis.cluster_interval([]),
        "single_cluster_interval": analysis.cluster_interval([("x", "only", .123)]),
        "duplicate_last_wins_a": contrast([a, b, duplicate]),
        "duplicate_last_wins_b": contrast([duplicate, b, a]),
        "missing_pair_ignored": contrast([a, b, row("unmatched", "retry", .0)]),
        "all_missing_pair_returns_empty": contrast([a]),
        "negative_effect_still_passes_one_sided_bound": (-.04 < .01),
        "vacuous_oracle_zero_leakage_on_empty": all(float(r["evaluation_leakage_proxy"]) == 0 for r in []),
    }


def overlap_audit(graph, configs, rows):
    # Anonymous ordinal attributes survive the production sampler's relabeling.
    # IDs are used only in memory; no original node identifiers are written.
    nx.set_node_attributes(graph, {node: i for i, node in enumerate(sorted(graph.nodes()))}, "_audit_ordinal")
    samples, records = {}, []
    for campaign, cfg in configs.items():
        for index in range(cfg["topology_sample_count"]):
            seed = cfg.get("seed_offset", 0) + index
            sample = sample_connected_subgraph(graph, seed, cfg["node_count"], SAMPLING_MODES[index % 3])
            nodes = {d["_audit_ordinal"] for _, d in sample.graph.nodes(data=True)}
            edges = {tuple(sorted((sample.graph.nodes[u]["_audit_ordinal"], sample.graph.nodes[v]["_audit_ordinal"])))
                     for u, v in sample.graph.edges()}
            split = "calibration" if index < cfg["calibration_sample_count"] else "sealed_holdout"
            expected_ids = {r["topology_sample_id"] for r in rows if r["campaign"] == campaign and int(r["topology_index"]) == index}
            assert expected_ids == {sample.sample_id}, (campaign, index, expected_ids, sample.sample_id)
            samples[(campaign, index)] = sample
            records.append({"campaign": campaign, "index": index, "sample_id": sample.sample_id,
                            "split": split, "nodes": nodes, "edges": edges, "stats": sample.stats()})
    sealed = [r for r in records if r["split"] == "sealed_holdout"]
    training = [r for r in records if r["split"] == "calibration"]
    def pairs_report(pairs):
        pairs = list(pairs)
        node_intersections = [len(a["nodes"] & b["nodes"]) for a, b in pairs]
        edge_intersections = [len(a["edges"] & b["edges"]) for a, b in pairs]
        return {"pair_count": len(pairs), "pairs_sharing_nodes": sum(n > 0 for n in node_intersections),
                "pairs_sharing_edges": sum(n > 0 for n in edge_intersections),
                "node_intersection": describe(node_intersections), "edge_intersection": describe(edge_intersections),
                "node_jaccard": describe([len(a["nodes"] & b["nodes"])/len(a["nodes"] | b["nodes"]) for a,b in pairs]),
                "edge_jaccard": describe([len(a["edges"] & b["edges"])/len(a["edges"] | b["edges"]) for a,b in pairs])}
    train_nodes = set().union(*(r["nodes"] for r in training))
    train_edges = set().union(*(r["edges"] for r in training))
    union_nodes = set().union(*(r["nodes"] for r in sealed))
    union_edges = set().union(*(r["edges"] for r in sealed))
    cover = [{"sample_id": r["sample_id"], "nodes_seen_in_any_calibration": len(r["nodes"] & train_nodes),
              "edges_seen_in_any_calibration": len(r["edges"] & train_edges)} for r in sealed]
    return samples, {
        "original_snapshot_nodes": graph.number_of_nodes(), "original_snapshot_edges": graph.number_of_edges(),
        "all_sample_ids_verified_against_rows": True,
        "sealed_samples": len(sealed), "calibration_samples": len(training),
        "sealed_unique_nodes": len(union_nodes), "sealed_unique_edges": len(union_edges),
        "sealed_node_occurrences": sum(len(r["nodes"]) for r in sealed),
        "sealed_edge_occurrences": sum(len(r["edges"]) for r in sealed),
        "sealed_pairs": pairs_report(combinations(sealed, 2)),
        "sealed_cross_campaign_pairs": pairs_report((a,b) for a,b in combinations(sealed, 2) if a["campaign"] != b["campaign"]),
        "sealed_calibration_pairs": pairs_report((a,b) for a in sealed for b in training),
        "sealed_calibration_coverage": cover,
        "samples": [{k:v for k,v in r.items() if k not in {"nodes", "edges"}} for r in records],
        "caveat": "Overlap is a sample-diversity fact, not a measured covariance. With independently randomized seeds on a fixed snapshot, overlapping subgraphs can still be conditionally independent draws. These intervals do not sample snapshot-to-snapshot uncertainty."
    }


class FrozenAgent(TerminalFeedbackAgent):
    def observe(self, path, delivered):
        pass


def execute_custom(state, demand, name, catalog, agent):
    if name == "oracle3":
        paths = sorted(catalog.paths(demand.source, demand.target),
                       key=lambda p: (state.route_cost_msat(p,demand.amount),len(p),p))[:3]
        for path in paths:
            if state.route_feasible(path, demand.amount):
                fee = state.route_cost_msat(path,demand.amount)
                state.apply_route(path,demand.amount)
                return True, fee, 0
        return False,0,0
    policy, budget = {"retry3":("retry",3), "retry8":("retry",8), "online3":("online",3),
                      "frozen3":("online",3), "oracle8":("oracle",3), "public1":("public",3)}[name]
    return execute_payment(state,demand,policy,catalog,agent,budget)


def state_digest(state):
    return digest([(c.u,c.v,c.capacity,c.balance_uv) for _,c in sorted(state.channels.items(),key=lambda item: sorted(item[0]))])


def budget_replay(samples, cfg, original_rows):
    policies = ("public1","retry3","online3","frozen3","oracle3","retry8","oracle8")
    records, matches, reproduction = [], [], []
    for index in (4,5,6):  # first original sealed random, periphery, hub samples
        sample = samples[("initial",index)]
        catalog = PathCatalog(sample.graph,8)
        for balance_model in ("uniform","polarized"):
            for regime in ("diffuse","stationary_hotspot","shifted_hotspot"):
                seed = index
                start = network_state_from_public_sample(sample,seed,10000*seed,balance_model)
                demands,_,_ = public_demand_stream(sample.graph,20000*seed,220,110,regime)
                cell = {"topology_index":index,"sample_id":sample.sample_id,"balance_model":balance_model,"demand_regime":regime}
                policy_rows = {}
                for name in policies:
                    state = start.clone()
                    agent = (FrozenAgent if name == "frozen3" else TerminalFeedbackAgent)(5000)
                    outcomes, trajectory, failures, fees = [],[],0,0
                    for step,demand in enumerate(demands):
                        delivered,fee,failed = execute_custom(state,demand,name,catalog,agent)
                        if step >= 110:
                            outcomes.append(delivered)
                            failures += failed
                            fees += fee
                        trajectory.append(state_digest(state))
                    row = dict(cell,policy=name,success_rate=sum(outcomes)/110,success_count=sum(outcomes),
                               failed_attempts=failures,fee_msat=fees,outcomes_sha256=digest(outcomes),
                               trajectory_sha256=digest(trajectory),final_state_sha256=state_digest(state))
                    records.append(row)
                    policy_rows[name]=row
                    original_policy={"public1":"public","retry3":"retry","online3":"online","oracle8":"oracle"}.get(name)
                    if original_policy:
                        old=[r for r in original_rows if r["campaign"] == "initial" and int(r["topology_index"]) == index
                             and r["balance_draw"] == "0" and r["balance_model"] == balance_model
                             and r["demand_regime"] == regime and r["routing_policy"] == original_policy and r["capital_policy"] == "none"]
                        assert len(old)==1
                        reproduction.append(dict(cell, policy=name,
                            old_success_count=int(old[0]["evaluation_succeeded"]),new_success_count=row["success_count"],
                            old_failed_attempts=int(old[0]["evaluation_infeasible_path_attempts"]),new_failed_attempts=row["failed_attempts"],
                            exact=(row["success_count"]==int(old[0]["evaluation_succeeded"]) and
                                   row["failed_attempts"]==int(old[0]["evaluation_infeasible_path_attempts"]))))
                for left,right in (("retry3","oracle3"),("retry8","oracle8"),("retry3","frozen3")):
                    assert policy_rows[left]["trajectory_sha256"] == policy_rows[right]["trajectory_sha256"]
                    matches.append(dict(cell,left=left,right=right,trajectory_identical=True))
                print(f"replayed sample {index} {balance_model} {regime}",flush=True)
    aggregates={p:{"cells":18,"mean_success_rate":mean(r["success_rate"] for r in records if r["policy"]==p),
                   "total_failed_attempts":sum(r["failed_attempts"] for r in records if r["policy"]==p),
                   "evaluation_demands":18*110} for p in policies}
    return {"design":"Post-hoc bounded diagnostic replay; three existing topology samples, two balances, three regimes, draw zero. No new confirmatory CI.",
            "cells":18,"episodes":len(records),"steps_per_episode":220,"evaluation_steps":110,
            "original_four_policies_exactly_reproduced":all(r["exact"] for r in reproduction),
            "original_reproduction_checks":reproduction,"aggregates":aggregates,
            "matched_budget_trajectory_checks":matches,"rows":records}


def route_budget_witness():
    state=NetworkState()
    for i in range(4):
        balance=10 if i==3 else 0
        state.add_channel(Channel("S",f"M{i}",20,balance,base_fee_msat=0,fee_ppm=0))
        state.add_channel(Channel(f"M{i}","T",20,10,base_fee_msat=0,fee_ppm=0))
    catalog=PathCatalog(graph_of(state),8)
    return {name:dict(zip(("delivered","fee_msat","failed_attempts"),execute_custom(state.clone(),Demand("S","T",1),name,catalog,TerminalFeedbackAgent(5000))))
            for name in ("public1","retry3","online3","oracle3","retry8","oracle8")}


def greedy_oracle_witness():
    state=NetworkState()
    for a,b,cap,bal,fee in (("S","A",1,1,0),("A","T",2,2,0),("S","B",1,1,1),("B","T",1,1,1)):
        state.add_channel(Channel(a,b,cap,bal,base_fee_msat=fee,fee_ppm=0))
    catalog=PathCatalog(graph_of(state),8)
    greedy=state.clone()
    first=execute_custom(greedy,Demand("S","T",1),"oracle8",catalog,TerminalFeedbackAgent(5000))
    second=execute_custom(greedy,Demand("A","T",2),"oracle8",catalog,TerminalFeedbackAgent(5000))
    alternative=state.clone()
    alternative.apply_route(("S","B","T"),1)
    alternative.apply_route(("A","T"),2)
    return {"demands":[["S","T",1],["A","T",2]],"production_greedy_oracle_successes":int(first[0])+int(second[0]),
            "feasible_alternative_successes":2,"alternative_routes":[["S","B","T"],["A","T"]],
            "interpretation":"Greedy per-demand feasibility filtering is not a full-horizon optimal-control upper bound."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",default=r"C:\projects\Spiral")
    args=parser.parse_args()
    repo=Path(args.repo)
    output=Path(__file__).resolve().parent
    configs,rows=load_campaigns(repo)
    snapshot=repo/"data/topology/20230716.gml.geo"
    assert sha(snapshot)==configs["initial"]["snapshot_sha256"]
    print("Reading verified snapshot",flush=True)
    graph=load_public_graph(snapshot)
    samples,overlaps=overlap_audit(graph,configs,rows)
    print("Overlap reconstruction complete",flush=True)
    (output/"overlap_interim.json").write_text(json.dumps(overlaps,indent=2),encoding="utf-8")
    results={"schema_version":"1.0","created_utc":datetime.now(timezone.utc).isoformat(),
             "pythonhashseed":os.environ.get("PYTHONHASHSEED"),
             "scope":"Offline audit of already published local results; synthetic diagnostics, not testnet4 LN execution.",
             "integrity":integrity(rows),"pipeline_counterexamples":pipeline_counterexamples(),
             "sample_overlap":overlaps,"route_budget_witness":route_budget_witness(),
             "greedy_oracle_witness":greedy_oracle_witness(),
             "budget_replay":budget_replay(samples,configs["initial"],rows)}
    path=output/"results.json"
    path.write_text(json.dumps(results,indent=2),encoding="utf-8")
    inputs=[repo/"paper/manuscript.md", snapshot,
            *(repo/"src/spiral_ln"/name for name in ("public_topology.py","public_topology_eval.py","public_topology_analysis.py","algebra.py","simulator.py")),
            *(repo/"configs"/f"{folder}.json" for folder in CAMPAIGNS.values()),
            *(repo/"output"/folder/"rows.csv" for folder in CAMPAIGNS.values())]
    receipt={"python":platform.python_version(),"networkx":nx.__version__,"script_sha256":sha(__file__),
             "pythonhashseed":os.environ.get("PYTHONHASHSEED"),
             "command":r'$env:PYTHONPATH="C:\projects\Spiral\src"; $env:PYTHONDONTWRITEBYTECODE="1"; $env:PYTHONHASHSEED="1"; & "C:\projects\Spiral\.venv\Scripts\python.exe" "E:\Recovered_C_projects\Spiral_target\projects\Spiral\audit\inference\run_audit.py"',
             "inputs":{str(p):sha(p) for p in inputs},"results_sha256":sha(path),
             "no_live_network":True,"no_wallet_operations":True}
    (output/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps({"integrity":results["integrity"],"sealed_pairs":overlaps["sealed_pairs"],
                      "aggregates":results["budget_replay"]["aggregates"],"output":str(path)},indent=2))


if __name__=="__main__":
    main()

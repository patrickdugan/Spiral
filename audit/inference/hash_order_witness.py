"""Probe hash-seed sensitivity on one actual public sample, without payments."""
import argparse
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
import networkx as nx
from spiral_ln.public_topology import load_public_graph, sample_connected_subgraph, network_state_from_public_sample
from spiral_ln.public_topology_eval import PathCatalog, run_episode, load_config

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
args = parser.parse_args()
graph = load_public_graph(r"C:\projects\Spiral\data\topology\20230716.gml.geo")
sample = sample_connected_subgraph(graph, 4, 64, "random")
catalog = PathCatalog(sample.graph, 8)
nodes = sorted(sample.graph)
pairs = [(a,b) for a in nodes for b in nodes if a!=b]
paths = [(a,b,catalog.paths(a,b)) for a,b in pairs[:512]]
digest = lambda obj: hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()
state = network_state_from_public_sample(sample,4,40000,"uniform")
canonical_state = sorted((tuple(sorted((c.u,c.v))), c.capacity, c.balance_uv) for c in state.channels.values())
metadata = sorted((tuple(sorted((a,b))), d.get("fee_base_msat"),d.get("fee_proportional_millionths"),d.get("cltv_expiry_delta")) for a,b,d in sample.graph.edges(data=True))
cfg = load_config(r"C:\projects\Spiral\configs\public_topology_eval.json")
episodes = {}
for policy in ("public","retry","online","oracle"):
    row = run_episode(sample,4,0,"uniform","diffuse",policy,"none",cfg,catalog)
    episodes[policy] = {"evaluation_succeeded":row.evaluation.succeeded,
                        "evaluation_failed_attempts":row.evaluation.infeasible_path_attempts}
stable_graph=nx.Graph()
stable_graph.add_nodes_from(sorted(sample.graph.nodes()))
for (a,b),attributes in sorted((tuple(sorted((a,b))),attributes) for a,b,attributes in sample.graph.edges(data=True)):
    stable_graph.add_edge(a,b,**attributes)
stable_sample=replace(sample,graph=stable_graph)
stable_state=network_state_from_public_sample(stable_sample,4,40000,"uniform")
stable_catalog=PathCatalog(stable_graph,8)
stable_paths=[(a,b,stable_catalog.paths(a,b)) for a,b in pairs[:512]]
stable_episodes={}
for policy in ("public","retry","online","oracle"):
    row=run_episode(stable_sample,4,0,"uniform","diffuse",policy,"none",cfg,stable_catalog)
    stable_episodes[policy]={"evaluation_succeeded":row.evaluation.succeeded,
                            "evaluation_failed_attempts":row.evaluation.infeasible_path_attempts}
result = {"pythonhashseed":os.environ.get("PYTHONHASHSEED"),"networkx":nx.__version__,
          "sample_id":sample.sample_id,"source_node_hash":sample.source_node_hash,
          "canonical_edges_sha256":digest(sorted(tuple(sorted(edge)) for edge in sample.graph.edges())),
          "iteration_nodes_sha256":digest(list(sample.graph.nodes())),
          "canonical_public_metadata_sha256":digest(metadata),
          "synthetic_state_sha256":digest(canonical_state),
          "catalogue_sha256":digest(paths),"pair_count":len(paths),
          "episodes":episodes,
          "canonical_order_reference":{
              "synthetic_state_sha256":digest(sorted((tuple(sorted((c.u,c.v))),c.capacity,c.balance_uv) for c in stable_state.channels.values())),
              "catalogue_sha256":digest(stable_paths),"episodes":stable_episodes,
              "scope":"Separate audit reference canonicalizes node and oriented-edge insertion; does not edit production sampler."},
          "path_counts":{str(n):sum(len(p)==n for a,b,p in paths) for n in range(9)}}
Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result))

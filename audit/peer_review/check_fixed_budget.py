"""Independent aggregate conservation and canonical-demand audit of holdouts."""
import hashlib
import json
from pathlib import Path

root = Path("audit/peer_review/capital")
cells = ["zero", "drain", "accumulate", "steady"]

def canonical_demand(cell, seed):
    state = seed
    def random():
        nonlocal state
        state = (state * 1664525 + 1013904223) % (2 ** 32)
        return state / (2 ** 32)
    agents = 3 if cell == "steady" else 200
    p_out = (.02 * 5000 - {"drain": -30, "accumulate": 60}.get(cell, 0)) / 4000
    events = []
    for height in range(0, 34560, 6):
        for holder in range(agents):
            if cell == "steady":
                outgoing = 100 + int(random() * 10)
                incoming = 100 + int(random() * 10)
            else:
                incoming = 5000 if random() < .02 else 0
                outgoing = 4000 if random() < p_out else 0
            for direction, amount in [("in", incoming), ("out", outgoing)]:
                if amount:
                    events.append({"height": height, "holder": holder, "direction": direction, "amount": amount})
    raw = json.dumps(events, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest(), len(events), sum(x["amount"] for x in events)

ark_count = channel_count = 0
bindings = {}
for cell in cells:
    path = root / f"fixed-budget-result-{cell}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pilot_path = root / f"fixed-budget-pilot-{cell}.json"
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    assert data["pilot_file_sha256"] == hashlib.sha256(pilot_path.read_bytes()).hexdigest()
    assert data["protocol"] == pilot["protocol"]
    for source, digest in pilot["source_sha256"].items():
        canonical = Path(source).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
        assert hashlib.sha256(canonical).hexdigest() == digest, source
    agents = 3 if cell == "steady" else 200
    canonical = {seed: canonical_demand(cell, seed) for seed in range(301, 325)}
    for initial in [0, 250000]:
        rows = [r for r in data["rows"] if r["initial_gross_holder_sat"] == initial]
        assert [r["seed"] for r in rows] == list(range(301, 325))
        budgets = next(b for b in pilot["rows"] if b["initial"] == initial)
        for row in rows:
            demand_hash, events, offered = canonical[row["seed"]]
            assert row["demand_sha256"] == demand_hash
            for variant in row["ark"]:
                r = variant["result"]; t = r["terminal"]; c = r["config"]
                frozen = next(b["config"] for b in budgets["ark"] if b["delay"] == variant["delay"])
                assert all(c[k] == v for k, v in frozen.items())
                assert r["offered_sat"] == offered and r["offered_events"] == events
                v = r["directional_value_sat"]
                assert v["in_delivered"] + v["out_delivered"] == r["delivered_sat"]
                assert r["target_met"] == (r["delivered_sat"] / offered >= .99)
                assert t["cash_sat"] + t["onchain_roots_sat"] + t["ln_local_sat"] + v["out_delivered"] + r["miner_fees_sat"] == c["wallet"] + c["local"] + agents * initial + v["in_delivered"]
                assert agents * initial + v["in_delivered"] == v["out_delivered"] + r["holder_service_fees_sat"] + t["holder_claims_sat"]
                assert t["ln_local_sat"] + t["ln_remote_sat"] == c["local"] + c["remote"]
                assert t["F_sat"] - t["C_sat"] == t["W_sat"]
                assert 0 <= t["exhausted_recovery_shortfall_sat"] <= t["W_sat"] <= c["fronting"]
                assert t["holder_claims_sat"] <= t["encumbered_root_sat"] <= t["onchain_roots_sat"]
                assert t["expired_holder_sat"] <= t["holder_claims_sat"]
                horizon = r["height"]; integrals = {k: int(x) for k, x in r["integrals_sat_blocks"].items()}
                fixed = (c["wallet"] + c["local"] + c["remote"] + agents * initial) * horizon
                assert int(r["initial_funding_sat_blocks"]) == fixed
                assert fixed - r["miner_fees_sat"] * horizon <= integrals["uniqueCommitted"] + integrals["idle"] <= fixed
                assert integrals["inbound"] + integrals["outbound"] == (c["local"] + c["remote"]) * horizon
                assert 0 <= integrals["fronting"] <= c["fronting"] * horizon
                assert integrals["holderOverlay"] <= integrals["uniqueCommitted"] - integrals["inbound"] - integrals["outbound"]
                assert r["integrals_sat_seconds"] is None and integrals["inFlight"] == 0
                assert all(int(at) > horizon for at in t["forecast_unencumbered_recovery_schedule"])
                ark_count += 1
            for r in row["channels"]:
                budget = next(b["budget"] for b in budgets["channels"] if b["group"] == r["group_size"])
                assert r["offered_sat"] == offered and r["offered_events"] == events
                assert r["initial_funded_resource_sat"] == sum(budget["local"]) + sum(budget["remote"])
                assert sum(r["terminal"]["local"]) + sum(r["terminal"]["remote"]) == r["initial_funded_resource_sat"]
                v = r["directional_value_sat"]
                assert agents * initial + v["in_delivered"] - v["out_delivered"] == r["terminal"]["holder_balance_sat"]
                assert r["delivered_sat"] == v["in_delivered"] + v["out_delivered"]
                channel_count += 1
    bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"Verified {cell}: 24 canonical demands, frozen budgets, economic and holder conservation.", flush=True)
assert ark_count == 384 and channel_count == 672
result = {"status": "passed", "ark_runs": ark_count, "channel_runs": channel_count,
          "independently_generated_demands": 96, "result_sha256": bindings,
          "scope": "Independent published-aggregate and integer capital-time checks; not a substitute for per-event live evidence or operational clocks."}
(root / "fixed-budget-check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: result[k] for k in ["status", "ark_runs", "channel_runs"]}))

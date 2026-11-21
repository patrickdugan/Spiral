"""Export sanitized transaction observations and exact capital-time accounting."""
import hashlib
import json
from pathlib import Path

from campaign import atomic, digest, draft_public, dump, output

FINAL = {"confirmed", "recovered", "reused"}


def timeline(plan, drafts, attempts, observations):
    funding = plan["funding"]
    start = plan["started_at"]
    height = plan["initial_height"]
    prior_seconds, highwater = start, height
    funded = funding["sat"]
    unavailable = 0
    metrics = {"funded_sat_blocks": 0, "funded_sat_seconds": 0,
               "unavailable_sat_blocks": 0, "unavailable_sat_seconds": 0,
               "peak_funded_sat": funded, "peak_unavailable_sat": 0}
    events = [{"at": start, "height": height, "kind": "funding", "funded_sat": funded,
               "unavailable_sat": 0, "reserve": funding}]
    confirmations = {}
    recovery_times = {}
    known_states = {}
    points = [(seq, at, 0, height, {"position": pos}) for pos, at, height, seq in attempts]
    points.extend((row["event_order"], row["at"], 1, row["height"], row) for row in observations)

    for seq, at, kind, height, row in sorted(points, key=lambda point: point[0]):
        seconds = max(at - prior_seconds, 0)
        blocks = max(height - highwater, 0)
        metrics["funded_sat_seconds"] += funded * seconds
        metrics["unavailable_sat_seconds"] += unavailable * seconds
        metrics["funded_sat_blocks"] += funded * blocks
        metrics["unavailable_sat_blocks"] += unavailable * blocks
        if kind == 0 and row["position"] not in known_states:
            known_states[row["position"]] = "attempted"
        if kind == 1:
            for phase in row["phases"]:
                pos = phase["position"]
                if phase["status"] == "unseen" and pos not in known_states:
                    continue
                known_states[pos] = phase["status"]
                if phase["status"] in FINAL:
                    prior = confirmations.get(pos)
                    if prior is None or prior[1] != phase["blockhash"]:
                        confirmations[pos] = (at, phase["blockhash"])
                else:
                    confirmations.pop(pos, None)
                if phase["status"] == "recovered":
                    recovery_times.setdefault(pos, (at, phase["blockhash"]))
                    if recovery_times[pos][1] != phase["blockhash"]:
                        recovery_times[pos] = (at, phase["blockhash"])
                elif phase["status"] not in FINAL or (pos in recovery_times and
                        recovery_times[pos][1] != phase["blockhash"]):
                    recovery_times.pop(pos, None)

        reserve = funding
        unavailable = 0
        for pos, draft in enumerate(drafts):
            status = known_states.get(pos)
            if status is None:
                break
            if status in FINAL:
                reserve = draft["change"]
                unavailable = reserve["sat"] if status == "confirmed" else 0
            else:
                unavailable = reserve["sat"]
                break
        funded = reserve["sat"]
        metrics["peak_unavailable_sat"] = max(metrics["peak_unavailable_sat"], unavailable)
        events.append({"event_order": seq, "at": at, "height": height,
                       "kind": "observation" if kind else "submission_attempt",
                       "tip": row.get("tip"), "reorg": row.get("reorg", False),
                       "funded_sat": funded, "unavailable_sat": unavailable, "reserve": reserve})
        prior_seconds, highwater = max(prior_seconds, at), max(highwater, height)

    latest = observations[-1] if observations else {"at": start, "phases": []}
    cutoff = max(latest["at"], prior_seconds)
    arrived = [item for group in plan["groups"] for item in group
               if item["arrival_seconds"] <= cutoff - start]
    offered_sat = sum(item["sat"] for item in arrived)
    attempts_by_pos = {pos: at for pos, at, _, _ in attempts}
    paid_sat = paid_count = fee_sat = settled_vbytes = 0
    settled = []
    for pos, draft in enumerate(drafts):
        if pos not in confirmations:
            break
        paid_at = confirmations[pos][0]
        fee_sat += draft["fee_sat"]
        settled_vbytes += draft["vsize"]
        for item in draft["payments"]:
            latency = paid_at - start - item["arrival_seconds"]
            by_deadline = 0 <= latency <= item["deadline_seconds"]
            if by_deadline:
                paid_sat += item["sat"]
                paid_count += 1
            queued = attempts_by_pos.get(pos)
            settled.append({"invoice": item["id"], "txid": draft["txid"], "sat": item["sat"],
                            "queue_seconds": (None if queued is None else
                                              queued - start - item["arrival_seconds"]),
                            "latency_seconds": latency, "by_deadline": by_deadline})
    if sum(item["sat"] for item in settled) + fee_sat + funded != funding["sat"]:
        raise ValueError("Confirmed chain and capital conservation disagree")
    latencies = []
    for phase in latest["phases"]:
        pos = phase["position"]
        if pos in recovery_times and pos in attempts_by_pos:
            latencies.append({"txid": phase["txid"],
                              "recovery_seconds": recovery_times[pos][0] - attempts_by_pos[pos]})
        if phase["status"] == "reused" and pos + 1 in confirmations and pos in recovery_times and pos in attempts_by_pos:
            latencies[-1]["reuse_after_recovery_seconds"] = (
                confirmations[pos + 1][0] - recovery_times[pos][0])
    latest_confirmed_ids = [row["txid"] for row in latest["phases"] if row["status"] in FINAL]
    active_fee_reserved = sum(draft["fee_sat"] for draft in drafts)
    attempted_fee_budget = sum(drafts[pos]["fee_sat"] for pos, _, _, _ in attempts)
    result = {"initial_funding_sat": funding["sat"], "confirmed_fees_sat": fee_sat,
              "signed_fee_budget_sat": active_fee_reserved, "attempted_fee_budget_sat": attempted_fee_budget,
              "terminal_funded_sat": funded, "terminal_unavailable_sat": unavailable,
              "settlement_virtual_bytes": settled_vbytes,
              "offered_invoices": len(arrived), "offered_sat": offered_sat,
              "attempted_invoices": sum(len(drafts[pos]["payments"]) for pos, _, _, _ in attempts),
              "confirmed_invoice_count": len(settled), "confirmed_application_sat": sum(
                  item["sat"] for item in settled),
              "settled_by_deadline_count": paid_count, "settled_by_deadline_sat": paid_sat,
              "unsettled_by_deadline_count": len(arrived) - paid_count,
              "expired_unsettled_count": sum(item["arrival_seconds"] + item["deadline_seconds"]
                  <= cutoff - start and item["id"] not in {s["invoice"] for s in settled if s["by_deadline"]}
                  for item in arrived),
              "delivery_slo_met_for_arrived_invoices": bool(arrived and
                  100 * paid_count >= 99 * len(arrived) and 100 * paid_sat >= 99 * offered_sat),
              "confirmed_txids": latest_confirmed_ids, "settlements": settled,
              "observed_seconds": cutoff - start,
              "recovery_and_reuse": latencies, "sample_end": cutoff, **metrics}
    return result, events


def export(directory, journal, plan):
    root = Path(__file__).resolve().parent
    matrix = json.loads((root / "capability-matrix.json").read_text(encoding="utf-8"))
    drafts = journal.data("drafts")
    attempts = list(journal.db.execute("SELECT position, started, height, event_order "
                                       "FROM attempts ORDER BY position"))
    observations = journal.data("observations")
    numbers, ledger = timeline(plan, drafts, attempts, observations)
    latest = observations[-1] if observations else {"phases": []}
    receipts = [phase["proof"] for phase in latest["phases"] if "proof" in phase]
    receipts.extend(phase["independent_inclusion"] for phase in latest["phases"]
                    if "independent_inclusion" in phase)
    for receipt in receipts:
        if "merkle_proof" in receipt:
            binary = bytes.fromhex(receipt["merkle_proof"])
            receipt["proof_bytes"] = len(binary)
            receipt["proof_sha256"] = hashlib.sha256(binary).hexdigest()
    result = {"campaign": plan["campaign"], "scope": plan["network"],
              "profile": plan["profile"], "plan_sha256": digest(plan),
              "initial_tip": plan["initial_tip"], "observed_tip": latest.get("tip"),
              "pinned_sources": matrix["sources"], "native_merkle_receipts": len(receipts),
              "fresh_nova_proof_receipts": 0, **numbers}
    failures = journal.data("failures")
    write_jsonl(directory / "transactions.jsonl", [
        {"kind": "signed_plan", **draft_public(draft)} for draft in drafts
    ] + [{"kind": "relay_attempt", "position": pos, "at": at, "height": height,
          "event_order": seq, "txid": drafts[pos]["txid"]} for pos, at, height, seq in attempts
         ] + [{"kind": "chain_observation", **row} for row in observations])
    write_jsonl(directory / "capital-ledger.jsonl", ledger)
    write_jsonl(directory / "proof-receipts.jsonl", receipts)
    output(directory / "capability-matrix.json", matrix)
    output(directory / "failure-ledger.json", failures)
    output(directory / "results.json", result)
    atomic(directory / "report.md", markdown(result, len(failures)))
    names = ("transactions.jsonl", "capital-ledger.jsonl", "proof-receipts.jsonl",
             "capability-matrix.json", "failure-ledger.json", "results.json", "report.md")
    output(directory / "manifest.json", {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                        for name in names})
    return result


def write_jsonl(path, rows):
    atomic(path, "".join(dump(row) + "\n" for row in rows))


def markdown(result, failure_count):
    return f"""# Capital Bound Moves campaign

Campaign `{result['campaign']}` used the `{result['profile']}` profile on `{result['scope']}`.

| Measure | Observed |
| --- | ---: |
| Initial funding, sats | {result['initial_funding_sat']} |
| Confirmed miner fees, sats | {result['confirmed_fees_sat']} |
| Confirmed settlement virtual bytes | {result['settlement_virtual_bytes']} |
| Offered invoices | {result['offered_invoices']} |
| Invoices settled by deadline | {result['settled_by_deadline_count']} |
| Value settled by deadline, sats | {result['settled_by_deadline_sat']} |
| Funded satoshi-blocks | {result['funded_sat_blocks']} |
| Unavailable satoshi-blocks | {result['unavailable_sat_blocks']} |
| Funded satoshi-seconds | {result['funded_sat_seconds']} |
| Unavailable satoshi-seconds | {result['unavailable_sat_seconds']} |
| Unavailable value at last observation, sats | {result['terminal_unavailable_sat']} |
| Native inclusion receipts | {result['native_merkle_receipts']} |
| Fresh Nova receipts | {result['fresh_nova_proof_receipts']} |
| Recorded command failures | {failure_count} |

The ledger uses the payer's canonical UTXO. Confirmed recipient outputs exit the payer's budget.
Block integrals use observed height advances above the previous high-water mark. Observer gaps
bound the timing resolution. Confirmation and unspent-change evidence comes from Bitcoin Core.
The current tip and any reorganization are recorded in the transaction observations.
"""

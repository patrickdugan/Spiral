"""Deterministic, explicitly simulated hackathon cases. No real keys or tokens."""
from dataclasses import asdict, replace

from .domain import ChainView, Evidence, Intent, Ledger, Refused, Rules, digest, plan_vtxo

NOW = 1794751200
SCRIPT = digest("demo:mint-deposit-script")

CASES = [
    {"id": "cashu", "name": "A payment reaches the Cashu desk", "group": "Accepted", "rail": "cashu",
     "description": "Bind a confirmed deposit to its fixed mint intent, then prepare one settlement request."},
    {"id": "ark", "name": "An Ark boarding payment", "group": "Accepted", "rail": "ark",
     "description": "Apply the same payment gate to an Ark intent. Bark still validates the board and exit tree."},
    {"id": "replay", "name": "One payment, two recipients", "group": "Rejected", "rail": "cashu",
     "description": "An attacker presents an already reserved payment for a different recipient."},
    {"id": "wrong-amount", "name": "A smaller deposit", "group": "Rejected", "rail": "cashu",
     "description": "A payment of 24,999 sats cannot satisfy a 25,000 sat intent."},
    {"id": "wrong-script", "name": "The wrong receiving script", "group": "Rejected", "rail": "ark",
     "description": "A valid payment to another script must never fund this intent."},
    {"id": "reorg", "name": "The deposit leaves the chain", "group": "Rejected", "rail": "cashu",
     "description": "A previously included payment is absent from the current active chain."},
    {"id": "stale", "name": "An old chain snapshot", "group": "Rejected", "rail": "ark",
     "description": "A stale chain view cannot authorize a new settlement request."},
    {"id": "operator-report", "name": "A mint says “paid”", "group": "Rejected", "rail": "cashu",
     "description": "A provider report cannot replace locally verified payment evidence."},
]


def sample() -> tuple[Intent, Evidence, ChainView, Rules]:
    intent = Intent("demo-cashu-25000", "regtest", SCRIPT, 25000, "demo:fixed-recipient", "cashu", NOW + 3600)
    evidence = Evidence("regtest", digest("demo:payment"), 0, 25000, SCRIPT,
                        digest("demo:block"), 1000, digest("demo:tip"), 1005, 9000, 6,
                        digest("demo:statement"), digest("demo:proof-placeholder"), "fixture")
    chain = ChainView("regtest", evidence.tip_hash, 1005, NOW, evidence.block_hash, 1000, "fixture")
    return intent, evidence, chain, Rules("regtest", min_chainwork=8000, mode="demo")


def run_case(case_id: str) -> dict:
    case = next((c for c in CASES if c["id"] == case_id), None)
    if case is None:
        raise Refused("unknown_case")
    intent, evidence, chain, rules = sample()
    if case["rail"] == "ark":
        intent = replace(intent, id="demo-ark-25000", rail="ark", beneficiary="demo:ark-recipient")
    ledger = Ledger(":memory:", "demo")
    try:
        ledger.add_intent(intent)
        if case_id == "wrong-amount":
            evidence = replace(evidence, value_sats=24999)
        if case_id == "wrong-script":
            evidence = replace(evidence, script_sha256=digest("demo:other-script"))
        if case_id == "reorg":
            chain = replace(chain, block_hash=digest("demo:replacement-block"))
        if case_id == "stale":
            chain = replace(chain, observed_at=NOW - 121)
        if case_id == "operator-report":
            evidence = replace(evidence, kind="operator-report")
        try:
            if case_id == "replay":
                ledger.prepare(intent.id, evidence, chain, rules, NOW)
                intent = replace(intent, id="demo-attacker", beneficiary="demo:different-recipient")
                ledger.add_intent(intent)
            receipt = ledger.prepare(intent.id, evidence, chain, rules, NOW)
            decision = {"accepted": True, "code": "prepared", "receipt": receipt}
        except Refused as exc:
            decision = {"accepted": False, "code": exc.code, "detail": exc.detail, "receipt": None}
        return {"case": case, "evidence_level": "fixture", "simulation": True,
                "decision": decision, "intent": asdict(intent), "evidence": asdict(evidence),
                "chain": asdict(chain), "receipts": ledger.receipts(),
                "steps": [
                    {"name": "Receive payment evidence", "state": "fixture", "detail": "Deterministic regtest display data."},
                    {"name": "Check proof and chain", "state": "simulated", "detail": "Native M16 verification runs only in connected mode."},
                    {"name": "Bind the payment intent", "state": "accepted" if decision["accepted"] else "rejected", "detail": decision["code"]},
                    {"name": "Reserve once", "state": "prepared" if decision["accepted"] else "blocked", "detail": "Atomic SQLite outpoint and intent reservation."},
                    {"name": "Settle with Cashu / Ark", "state": "pending", "detail": "No tokens issued and no Bitcoin transaction sent."},
                ]}
    finally:
        ledger.close()


def vtxos() -> list[dict]:
    base = {"value_sats": 50000, "exit_budget_blocks": 24, "exit_package_validated": True, "operator_online": True}
    return [
        {**base, "id": "demo-vtxo-a", "expiry_height": 1400},
        {**base, "id": "demo-vtxo-b", "value_sats": 25000, "expiry_height": 1120},
        {**base, "id": "demo-vtxo-c", "value_sats": 18000, "expiry_height": 1060, "operator_online": False},
    ]


def plans(tip: int = 1005) -> list[dict]:
    return [plan_vtxo(v, tip) for v in vtxos()]

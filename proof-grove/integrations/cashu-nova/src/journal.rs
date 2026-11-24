//! Canonical inputs for auditing a declared protected-mint journal.
use proof_grove_cashu_nova::{
    check_step, commitment, context, CashuStep, Id, Ledger, Operation, State, F,
};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::Read;
use std::path::Path;

const MAX_JSON_BYTES: u64 = 256 * 1024;
const MAX_STEPS: usize = 256;
const REGTEST_GENESIS: &str = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Journal {
    schema: String,
    genesis: String,
    mint_profile_sha256: String,
    events: Vec<Event>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Event {
    funding_txid: String,
    funding_vout: u32,
    amount_sats: u64,
    evidence_sha256: String,
    action: Action,
}

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum Action {
    Register {
        intent: String,
    },
    Issue {
        intent: String,
        claim: String,
    },
    Split {
        input: String,
        first: String,
        second: String,
        first_sats: u64,
    },
    Swap {
        input: String,
        output: String,
    },
    Redeem {
        input: String,
        reserve_before_sats: u64,
    },
}

pub struct Replay {
    pub initial: State,
    pub expected: State,
    pub prior_journal_root: F,
    pub steps: Vec<CashuStep>,
    pub constraints: usize,
    pub sha256: String,
}

fn bytes32(value: &str) -> Result<[u8; 32], &'static str> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("expected canonical 32-byte hex");
    }
    let mut bytes = [0; 32];
    hex::decode_to_slice(value, &mut bytes).map_err(|_| "invalid hex")?;
    Ok(bytes)
}

fn id(label: &str, encoded: &str) -> Result<Id, &'static str> {
    Ok(commitment(label, &bytes32(encoded)?))
}

fn replay(raw: &[u8], pin: Option<&str>) -> Result<Replay, Box<dyn std::error::Error>> {
    let sha256 = hex::encode(Sha256::digest(raw));
    if let Some(pin) = pin {
        bytes32(pin)?;
        if pin != sha256 {
            return Err("journal SHA-256 does not match the pinned journal".into());
        }
    }
    let journal: Journal = serde_json::from_slice(raw)?;
    if journal.schema != "proof-grove/cashu-nova-journal/v1"
        || journal.genesis != REGTEST_GENESIS
        || !(1..=MAX_STEPS).contains(&journal.events.len())
    {
        return Err("invalid journal schema, regtest genesis, or event count".into());
    }
    let genesis = bytes32(&journal.genesis)?;
    let profile = bytes32(&journal.mint_profile_sha256)?;
    let ledger_context = context(commitment("ledger-context", &[genesis, profile].concat()));
    let mut ledger = Ledger::empty(ledger_context);
    let initial = ledger.state();
    let mut steps = Vec::with_capacity(journal.events.len());
    let mut constraints = 0;
    let mut prior_journal_root = initial[8];

    for (index, event) in journal.events.into_iter().enumerate() {
        let txid = bytes32(&event.funding_txid)?;
        let funding = [
            genesis.as_slice(),
            txid.as_slice(),
            &event.funding_vout.to_be_bytes(),
        ]
        .concat();
        let mut step = CashuStep::default();
        step.reserve = commitment("reserve-outpoint", &funding);
        step.amount = event.amount_sats;
        step.evidence = id("event-evidence", &event.evidence_sha256)?;
        match event.action {
            Action::Register { intent } => {
                step.operation = Operation::Register;
                step.intent = id("issue-intent", &intent)?;
            }
            Action::Issue { intent, claim } => {
                step.operation = Operation::Issue;
                step.intent = id("issue-intent", &intent)?;
                step.outputs[0] = id("claim", &claim)?;
            }
            Action::Split {
                input,
                first,
                second,
                first_sats,
            } => {
                step.operation = Operation::Split;
                step.input = id("claim", &input)?;
                step.outputs = [id("claim", &first)?, id("claim", &second)?];
                step.split_first = first_sats;
            }
            Action::Swap { input, output } => {
                step.operation = Operation::Swap;
                step.input = id("claim", &input)?;
                step.outputs[0] = id("claim", &output)?;
            }
            Action::Redeem {
                input,
                reserve_before_sats,
            } => {
                step.operation = Operation::Redeem;
                step.input = id("claim", &input)?;
                step.reserve_before = reserve_before_sats;
            }
        }
        let before = ledger.state();
        prior_journal_root = before[8];
        let witness = ledger
            .apply(step)
            .map_err(|why| format!("event {index}: {why}"))?;
        let (after, count) = check_step(&before, &witness)
            .map_err(|constraint| format!("event {index} failed constraint {constraint}"))?;
        if after != ledger.state() {
            return Err(format!("event {index} produced a different native state").into());
        }
        constraints = count;
        steps.push(witness);
    }
    Ok(Replay {
        initial,
        expected: ledger.state(),
        prior_journal_root,
        steps,
        constraints,
        sha256,
    })
}

pub fn read(path: &Path, pin: Option<&str>) -> Result<Replay, Box<dyn std::error::Error>> {
    let mut raw = Vec::new();
    File::open(path)?
        .take(MAX_JSON_BYTES + 1)
        .read_to_end(&mut raw)?;
    if raw.is_empty() || raw.len() as u64 > MAX_JSON_BYTES {
        return Err("unexpected journal length".into());
    }
    replay(&raw, pin)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn registration_rejects_the_same_funding_outpoint_under_another_intent() {
        let mut event = json!({
            "funding_txid": "10".repeat(32), "funding_vout": 2, "amount_sats": 25000,
            "evidence_sha256": "20".repeat(32), "action": {"kind":"register", "intent":"30".repeat(32)}
        });
        let mut journal = json!({"schema":"proof-grove/cashu-nova-journal/v1", "genesis":REGTEST_GENESIS,
                                 "mint_profile_sha256":"40".repeat(32), "events":[event.clone()]});
        let good = serde_json::to_vec(&journal).unwrap();
        let good_sha = hex::encode(Sha256::digest(&good));
        assert!(replay(&good, Some(&good_sha)).is_ok());
        event["action"]["intent"] = json!("50".repeat(32));
        journal["events"].as_array_mut().unwrap().push(event);
        let bad = serde_json::to_vec(&journal).unwrap();
        assert!(replay(&bad, Some(&good_sha))
            .err()
            .unwrap()
            .to_string()
            .contains("SHA-256"));
        assert!(replay(&bad, None)
            .err()
            .unwrap()
            .to_string()
            .contains("membership or vacancy"));
    }
}

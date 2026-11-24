use bincode::Options;
use nova_snark::nova::{CompressedSNARK, PublicParams, RecursiveSNARK};
use nova_snark::provider::{ipa_pc::EvaluationEngine, PallasEngine, VestaEngine};
use nova_snark::spartan::snark::RelaxedR1CSSNARK;
use nova_snark::traits::snark::RelaxedR1CSSNARKTrait;
use proof_grove_cashu_nova::{
    check_step, commitment, context, field_hex, CashuStep, Ledger, Operation, State,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Read;
use std::path::Path;
use std::time::Instant;

mod journal;

type E1 = PallasEngine;
type E2 = VestaEngine;
type S1 = RelaxedR1CSSNARK<E1, EvaluationEngine<E1>>;
type S2 = RelaxedR1CSSNARK<E2, EvaluationEngine<E2>>;
type PP = PublicParams<E1, E2, CashuStep>;
type RS = RecursiveSNARK<E1, E2, CashuStep>;
type CS = CompressedSNARK<E1, E2, CashuStep, S1, S2>;
const MAX_PROOF_BYTES: u64 = 4 * 1024 * 1024;

fn demo() -> (State, Vec<CashuStep>, State, usize) {
    let domain = commitment("ledger-context", b"regtest/fixture-mint/protected-cashu-v1");
    let mut ledger = Ledger::empty(context(domain));
    let initial = ledger.state();
    let reserve = commitment(
        "reserve-outpoint",
        b"one confirmed fixture funding outpoint",
    );
    let intent = commitment("issue-intent", b"one quote and prepared issuance");
    let claim = |name| commitment("claim", name);
    let (issued, split1, split2, swapped) = (
        claim(b"issued"),
        claim(b"split1"),
        claim(b"split2"),
        claim(b"swapped"),
    );
    let details = [
        (
            Operation::Register,
            [0; 2],
            [[0; 2]; 2],
            25_000,
            0,
            0,
            "funding",
        ),
        (
            Operation::Issue,
            [0; 2],
            [issued, [0; 2]],
            25_000,
            0,
            0,
            "issue",
        ),
        (
            Operation::Split,
            issued,
            [split1, split2],
            25_000,
            15_000,
            0,
            "split",
        ),
        (
            Operation::Swap,
            split1,
            [swapped, [0; 2]],
            15_000,
            0,
            0,
            "swap",
        ),
        (
            Operation::Redeem,
            swapped,
            [[0; 2]; 2],
            15_000,
            0,
            25_000,
            "redeem",
        ),
    ];
    let mut steps = Vec::new();
    let mut constraints = 0;
    for (operation, input, outputs, amount, split_first, reserve_before, label) in details {
        let mut step = CashuStep::default();
        step.operation = operation;
        step.reserve = reserve;
        step.intent = intent;
        step.input = input;
        step.outputs = outputs;
        step.amount = amount;
        step.split_first = split_first;
        step.reserve_before = reserve_before;
        step.evidence = commitment("fixture-admission", label.as_bytes());
        let before = ledger.state();
        let witness = ledger.apply(step).expect("valid fixture");
        let (after, count) = check_step(&before, &witness).expect("fixture satisfies constraints");
        assert_eq!(after, ledger.state());
        constraints = count;
        steps.push(witness);
    }
    (initial, steps, ledger.state(), constraints)
}

fn bounded_proof(path: &Path) -> std::io::Result<Vec<u8>> {
    let mut proof = Vec::new();
    fs::File::open(path)?
        .take(MAX_PROOF_BYTES + 1)
        .read_to_end(&mut proof)?;
    if proof.is_empty() || proof.len() as u64 > MAX_PROOF_BYTES {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "unexpected proof length",
        ));
    }
    Ok(proof)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let argv: Vec<_> = std::env::args_os().skip(1).collect();
    let mode = argv
        .first()
        .and_then(|command| command.to_str())
        .unwrap_or_default();
    let (output, (initial, steps, expected, count), journal_context) = match (mode, argv.as_slice()) {
        ("prove-demo" | "verify-demo", [_, output]) => (Path::new(output), demo(), None),
        ("prove-journal", [_, output, journal]) => {
            let replay = journal::read(Path::new(journal), None)?;
            (Path::new(output), (replay.initial, replay.steps, replay.expected, replay.constraints), Some((replay.sha256, field_hex(replay.prior_journal_root))))
        }
        ("verify-journal", [_, output, journal, pin]) => {
            let replay = journal::read(Path::new(journal), Some(pin.to_str().ok_or("invalid journal SHA-256")?))?;
            (Path::new(output), (replay.initial, replay.steps, replay.expected, replay.constraints), Some((replay.sha256, field_hex(replay.prior_journal_root))))
        }
        _ => return Err("usage: proof-grove-cashu-nova {prove-demo|verify-demo} DIR | prove-journal DIR JOURNAL | verify-journal DIR JOURNAL EXPECTED_SHA256".into()),
    };
    let start = Instant::now();
    let pp = PP::setup(&CashuStep::default(), &*S1::ck_floor(), &*S2::ck_floor())?;
    let (pk, vk) = CS::setup(&pp)?;
    let vk_id = hex::encode(Sha256::digest(bincode::serialize(&vk)?));
    let setup_seconds = start.elapsed().as_secs_f64();
    let start = Instant::now();
    let (bytes, fold_seconds, compress_seconds) = if matches!(mode, "prove-demo" | "prove-journal")
    {
        let mut proof = RS::new(&pp, &steps[0], &initial)?;
        for step in &steps {
            proof.prove_step(&pp, step)?;
        }
        assert_eq!(proof.verify(&pp, steps.len(), &initial)?, expected);
        let fold_seconds = start.elapsed().as_secs_f64();
        let compress_start = Instant::now();
        let compressed = CS::prove(&pp, &pk, &proof)?;
        let bytes = bincode::serialize(&compressed)?;
        let compress_seconds = compress_start.elapsed().as_secs_f64();
        fs::create_dir(output)?;
        fs::write(output.join("nova-proof.bin"), &bytes)?;
        (bytes, Some(fold_seconds), Some(compress_seconds))
    } else {
        (bounded_proof(&output.join("nova-proof.bin"))?, None, None)
    };

    // A verifier recomputes the checkpoint and expected root from the fixture
    // or its independently pinned journal, then checks the compressed proof.
    let verify_start = Instant::now();
    let proof: CS = bincode::DefaultOptions::new()
        .with_fixint_encoding()
        .with_limit(MAX_PROOF_BYTES)
        .reject_trailing_bytes()
        .deserialize(&bytes)?;
    if bincode::serialize(&proof)? != bytes {
        return Err("noncanonical proof serialization".into());
    }
    let after = proof.verify(&vk, steps.len(), &initial)?;
    if after != expected {
        return Err("proof terminated at a different accounting state".into());
    }
    let verify_seconds = verify_start.elapsed().as_secs_f64();
    let mut wrong_anchor = initial;
    wrong_anchor[9] += proof_grove_cashu_nova::F::from(1u64);
    assert!(proof.verify(&vk, steps.len(), &wrong_anchor).is_err());
    assert!(proof.verify(&vk, steps.len() + 1, &initial).is_err());
    let peak = fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|status| {
            status
                .lines()
                .find(|line| line.starts_with("VmHWM:"))
                .and_then(|line| line.split_whitespace().nth(1))
                .and_then(|value| value.parse::<u64>().ok())
        });
    let operations: Vec<_> = steps
        .iter()
        .map(|step| match step.operation {
            Operation::Register => "register",
            Operation::Issue => "issue",
            Operation::Split => "split",
            Operation::Swap => "swap",
            Operation::Redeem => "redeem",
        })
        .collect();
    let balance = |index: usize| u64::from_str_radix(&field_hex(expected[index])[48..], 16);
    let receipt = json!({
        "schema": "proof-grove/cashu-nova-regtest-accounting/v1",
        "mode": mode, "verified": true, "proof_bytes": bytes.len(),
        "proof_sha256": hex::encode(Sha256::digest(&bytes)), "verifier_key_sha256": vk_id,
        "constraints_per_step": count, "steps": steps.len(), "operations": operations,
        "journal_sha256": journal_context.as_ref().map(|(sha256, _)| sha256),
        "before_final_journal_root": journal_context.as_ref().map(|(_, root)| root),
        "z0": initial.map(field_hex), "zn": expected.map(field_hex),
        "declared_reserve_sats": balance(4)?, "outstanding_claims_sats": balance(6)?,
        "setup_seconds": setup_seconds, "fold_seconds": fold_seconds, "compress_seconds": compress_seconds,
        "verify_seconds": verify_seconds, "peak_rss_kib": peak,
        "rejected": ["different_context_anchor", "wrong_step_count"],
        "scope": "declared accounting, with external admission evidence commitments"
    });
    println!("{}", serde_json::to_string_pretty(&receipt)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_mutated_witness_and_old_paths() {
        let (initial, steps, final_state, _) = demo();
        assert!(
            check_step(&final_state, &steps[0]).is_err(),
            "outpoint and intent reuse"
        );
        assert!(
            check_step(&final_state, &steps[1]).is_err(),
            "repeated issuance"
        );
        assert!(
            check_step(&final_state, &steps[4]).is_err(),
            "repeated redemption"
        );
        assert!(
            check_step(&initial, &steps[4]).is_err(),
            "redemption before issuance"
        );

        let (funded, _) = check_step(&initial, &steps[0]).unwrap();
        let mut changed = steps[1].clone();
        changed.amount += 1;
        assert!(check_step(&funded, &changed).is_err(), "overissuance");
        let (issued, _) = check_step(&funded, &steps[1]).unwrap();
        changed = steps[2].clone();
        changed.split_first = changed.amount + 1;
        assert!(check_step(&issued, &changed).is_err(), "split range");
        changed = steps[2].clone();
        changed.outputs[1] = changed.outputs[0];
        assert!(
            check_step(&issued, &changed).is_err(),
            "duplicate split output"
        );
        changed = steps[2].clone();
        changed.outputs[0] = changed.input;
        assert!(check_step(&issued, &changed).is_err(), "reused spent ID");
        changed = steps[2].clone();
        changed.reserve = commitment("reserve-outpoint", b"substitute reserve");
        assert!(
            check_step(&issued, &changed).is_err(),
            "wrong reserve binding"
        );
    }
}

//! Run the pinned prover on an existing Cairo execution input.

use std::{fs::File, path::PathBuf};

use anyhow::{ensure, Context, Result};
use cairo_air::utils::ProofFormat;
use stwo_cairo_adapter::ProverInput;
use stwo_cairo_prover::prover::create_and_serialize_proof;
use tracing_subscriber::fmt::format::FmtSpan;

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    let [input, profile, output] = args.as_slice() else {
        anyhow::bail!("usage: prove-json PROVER_INPUT.json PROFILE.json NEW_PROOF.json");
    };
    ensure!(!output.exists(), "proof output already exists");
    tracing_subscriber::fmt()
        .with_span_events(FmtSpan::ENTER | FmtSpan::CLOSE)
        .init();
    let span = tracing::info_span!("decode_prover_input").entered();
    let input: ProverInput = serde_json::from_reader(
        File::open(input).context("open pinned Cairo prover input")?,
    )?;
    drop(span);
    let _span = tracing::info_span!("create_and_serialize_proof").entered();
    create_and_serialize_proof(input, false, output.clone(), ProofFormat::Json, Some(profile.clone()))
}

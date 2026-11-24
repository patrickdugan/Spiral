//! Prove a saved Cairo input with the pinned CUDA candidate and archive stock JSON.

use std::{
    fs::File,
    io::BufReader,
    path::{Path, PathBuf},
};

use anyhow::{ensure, Context, Result};
use cairo_air::utils::{serialize_proof_to_file, ProofFormat};
use serde_json::{json, Value};
use stwo::core::vcs_lifted::blake2_merkle::Blake2sMerkleChannel;
use stwo_cairo_adapter::ProverInput;
use stwo_cairo_prover::{prove_cairo_cuda, prover::ProverParameters};
use tracing_subscriber::fmt::format::FmtSpan;

fn pinned_parameters(profile: &Path, smoke: bool) -> Result<ProverParameters> {
    let mut value: Value = serde_json::from_reader(BufReader::new(
        File::open(profile).context("open pinned Cairo profile")?,
    ))?;
    let split = value
        .as_object_mut()
        .context("expected a Cairo profile object")?
        .remove("opt_n_id_to_big_components");
    ensure!(
        split.is_none_or(|value| value.is_null()),
        "CUDA component split override is unsupported"
    );
    let (pow, queries, lifting, trace) = if smoke {
        (10, 3, 22, "canonical_small")
    } else {
        (26, 70, 26, "canonical_without_pedersen")
    };
    let expected = json!({
        "channel_hash": "blake2s",
        "channel_salt": 0,
        "pcs_config": {
            "pow_bits": pow,
            "fri_config": {
                "log_last_layer_degree_bound": 0,
                "log_blowup_factor": 1,
                "n_queries": queries,
                "fold_step": 1,
            },
            "lifting_log_size": lifting,
        },
        "preprocessed_trace": trace,
        "store_polynomials_coefficients": false,
        "include_all_preprocessed_columns": false,
    });
    ensure!(
        value == expected,
        "Cairo profile differs from the pinned CUDA adapter profile"
    );
    // The pinned 1.1.0 profile predates this optional field in the 1.2.2 candidate.
    value["opt_n_id_to_big_components"] = Value::Null;
    serde_json::from_value(value).context("decode pinned CUDA prover parameters")
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    let (input, profile, output, smoke) = match args.as_slice() {
        [input, profile, output] => (input, profile, output, false),
        [flag, input, profile, output] if flag.as_path() == Path::new("--smoke") => {
            (input, profile, output, true)
        }
        _ => anyhow::bail!(
            "usage: prove-json-cuda [--smoke] PROVER_INPUT.json PROFILE.json NEW_PROOF.json"
        ),
    };
    ensure!(!output.exists(), "proof output already exists");
    let profile = pinned_parameters(profile, smoke)?;
    tracing_subscriber::fmt()
        .with_span_events(FmtSpan::ENTER | FmtSpan::CLOSE)
        .init();
    let span = tracing::info_span!("decode_prover_input").entered();
    let input: ProverInput = serde_json::from_reader(BufReader::new(
        File::open(input).context("open pinned Cairo prover input")?,
    ))?;
    drop(span);
    vortexstark::cuda::ffi::init_memory_pool();
    let span = tracing::info_span!("prove_saved_input_cuda").entered();
    let proof = prove_cairo_cuda::<Blake2sMerkleChannel>(input, profile)
        .context("prove saved Cairo input with CUDA")?;
    drop(span);
    let _span = tracing::info_span!("serialize_proof").entered();
    serialize_proof_to_file(&proof, output, ProofFormat::Json)
        .context("write stock verifier JSON proof")
}

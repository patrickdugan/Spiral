//! Verified compressed proving over the supplied SP1 backend.
use std::{
    fs::{File, OpenOptions},
    path::Path,
    sync::{atomic::Ordering, Arc},
    time::Instant,
};

use anyhow::{ensure, Context, Result};
use sha2::{Digest, Sha256};
use slop_algebra::PrimeField32;
use sp1_core_executor::{ELEMENT_THRESHOLD, HEIGHT_THRESHOLD, MINIMAL_TRACE_CHUNK_THRESHOLD};
use sp1_core_machine::riscv::RiscvAir;
use sp1_sdk::{HashableKey, SP1ProofWithPublicValues, SP1Stdin};

use crate::{
    backend::Backend,
    config::{fresh_nonce, RunConfig, SP1_VERSION},
    memo::{Kind, Memo},
    node::ShardedNode,
};

/// Settings that determine shard boundaries and must match across resumes.
#[derive(Clone, Copy, Debug)]
pub struct ShardConfig {
    pub element_threshold: u64,
    pub height_threshold: u64,
    pub shard_size: usize,
    pub minimal_trace_chunk_threshold: u64,
    pub trace_chunk_slots: usize,
    pub full_size_shards: bool,
}

impl Default for ShardConfig {
    fn default() -> Self {
        Self {
            element_threshold: ELEMENT_THRESHOLD,
            height_threshold: HEIGHT_THRESHOLD,
            shard_size: 1usize << 24,
            minimal_trace_chunk_threshold: MINIMAL_TRACE_CHUNK_THRESHOLD,
            trace_chunk_slots: 2,
            full_size_shards: false,
        }
    }
}

/// A single resumable proof request. The caller loads the ELF and guest inputs.
pub struct ProveRequest<'a> {
    pub elf: &'a [u8],
    pub inputs: &'a [Vec<u8>],
    pub run_dir: &'a Path,
    pub proof_path: &'a Path,
    pub sharding: ShardConfig,
    /// Limits in-flight worker tasks. A host RAM/swap cap is enforced outside this process.
    pub permits: usize,
    /// If supplied, execute first and require this digest of the committed public values.
    pub expected_public_sha256: Option<&'a str>,
}

pub(crate) fn sha_hex(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

fn lock_run_dir(run_dir: &Path) -> Result<File> {
    std::fs::create_dir_all(run_dir)?;
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(run_dir.join(".nb3-prover.lock"))?;
    file.try_lock()
        .with_context(|| format!("cannot lock prover run directory {}", run_dir.display()))?;
    Ok(file)
}

/// Resume or prove a guest, verify the compressed proof, then write the proof and result.json.
/// The caller configures the worker environment and any process-level resource limits.
pub async fn prove<B: Backend>(request: ProveRequest<'_>, backend: B) -> Result<serde_json::Value> {
    let ProveRequest {
        elf,
        inputs,
        run_dir,
        proof_path: out,
        sharding,
        permits,
        expected_public_sha256,
    } = request;
    ensure!(permits > 0, "prover permits must be positive");
    let _lock = lock_run_dir(run_dir)?;
    let fresh = RunConfig {
        sp1_version: SP1_VERSION.into(),
        elf_sha256: sha_hex(elf),
        inputs_sha256: inputs.iter().map(|bytes| sha_hex(bytes)).collect(),
        element_threshold: sharding.element_threshold,
        height_threshold: sharding.height_threshold,
        shard_size: sharding.shard_size,
        minimal_trace_chunk_threshold: sharding.minimal_trace_chunk_threshold,
        trace_chunk_slots: sharding.trace_chunk_slots,
        full_size_shards: sharding.full_size_shards,
        nonce: fresh_nonce(),
    };
    let (cfg, resumed) = RunConfig::load_or_init(run_dir, fresh)?;
    let memo = Arc::new(Memo::open(run_dir, cfg.digest())?);
    let (prior_shards, prior_reduces) = (
        Memo::count(run_dir, Kind::Shard),
        Memo::count(run_dir, Kind::Reduce),
    );
    tracing::info!(
        "run {} ({}): {prior_shards} shard and {prior_reduces} recursion tasks already recorded",
        run_dir.display(),
        if resumed { "resumed" } else { "new" }
    );

    let mut stdin = SP1Stdin::new();
    for b in inputs {
        stdin.write_vec(b.clone());
    }

    let mut opts = cfg.core_opts();
    backend.adjust_opts(&mut opts);
    let builder = backend
        .worker_builder(RiscvAir::machine(), &opts, permits)
        .await?;
    let node = ShardedNode::build(run_dir, memo.clone(), opts, builder).await?;
    tracing::info!("backend: {}", backend.name());

    let mut instructions = None;
    if let Some(expect) = expected_public_sha256 {
        // Refuse to spend proving time on an input the guest rejects.
        let t = Instant::now();
        let (pv, report) = node.execute(elf, stdin.clone()).await?;
        ensure!(
            report.exit_code == 0,
            "guest exits with code {}",
            report.exit_code
        );
        ensure!(
            sha_hex(pv.as_slice()) == expect,
            "committed public values differ from --expect-public-sha256"
        );
        instructions = Some(report.total_instruction_count());
        tracing::info!(
            "executed: {} instructions in {:.1} s, public values match",
            report.total_instruction_count(),
            t.elapsed().as_secs_f64()
        );
    }

    let vk = node.setup(elf).await?;

    let started = Instant::now();
    let mut ticker = tokio::task::JoinSet::new();
    {
        let (memo, store) = (memo.clone(), node.store.clone());
        ticker.spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(60)).await;
                let c = &memo.counters;
                let (sp, sr) = (c.shard_proved.load(Ordering::Relaxed), c.shard_replayed.load(Ordering::Relaxed));
                let (rp, rr) = (c.reduce_proved.load(Ordering::Relaxed), c.reduce_replayed.load(Ordering::Relaxed));
                let ms = c.shard_prove_ms.load(Ordering::Relaxed);
                tracing::info!(
                    "progress {:.0} s: shards proved {sp} replayed {sr} (mean {:.1} s), recursion proved {rp} replayed {rr}, store {} MiB",
                    started.elapsed().as_secs_f64(),
                    if sp > 0 { ms as f64 / sp as f64 / 1000.0 } else { 0.0 },
                    store.live_bytes() >> 20
                );
            }
        });
    }

    let proof = node.prove_compressed(elf, stdin, cfg.nonce).await;
    ticker.shutdown().await;
    let proof = proof?;
    let prove_s = started.elapsed().as_secs_f64();
    node.core
        .verify(&vk, &proof.proof)
        .context("SP1 rejects the compressed proof")?;

    let committed = sha_hex(proof.public_values.as_slice());
    let proof: SP1ProofWithPublicValues = proof.into();
    proof.save(out)?;

    let c = &memo.counters;
    let vk_digest: Vec<u8> = vk
        .hash_koalabear()
        .iter()
        .flat_map(|x| x.as_canonical_u32().to_le_bytes())
        .collect();
    let result = serde_json::json!({
        "status": "compressed_proof_verified",
        "backend": backend.name(),
        "elf_sha256": cfg.elf_sha256,
        "program_vk_digest": hex::encode(vk_digest),
        "program_vkey_bytes32": vk.bytes32(),
        "committed_values_sha256": committed,
        "instructions": instructions,
        "prove_seconds": prove_s,
        "shard_tasks": { "proved": c.shard_proved.load(Ordering::Relaxed), "replayed": c.shard_replayed.load(Ordering::Relaxed) },
        "recursion_tasks": { "proved": c.reduce_proved.load(Ordering::Relaxed), "replayed": c.reduce_replayed.load(Ordering::Relaxed) },
        "proof_path": out, "proof_file_bytes": std::fs::metadata(out)?.len(),
    });
    std::fs::write(
        run_dir.join("result.json"),
        serde_json::to_string_pretty(&result)? + "\n",
    )?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_directory_can_be_reopened_after_the_owner_releases_it() -> Result<()> {
        let suffix = fresh_nonce()[0];
        let directory =
            std::env::temp_dir().join(format!("nb3-run-lock-{}-{suffix}", std::process::id()));
        let writer = lock_run_dir(&directory)?;
        let competing_writer = lock_run_dir(&directory);
        drop(writer);
        let resumed = lock_run_dir(&directory)?;
        drop(resumed);
        std::fs::remove_file(directory.join(".nb3-prover.lock"))?;
        std::fs::remove_dir(directory)?;
        assert!(competing_writer.is_err());
        Ok(())
    }
}

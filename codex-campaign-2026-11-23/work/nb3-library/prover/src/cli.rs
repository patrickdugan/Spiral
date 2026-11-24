//! The nb3-prove command line, over any [`Backend`] (`nb3-prove` is the CPU binary,
//! `nb3-prove-gpu` in `nova-bitvm3/prover-gpu` the CUDA one).
//!
//!   nb3-prove prove --elf ELF --input FILE [--input FILE ...] --run-dir DIR --out PROOF.bin
//!                   [--element-threshold N] [--height-threshold N] [--shard-size N]
//!                   [--trace-chunk-threshold N] [--trace-chunk-slots N] [--permits N]
//!                   [--expect-public-sha256 HEX] [--sp1-worker-defaults]
//!       Each --input is written to the guest's stdin with `write_vec`, in order. Rerunning the
//!       same command after an interruption replays every finished shard and recursion task from
//!       DIR/memo and proves only what is missing. The proof is verified, then saved in SP1's
//!       `SP1ProofWithPublicValues` format (the format `m13 shrink-wrap` reads).
//!
//!   nb3-prove execute --elf ELF --input FILE [--input FILE ...] [--expect-public-sha256 HEX]
//!       Executes without proving: instruction count, syscall counts, cycle-tracker spans.
//!
//!   nb3-prove status --run-dir DIR
//!       Tasks recorded so far, mean proving time per task, and the result once finished.
use std::{
    path::{Path, PathBuf},
    time::Instant,
};

use anyhow::{bail, ensure, Context, Result};
use crate::{
    backend::Backend,
    config::RunConfig,
    memo::{Kind, Memo},
    prove::{sha_hex, ProveRequest, ShardConfig},
};
use sp1_sdk::SP1Stdin;

/// SP1 worker-pool settings for a single machine with limited RAM: one task of each kind in
/// flight. Applied only where the environment does not already set them.
const LOW_MEMORY_WORKERS: &[(&str, &str)] = &[
    ("SP1_WORKER_NUM_CORE_WORKERS", "1"),
    ("SP1_WORKER_NUM_RECURSION_PROVER_WORKERS", "1"),
    ("SP1_WORKER_NUM_RECURSION_EXECUTOR_WORKERS", "1"),
    ("SP1_WORKER_NUM_PREPARE_REDUCE_WORKERS", "1"),
    ("SP1_WORKER_NUM_SETUP_WORKERS", "1"),
    ("SP1_WORKER_NUM_SPLICING_WORKERS", "1"),
    ("SP1_WORKER_NUM_DEFERRED_WORKERS", "1"),
    ("SP1_WORKER_CORE_BUFFER_SIZE", "1"),
    ("SP1_WORKER_RECURSION_EXECUTOR_BUFFER_SIZE", "1"),
    ("SP1_WORKER_RECURSION_PROVER_BUFFER_SIZE", "1"),
    ("SP1_WORKER_SETUP_BUFFER_SIZE", "1"),
    ("SP1_WORKER_NUMBER_OF_GAS_EXECUTORS", "1"),
    ("SP1_WORKER_NUMBER_OF_SEND_SPLICE_WORKERS_PER_SPLICE", "1"),
    ("SP1_WORKER_SPLICING_BUFFER_SIZE", "1"),
];

struct Args(Vec<String>);

impl Args {
    fn one(&self, flag: &str) -> Option<String> {
        self.0.iter().position(|a| a == flag).and_then(|i| self.0.get(i + 1)).cloned()
    }
    fn all(&self, flag: &str) -> Vec<String> {
        self.0.windows(2).filter(|w| w[0] == flag).map(|w| w[1].clone()).collect()
    }
    fn has(&self, flag: &str) -> bool {
        self.0.iter().any(|a| a == flag)
    }
    fn need(&self, flag: &str) -> Result<String> {
        self.one(flag).with_context(|| format!("missing {flag}"))
    }
    fn num<T: std::str::FromStr>(&self, flag: &str, default: T) -> Result<T>
    where
        T::Err: std::fmt::Display,
    {
        match self.one(flag) {
            None => Ok(default),
            Some(s) => s.parse().map_err(|e| anyhow::anyhow!("{flag} {s}: {e}")),
        }
    }
}

/// Runs the command line with the provers of `backend`.
pub async fn main_with<B: Backend>(backend: B) -> Result<()> {
    let args = Args(std::env::args().collect());
    match args.0.get(1).map(String::as_str) {
        Some("prove") => prove(&args, backend).await,
        Some("execute") => execute(&args).await,
        Some("status") => status(Path::new(&args.need("--run-dir")?)),
        _ => bail!("usage: see the header of src/main.rs"),
    }
}

async fn prove<B: Backend>(args: &Args, backend: B) -> Result<()> {
    if !args.has("--sp1-worker-defaults") {
        for (k, v) in LOW_MEMORY_WORKERS {
            if std::env::var_os(k).is_none() {
                std::env::set_var(k, v);
            }
        }
    }
    sp1_sdk::utils::setup_logger();

    let elf = std::fs::read(args.need("--elf")?).context("reading --elf")?;
    let inputs: Vec<Vec<u8>> =
        args.all("--input").iter().map(|p| std::fs::read(p).with_context(|| format!("reading {p}"))).collect::<Result<_>>()?;
    let run_dir = PathBuf::from(args.need("--run-dir")?);
    let out = args.need("--out")?;
    let permits: usize = args.num("--permits", 1)?;

    let defaults = ShardConfig::default();
    let sharding = ShardConfig {
        element_threshold: args.num("--element-threshold", defaults.element_threshold)?,
        height_threshold: args.num("--height-threshold", defaults.height_threshold)?,
        shard_size: args.num("--shard-size", defaults.shard_size)?,
        minimal_trace_chunk_threshold: args.num("--trace-chunk-threshold", defaults.minimal_trace_chunk_threshold)?,
        trace_chunk_slots: args.num("--trace-chunk-slots", defaults.trace_chunk_slots)?,
        ..defaults
    };
    let expected = args.one("--expect-public-sha256");
    let request = ProveRequest {
        elf: &elf,
        inputs: &inputs,
        run_dir: &run_dir,
        proof_path: Path::new(&out),
        sharding,
        permits,
        expected_public_sha256: expected.as_deref(),
    };
    let result = crate::prove::prove(request, backend).await?;
    println!("{result}");
    Ok(())
}

/// Executes the guest without proving and prints its instruction count, syscall counts and
/// cycle-tracker spans.
async fn execute(args: &Args) -> Result<()> {
    sp1_sdk::utils::setup_logger();
    let elf = std::fs::read(args.need("--elf")?).context("reading --elf")?;
    let mut stdin = SP1Stdin::new();
    for p in args.all("--input") {
        stdin.write_vec(std::fs::read(&p).with_context(|| format!("reading {p}"))?);
    }
    let client = sp1_sdk::ProverClient::builder().light().build().await;
    let t = Instant::now();
    let (pv, report) = sp1_sdk::Prover::execute(&client, sp1_sdk::Elf::from(elf.clone()), stdin).await?;
    let secs = t.elapsed().as_secs_f64();
    let committed = sha_hex(pv.as_slice());
    let tracker: std::collections::BTreeMap<_, _> = report.cycle_tracker.iter().map(|(k, v)| (k.clone(), *v)).collect();
    let syscalls: std::collections::BTreeMap<String, u64> = report
        .syscall_counts
        .iter()
        .filter(|(_, n)| **n > 0)
        .map(|(c, n)| (format!("{c:?}"), *n))
        .collect();
    let v = serde_json::json!({
        "elf_sha256": sha_hex(&elf), "exit_code": report.exit_code,
        "instructions": report.total_instruction_count(), "syscalls": syscalls,
        "cycle_tracker": tracker, "touched_memory_addresses": report.touched_memory_addresses,
        "committed_values_sha256": committed, "public_values_bytes": pv.as_slice().len(),
        "execute_seconds": secs,
    });
    println!("{v}");
    if let Some(expect) = args.one("--expect-public-sha256") {
        ensure!(report.exit_code == 0 && committed == expect, "exit code {} / public values {committed}", report.exit_code);
    }
    Ok(())
}

fn status(run_dir: &Path) -> Result<()> {
    let cfg: RunConfig = serde_json::from_slice(&std::fs::read(run_dir.join("run.json")).context("no run.json")?)?;
    let (mut n, mut ms, mut last) = ([0u64; 4], [0u64; 2], 0u64);
    if let Ok(log) = std::fs::read_to_string(run_dir.join("progress.jsonl")) {
        for line in log.lines() {
            let Ok(v) = serde_json::from_str::<serde_json::Value>(line) else { continue };
            let shard = v["kind"] == "shard";
            let replayed = v["replayed"].as_bool().unwrap_or(false);
            n[(!shard as usize) * 2 + replayed as usize] += 1;
            if !replayed {
                ms[!shard as usize] += v["ms"].as_u64().unwrap_or(0);
            }
            last = last.max(v["t"].as_u64().unwrap_or(0));
        }
    }
    let mean = |m: u64, k: u64| if k > 0 { m as f64 / k as f64 / 1000.0 } else { 0.0 };
    let v = serde_json::json!({
        "run": cfg,
        "recorded": { "shard": Memo::count(run_dir, Kind::Shard), "recursion": Memo::count(run_dir, Kind::Reduce) },
        "log": {
            "shard_proved": n[0], "shard_replayed": n[1], "recursion_proved": n[2], "recursion_replayed": n[3],
            "mean_shard_seconds": mean(ms[0], n[0]), "mean_recursion_seconds": mean(ms[1], n[2]),
            "last_event_unix": last,
        },
        "result": std::fs::read(run_dir.join("result.json")).ok().and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok()),
    });
    println!("{}", serde_json::to_string_pretty(&v)?);
    Ok(())
}

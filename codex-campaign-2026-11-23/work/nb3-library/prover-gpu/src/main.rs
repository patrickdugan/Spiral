//! nb3-prove-gpu: `nb3-prove` (resumable, disk-backed SP1 6.9 proving) over SP1's CUDA shard
//! provers. Same command line as `nb3-prove`, plus:
//!
//!   --trace-buffers N   pinned host trace buffers per core and recursion prover (default 2)
//!
//! NB3_GPU_MEMORY_SAVER=1 discards retained LDEs (including recursion setup
//! keys) and recomputes GKR's first layer. It trades compute for device memory;
//! it does not alter shard boundaries and is not itself a VRAM limit.
//! NB3_GPU_RECOMPUTE_GKR and NB3_GPU_DROP_LDES independently override that
//! policy (0 or 1). Caching GKR while dropping LDEs spends more VRAM to avoid
//! first-layer recomputation without retaining all setup-key LDEs.
//! NB3_GPU_COMPOSE_ARITY=2 retains only the one- and two-input compose keys,
//! preserving SP1's default four-input circuit shape and full allowed-key map.
//! It trades additional recursion tasks for less resident setup data.
//!
//! SP1's own GPU setup (`sp1_gpu_prover::cuda_worker_builder`, via `local_gpu_opts`) refuses GPUs
//! with less than 24 GB and sizes the core trace buffer for its largest shard (about 4 × 10^8
//! field elements). Device memory comes from CUDA's stream-ordered pool and follows the shard
//! actually proved, so this builder takes the core trace size from the run's
//! `--element-threshold` instead; smaller shards fit smaller GPUs, or a GPU shared with another
//! job. The recursion, shrink and wrap provers keep SP1's allocations, which the fixed recursion
//! programs need.
use anyhow::Result;
use nb3_prover_gpu::{run_in_place, CudaBackend, CudaOptions};

fn boolean_setting(
    name: &str,
    value: Result<String, std::env::VarError>,
    default: bool,
) -> Result<bool> {
    match value {
        Err(std::env::VarError::NotPresent) => Ok(default),
        Ok(value) if value == "0" => Ok(false),
        Ok(value) if value == "1" => Ok(true),
        _ => anyhow::bail!("{name} must be unset, 0 or 1"),
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let memory_saver = boolean_setting(
        "NB3_GPU_MEMORY_SAVER",
        std::env::var("NB3_GPU_MEMORY_SAVER"),
        false,
    )?;
    let recompute_gkr = boolean_setting(
        "NB3_GPU_RECOMPUTE_GKR",
        std::env::var("NB3_GPU_RECOMPUTE_GKR"),
        memory_saver,
    )?;
    let drop_ldes = boolean_setting(
        "NB3_GPU_DROP_LDES",
        std::env::var("NB3_GPU_DROP_LDES"),
        memory_saver,
    )?;
    let compose_arity = match std::env::var("NB3_GPU_COMPOSE_ARITY") {
        Err(std::env::VarError::NotPresent) => None,
        Ok(value) if value == "2" => Some(2),
        _ => anyhow::bail!("NB3_GPU_COMPOSE_ARITY must be unset or 2"),
    };
    let args: Vec<String> = std::env::args().collect();
    let trace_buffers = args
        .iter()
        .position(|a| a == "--trace-buffers")
        .and_then(|i| args.get(i + 1))
        .map(|s| s.parse::<usize>())
        .transpose()?
        .unwrap_or_else(|| CudaOptions::default().trace_buffers);
    let options = CudaOptions {
        trace_buffers,
        recompute_gkr,
        drop_ldes,
        two_input_compose: compose_arity.is_some(),
    };
    options.validate_compose_shape()?;
    let handle = run_in_place(|scope| async move {
        nb3_prover::cli::main_with(CudaBackend::new(scope, options)).await
    })
    .await;
    handle
        .await
        .map_err(|e| anyhow::anyhow!("CUDA task: {e:?}"))?
}

#[cfg(test)]
mod retention_settings {
    use super::*;

    #[test]
    fn unset_overrides_preserve_legacy_policy() {
        for legacy in [false, true] {
            assert_eq!(
                boolean_setting("GKR", Err(std::env::VarError::NotPresent), legacy).unwrap(),
                legacy
            );
            assert_eq!(
                boolean_setting("LDE", Err(std::env::VarError::NotPresent), legacy).unwrap(),
                legacy
            );
        }
    }

    #[test]
    fn mixed_policy_can_cache_gkr_while_discarding_ldes() {
        assert!(!boolean_setting("GKR", Ok("0".into()), true).unwrap());
        assert!(boolean_setting("LDE", Ok("1".into()), false).unwrap());
    }

    #[test]
    fn malformed_overrides_are_refused_before_cuda() {
        for value in ["", "true", "false", "2", "-1", " 0"] {
            assert!(boolean_setting("GKR", Ok(value.into()), true).is_err());
        }
    }
}

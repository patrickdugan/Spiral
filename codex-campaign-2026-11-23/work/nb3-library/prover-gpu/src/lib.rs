//! The CUDA backend for the resumable SP1 prover.
use std::sync::Arc;

use anyhow::{ensure, Context, Result};
use nb3_prover::backend::Backend;
use sp1_core_executor::SP1CoreOpts;
use sp1_core_machine::riscv::RiscvAir;
use sp1_gpu_cudart::cuda_memory_info;
pub use sp1_gpu_cudart::{run_in_place, TaskScope};
use sp1_gpu_prover::{
    new_cuda_prover, SP1CudaProverComponents, RECURSION_TRACE_ALLOCATION, SHRINK_TRACE_ALLOCATION,
    WRAP_TRACE_ALLOCATION,
};
use sp1_hypercube::{prover::ProverSemaphore, Machine};
use sp1_primitives::SP1Field;
use sp1_prover::{
    worker::SP1WorkerBuilder, ReadyWrapProverBuilder, SP1ProverComponents, CORE_LOG_STACKING_HEIGHT,
};

/// Runtime settings for the CUDA worker, independent of the persisted sharding profile.
#[derive(Clone, Copy, Debug)]
pub struct CudaOptions {
    /// Pinned host trace buffers per core and recursion prover, from 1 to 4.
    pub trace_buffers: usize,
    /// Recompute the first GKR layer instead of keeping its intermediate data.
    pub recompute_gkr: bool,
    /// Discard retained low-degree extensions.
    pub drop_ldes: bool,
    /// Schedule at most two compose inputs using the original four-input circuit shape.
    pub two_input_compose: bool,
}

impl Default for CudaOptions {
    fn default() -> Self {
        Self {
            trace_buffers: 2,
            recompute_gkr: false,
            drop_ldes: false,
            two_input_compose: false,
        }
    }
}

impl CudaOptions {
    /// Check the worker's process environment against the selected compose policy.
    pub fn validate_compose_shape(&self) -> Result<()> {
        ensure!(
            !self.two_input_compose
                || std::env::var("SP1_WORKER_MAX_COMPOSE_ARITY").map_or(true, |value| value == "4"),
            "reduced compose setup requires the original four-input circuit shape"
        );
        Ok(())
    }
}

/// CUDA backend sized from the run's pinned shard boundaries.
pub struct CudaBackend {
    scope: TaskScope,
    options: CudaOptions,
}

impl CudaBackend {
    /// Pass the task scope from run_in_place and keep it alive for the duration of the proof.
    pub fn new(scope: TaskScope, options: CudaOptions) -> Self {
        Self { scope, options }
    }
}

impl Backend for CudaBackend {
    type C = SP1CudaProverComponents;

    fn name(&self) -> &'static str {
        "cuda"
    }

    fn adjust_opts(&self, opts: &mut SP1CoreOpts) {
        // As SP1's GPU options, except the shard size, which the run configuration decides.
        opts.global_dependencies_opt = true;
        opts.recompute_gkr_trace = self.options.recompute_gkr;
        opts.drop_ldes = self.options.drop_ldes;
    }

    async fn worker_builder(
        &self,
        machine: Machine<SP1Field, RiscvAir<SP1Field>>,
        opts: &SP1CoreOpts,
        permits: usize,
    ) -> Result<SP1WorkerBuilder<SP1CudaProverComponents>> {
        self.options.validate_compose_shape()?;
        let compose_arity = self.options.two_input_compose.then_some(2);
        if let Some(arity) = compose_arity {
            // The embedded map remains complete. Refuse a configuration for which
            // reducing the set of constructed keys would change its commitment.
            let original = sp1_prover::recursion::RecursionVks::new(None, 4, true).root();
            let reduced = sp1_prover::recursion::RecursionVks::new(None, arity, true).root();
            ensure!(
                original == reduced,
                "smaller compose setup changes the allowed-key root"
            );
        }
        let (free, total) = cuda_memory_info()?;
        tracing::info!("GPU memory: {} MiB free of {} MiB", free >> 20, total >> 20);
        let (free, total) = (free as u64, total as u64);
        ensure!(permits > 0, "--permits must be positive");
        ensure!(
            (1..=4).contains(&self.options.trace_buffers),
            "--trace-buffers must be between 1 and 4"
        );
        let base = usize::try_from(opts.sharding_threshold.element_threshold)
            .context("element threshold exceeds usize")?;
        ensure!(base > 0, "--element-threshold must be positive");
        let stack = 1usize
            .checked_shl(CORE_LOG_STACKING_HEIGHT as u32)
            .context("stacking height overflow")?;
        let core_elements = base
            .checked_add(stack)
            .context("core trace allocation overflow")?;
        // Lower bound only: FRI, recursion, CUDA graphs and other buffers also consume VRAM.
        let min_trace_bytes = (core_elements as u64)
            .checked_mul(std::mem::size_of::<SP1Field>() as u64)
            .context("core trace byte count overflow")?;
        let reserve = (total / 4).min(512 * 1024 * 1024);
        ensure!(free > reserve && min_trace_bytes <= free - reserve,
            "core trace alone needs {} MiB with {} MiB free; reduce --element-threshold or free GPU memory",
            min_trace_bytes >> 20, free >> 20);
        tracing::info!(
            "core trace {} MiB minimum, GPU reserve {} MiB; this does not bound peak usage",
            min_trace_bytes >> 20,
            reserve >> 20
        );
        tracing::info!(
            recompute_gkr = self.options.recompute_gkr,
            drop_ldes = self.options.drop_ldes,
            "CUDA LDE retention and GKR recomputation policy"
        );
        let permits = ProverSemaphore::new(permits);
        let s = &self.scope;
        let core_verifier = SP1CudaProverComponents::core_verifier(machine.clone());
        let core = new_cuda_prover(
            &core_verifier,
            core_elements,
            self.options.trace_buffers,
            opts.recompute_gkr_trace,
            opts.drop_ldes,
            s.clone(),
        )
        .await;
        let compress_verifier = SP1CudaProverComponents::compress_verifier();
        let compress = new_cuda_prover(
            &compress_verifier,
            RECURSION_TRACE_ALLOCATION,
            self.options.trace_buffers,
            self.options.recompute_gkr,
            self.options.drop_ldes,
            s.clone(),
        )
        .await;
        let shrink_verifier = SP1CudaProverComponents::shrink_verifier();
        let shrink = new_cuda_prover(
            &shrink_verifier,
            SHRINK_TRACE_ALLOCATION,
            1,
            self.options.recompute_gkr,
            self.options.drop_ldes,
            s.clone(),
        )
        .await;
        let wrap_verifier = SP1CudaProverComponents::wrap_verifier();
        let wrap = new_cuda_prover(
            &wrap_verifier,
            WRAP_TRACE_ALLOCATION,
            1,
            self.options.recompute_gkr,
            self.options.drop_ldes,
            s.clone(),
        )
        .await;
        let builder = SP1WorkerBuilder::<SP1CudaProverComponents>::new_with_machine(machine)
            .with_core_opts(opts.clone())
            .with_core_air_prover(Arc::new(core), permits.clone())
            .with_compress_air_prover(Arc::new(compress), permits.clone())
            .with_shrink_air_prover(Arc::new(shrink), permits.clone())
            .with_wrap_air_prover(ReadyWrapProverBuilder::new(Arc::new(wrap)), permits);
        Ok(if let Some(arity) = compose_arity {
            builder.with_config(|config| {
                // Keep reduce_shape from the default four-input configuration:
                // only scheduling and the eagerly constructed key subset change.
                config.controller_config.max_reduce_arity = arity;
                config
                    .prover_config
                    .recursion_prover_config
                    .max_compose_arity = arity;
                tracing::info!(
                    compose_arity = arity,
                    "reduced compose setup; original circuit shape and allowed-key root retained"
                );
            })
        } else {
            builder
        })
    }
}

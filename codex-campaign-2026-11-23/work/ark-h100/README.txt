Ark H100 SXM pilot
=================

Use a single on-demand Secure Cloud H100 SXM 80 GB Pod. Enable full SSH with TCP
port 22. Use x86-64 Ubuntu 24.04, NVIDIA CUDA 12.8.1 development tools
(nvcc V12.8.93), and a 120 GB /workspace network volume in a datacenter that
offers both the storage and the H100. Use the same image for any CPU staging
Pod and the H100. Runpod documents
runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404 as a CUDA 12.8.1 image option.
The published H100 SXM configuration has 125 GB RAM and 20 vCPUs. Verify
posted availability, nvcc and price in the selected template.

To preserve the paid GPU hour, stage the archive and build on compatible
CPU compute with the same volume before attaching the H100. A fresh build
can spend part of the hour compiling. The CPU build has not been timed.
The expected toolchain is Rust 1.99.1. Install the usual compiler tools for
the build image (build-essential, clang, cmake, pkg-config, libssl-dev,
protobuf-compiler, Python 3 and Git) and Go if the build enables gnark.

Upload through the Pod's full SSH/SCP endpoint or stage via the approved
storage interface. Keep the checkpoint and regtest proof inputs private.
Copy these four files into /workspace/ark-h100-upload

  hopper-build.tar.gz
  hopper-build.sha256
  checkpoint.tar
  checkpoint.sha256

On the staging machine

  cd /workspace/ark-h100-upload
  sha256sum -c hopper-build.sha256 checkpoint.sha256
  mkdir /workspace/ark-h100-kit /workspace/ark-h100-trial-01
  tar -xzf hopper-build.tar.gz -C /workspace/ark-h100-kit
  umask 077
  tar -xf checkpoint.tar -C /workspace/ark-h100-trial-01
  cd /workspace/ark-h100-kit
  bash build-hopper.sh

Inspect hopper-binary.sha256 and hopper-fatbins.txt. The Hopper binary has its
own hash. The laptop binary targets a different CUDA architecture.

Attach the same volume to the H100 and use the same CUDA runtime image.
Set a one-hour Pod auto-stop when available, with no auto-termination.
Once the copy and build are ready

  bash /workspace/ark-h100-kit/run-pilot.sh /workspace/ark-h100-trial-01

The pilot shuts down its own prover after 55 minutes, leaving five minutes
for Pod and result handling. pilot-result.json reports new core and recursion
proofs per minute after a ten-minute warm-up. Check prover.log for successful
checkpoint replay and any CUDA or resource failure. The laptop baseline is
4.8 new cores per minute. Extend only if the pilot sustains about 10/min and
new recursion work continues. A pilot stop is expected and distinct from an
independently verified proof. If compressed.bin exists, keep it and verify it
with the pinned local SDK, M13 and M14 chain.

Pins and scope

  SP1 6.9.0, upstream revision b8387fa61e1361d90ee7de49f551863418ca0f08
  Cached-GKR driver from the laptop campaign, with Cargo paths relocated
  CUDA architecture 90, same guest, Nova verifying key, proof and cache nonce
  Original core partition, recursion arity, retention settings and one permit
  Native cloud run with separate storage and without laptop-specific WSL shims
  Historical checkpoint copy verified against all 20,181 recorded entries

The checkpoint predates newer checkpoints on the laptop. Use replay evidence
to assess how far the cloud run has caught up. Keep the trial cache on the
volume until all needed reports or outputs have been retrieved.

Runpod references
  https://www.runpod.io/pricing
  https://docs.runpod.io/pods/storage/types
  https://docs.runpod.io/pods/configuration/use-ssh

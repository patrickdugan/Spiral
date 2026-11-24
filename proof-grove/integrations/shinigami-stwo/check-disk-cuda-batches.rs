//! Exercise the same CUDA batch loader that the archived disk prover uses.

#[path = "disk-merkle-cuda.rs"]
mod disk_cuda;

use std::fs::File;
use std::io::{self, Write};

const LEAVES: usize = 1 << 15;
const BATCH: usize = 1 << 13;
const HASH_BYTES: usize = 32;
const PRIME: u32 = 0x7fff_ffff;

fn column_value(column: usize, row: usize) -> u32 {
    match row % 256 {
        0 => PRIME,
        1 => 0,
        _ => (column as u32 + 1) * 100_000 + row as u32 * 17,
    }
}

fn main() -> io::Result<()> {
    let Some(path) = std::env::args_os().nth(1) else {
        return Err(io::Error::other("usage: check-disk-cuda-batches NEW_LAYERS.bin"));
    };
    let mut cuda = disk_cuda::CudaDiskMerkle::from_environment()?
        .ok_or_else(|| io::Error::other("STWO_CUDA_DISK_MERKLE_LIBRARY is required"))?;
    let widths: [usize; 4] = [2, 8, 8192, LEAVES];
    let shifts = widths.map(|width| LEAVES.ilog2() - width.ilog2());
    let batch_size = disk_cuda::CudaDiskMerkle::leaf_batch_size(BATCH, &shifts)?;
    assert_eq!(batch_size, BATCH);
    assert_eq!(disk_cuda::CudaDiskMerkle::leaf_batch_size(BATCH, &[0; 4096])?, 4096);
    assert!(disk_cuda::CudaDiskMerkle::leaf_batch_size(BATCH, &[0; 16385]).is_err());
    let mut layer = vec![0; LEAVES * HASH_BYTES];
    let mut output = File::create_new(path)?;
    let mut launches = 0;
    for (batch, hashes) in layer.chunks_exact_mut(batch_size * HASH_BYTES).enumerate() {
        cuda.hash_leaves(batch * batch_size, &shifts, hashes, |column, row| {
            assert!(row < widths[column]);
            column_value(column, row)
        })?;
        launches += 1;
    }
    output.write_all(&layer)?;
    while layer.len() > HASH_BYTES {
        let mut next = vec![0; layer.len() / 2];
        for (batch, hashes) in next.chunks_mut(BATCH * HASH_BYTES).enumerate() {
            let first_byte = batch * BATCH * HASH_BYTES * 2;
            cuda.hash_parents(&layer[first_byte..first_byte + 2 * hashes.len()], hashes)?;
            launches += 1;
        }
        output.write_all(&next)?;
        layer = next;
    }
    println!("hashed {} nodes using {launches} CUDA launches", 2 * LEAVES - 1);
    Ok(())
}

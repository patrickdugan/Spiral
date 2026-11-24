//! Diagnose a saved CUDA proof using the matching Cairo build's CPU verifier.

use std::{error::Error, path::PathBuf};

use cairo_air::{
    utils::{deserialize_proof_from_file, ProofFormat},
    verifier::verify_cairo,
};
use stwo::core::vcs_lifted::blake2_merkle::{Blake2sMerkleChannel, Blake2sMerkleHasher};

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    let [path] = args.as_slice() else {
        return Err("usage: verify-cuda-candidate PROOF.json".into());
    };
    let proof = deserialize_proof_from_file::<Blake2sMerkleHasher>(path, ProofFormat::Json)?;
    verify_cairo::<Blake2sMerkleChannel>(proof)?;
    println!("Matching Cairo CPU verifier accepted the CUDA proof candidate");
    Ok(())
}

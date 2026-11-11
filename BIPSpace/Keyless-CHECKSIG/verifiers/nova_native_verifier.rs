//! Native compressed Nova SNARK gate for the existing NHC1/NHT4 header fold.
//!
//! Copy this file into zk-rusto-no-bitcoino/integrations/bitvm3-nova/m12/native/
//! src/bin/keyless_nova_verify.rs and run it as described in README.md.
//! It calls the already tested Nova 0.76 Pallas/Vesta Spartan+IPA verifier.
//! It runs NATIVELY, not in Bitcoin Script. No script-value authorization
//! follows from its output unless the proved statement includes that relation.

use nova_bitvm3_m12::{bundle::Bundle, nova_io};
use std::{env, fs, process::ExitCode};

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {
        return Err(
            "usage: keyless_nova_verify NHC1_OR_NHT4_BUNDLE COMPRESSED_VERIFIER_KEY_OR_--rebuild-testnet4-k1 EXPECTED_PUBLIC_STATEMENT_SHA256"
                .to_owned(),
        );
    }
    let bundle = fs::read(&args[1]).map_err(|e| format!("read bundle: {e}"))?;
    let vk = if args[2] == "--rebuild-testnet4-k1" {
        let desc = Bundle::parse(&bundle).map_err(|e| format!("bundle: {e}"))?;
        if desc.net.name() != "testnet4" || desc.k != 1 {
            return Err("key rebuild permitted only for pinned testnet4 k=1 fixture".into());
        }
        nova_io::vk_export(desc.net, 1)
    } else {
        fs::read(&args[2]).map_err(|e| format!("read verifier key: {e}"))?
    };
    if args[3].len() != 64 || !args[3].bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("expected statement digest must be 64 hexadecimal characters".to_owned());
    }
    // verify_statement checks key pins for (network,k), deserializes Nova
    // CompressedSNARK, verifies its proof and reconstructs the 1,164-byte
    // public statement from the verified terminal state.
    let verified = nova_io::verify_statement(&bundle, &vk)
        .map_err(|e| format!("Nova verification rejected: {e}"))?;
    if verified.statement.public_statement_sha256 != args[3].to_ascii_lowercase() {
        return Err("verified Nova proof has a different public statement".to_owned());
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&verified.statement)
            .map_err(|e| format!("encode JSON: {e}"))?
    );
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(msg) => {
            eprintln!("REJECTED: {msg}");
            ExitCode::FAILURE
        }
    }
}

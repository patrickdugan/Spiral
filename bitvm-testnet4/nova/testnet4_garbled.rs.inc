

#[test]
fn testnet4_nova_demo_accepts_and_rejects() {
    let shape = native::load(native::FIXTURE_V2);
    let proof = native::load(A_PROOF);
    let expected: m13_verify::FinalStatement = serde_json::from_slice(&std::fs::read(A_STATEMENT).unwrap()).unwrap();
    m13_verify::verify_final(&proof, &expected).expect("native final verifier must accept the real Nova guest proof");
    let original = native::bits(&full::items(&proof));
    assert_eq!(original.len(), 8_635_080);
    let mut tampered = original.clone();
    let at = tampered.len() - 40;
    tampered[at] = !tampered[at];
    let mut other = expected.clone();
    other.committed_values_sha256 = m13_verify::sha_hex(b"wrong Testnet4 demo statement");
    assert!(m13_verify::verify_final(&proof, &other).is_err());
    for (name, statement, bits, wanted) in [
        ("real-nova-proof", expected.clone(), original.clone(), true),
        ("tampered-proof-input", expected, tampered, false),
        ("wrong-statement", other, original, false),
    ] {
        let started = std::time::Instant::now();
        let (accepted, rejected, gates) = demo_disk_garble_and_evaluate(&shape, &statement, bits);
        assert_eq!(gates, 785_442_492);
        assert_eq!(accepted, wanted, "{name}");
        assert_eq!(rejected, !wanted, "{name}");
        eprintln!("BITVM3_DEMO {}", serde_json::json!({"case":name,"accepted":accepted,"rejected":rejected,"ciphertexts":gates,"input_bits":8_635_080,"seconds":started.elapsed().as_secs_f64()}));
    }
}

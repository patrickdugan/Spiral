
// The same streaming half-gate circuit with one large working set resident at a time.
// Temporary ciphertexts are bounded to exactly one M14 evaluation and removed on drop.
struct DemoDiskFile(std::path::PathBuf);
impl DemoDiskFile {
    fn create() -> (Self, std::fs::File) {
        let directory = std::path::PathBuf::from(std::env::var_os("BITVM_DEMO_CIPHERTEXT_DIR").expect("set dedicated ciphertext directory"));
        std::fs::create_dir_all(&directory).unwrap();
        let nonce = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let path = directory.join(format!("m14-{}-{nonce}.ciphertexts", std::process::id()));
        let file = std::fs::OpenOptions::new().write(true).create_new(true).open(&path).unwrap();
        (Self(path), file)
    }
}
impl Drop for DemoDiskFile {
    fn drop(&mut self) { std::fs::remove_file(&self.0).expect("remove only owned ciphertext file"); }
}
const DEMO_CIPHERTEXTS: u64 = 785_442_492;
struct DemoDiskSink { writer: std::io::BufWriter<std::fs::File>, count: u64 }
impl CiphertextHandler for DemoDiskSink {
    type Result = u64;
    fn handle(&mut self, value: garbled_snark_verifier::S) {
        use std::io::Write;
        assert!(self.count < DEMO_CIPHERTEXTS, "ciphertext scratch bound exceeded");
        self.writer.write_all(&value.to_u128().to_be_bytes()).unwrap();
        self.count += 1;
    }
    fn finalize(mut self) -> u64 {
        use std::io::Write;
        self.writer.flush().unwrap();
        self.count
    }
}
struct DemoDiskSource { reader: std::io::BufReader<std::fs::File>, count: u64, records: u64 }
impl DemoDiskSource {
    fn open(path: &std::path::Path) -> Self {
        let file = std::fs::File::open(path).unwrap();
        let bytes = file.metadata().unwrap().len();
        assert_eq!(bytes % 16, 0, "truncated ciphertext record");
        assert!(bytes / 16 <= DEMO_CIPHERTEXTS);
        Self { reader: std::io::BufReader::with_capacity(1 << 20, file), count: 0, records: bytes / 16 }
    }
}
impl CiphertextSource for DemoDiskSource {
    type Result = u64;
    fn recv(&mut self) -> Option<garbled_snark_verifier::S> {
        use std::io::Read;
        if self.count == self.records { return None; }
        let mut bytes = [0u8; 16];
        self.reader.read_exact(&mut bytes).expect("complete ciphertext record");
        self.count += 1;
        Some(garbled_snark_verifier::S::from_u128(u128::from_be_bytes(bytes)))
    }
    fn finalize(mut self) -> u64 {
        use std::io::Read;
        assert_eq!(self.count, self.records, "unconsumed ciphertexts");
        assert_eq!(self.reader.read(&mut [0u8; 1]).unwrap(), 0);
        self.count
    }
}

fn demo_disk_garble_and_evaluate(proof: &native::Proof, expect: &m13_verify::FinalStatement, bits: Vec<bool>) -> (bool, bool, u64) {
    let n = bits.len();
    let (scratch, file) = DemoDiskFile::create();
    let known = &Known::new(proof, expect);
    let mut garbled: StreamingResult<GarbleMode<AesCcrGateHasher, DemoDiskSink>, _, Vec<GarbledWire>> =
        CircuitBuilder::streaming_garbling(GIn(n), CAP, SEED,
            DemoDiskSink { writer: std::io::BufWriter::with_capacity(1 << 20, file), count: 0 },
            |c, w| vec![full::final_verifier(c, known, w)]);
    let output = garbled.output_value[0].clone();
    let labels = std::mem::take(&mut garbled.input_wire_values);
    let (t_label, f_label) = (garbled.true_wire_constant.select(true).to_u128(), garbled.false_wire_constant.select(false).to_u128());
    let gates = garbled.gate_count.nonfree_gate_count();
    assert_eq!(gates, DEMO_CIPHERTEXTS);
    assert_eq!(garbled.ciphertext_handler_result, gates);
    assert_eq!(std::fs::metadata(&scratch.0).unwrap().len(), gates * 16);
    drop(garbled);
    eprintln!("BITVM3_PHASE garbling_complete ciphertexts={gates} bytes={}", gates * 16);
    let mut rng = ChaChaRng::seed_from_u64(SEED);
    let evaluated: StreamingResult<EvaluateMode<AesCcrGateHasher, DemoDiskSource>, _, Vec<EvaluatedWire>> =
        CircuitBuilder::streaming_evaluation(EIn { labels, bits }, CAP, t_label, f_label,
            AesCcrGateHasher::from_rng(&mut rng), DemoDiskSource::open(&scratch.0),
            |c, w| vec![full::final_verifier(c, known, w)]);
    assert_eq!(evaluated.gate_count.nonfree_gate_count(), gates);
    assert_eq!(evaluated.ciphertext_handler_result, gates);
    let label = evaluated.output_value[0].active_label;
    (label == output.select(true), label == output.select(false), gates)
}

#[test]
fn testnet4_disk_transport_roundtrip_and_truncation() {
    let (scratch, file) = DemoDiskFile::create();
    let mut sink = DemoDiskSink { writer: std::io::BufWriter::new(file), count: 0 };
    sink.handle(garbled_snark_verifier::S::from_u128(1));
    sink.handle(garbled_snark_verifier::S::from_u128(u128::MAX));
    assert_eq!(sink.finalize(), 2);
    let mut source = DemoDiskSource::open(&scratch.0);
    assert_eq!(source.recv().unwrap().to_u128(), 1);
    assert_eq!(source.recv().unwrap().to_u128(), u128::MAX);
    assert!(source.recv().is_none());
    assert_eq!(source.finalize(), 2);
    std::fs::OpenOptions::new().write(true).open(&scratch.0).unwrap().set_len(31).unwrap();
    assert!(std::panic::catch_unwind(|| DemoDiskSource::open(&scratch.0)).is_err());
}

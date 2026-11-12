#!/usr/bin/env python3
"""Instrument locked DSL 0.2.0 without changing constraints or evaluation.
Export verifier bytecode and witness separately from inline-push test code.
"""
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
metadata = json.loads(subprocess.check_output(['cargo','metadata','--locked','--format-version=1'],cwd=root,text=True))
packages = [p for p in metadata['packages'] if p['name']=='bitcoin-script-dsl']
if len(packages) != 1:
    raise SystemExit('Expected one locked bitcoin-script-dsl package')
package = packages[0]
if package['version'] != '0.2.0':
    raise SystemExit('Unexpected DSL version')
source = Path(package['manifest_path']).parent/'src/lib.rs'
text = source.read_text()
anchor = '    for elem in expected_final_stack.iter().rev() {'
if text.count(anchor) != 1:
    raise SystemExit('Expected one measurement anchor')
instrument = r'''
    // BIPSpace measurement only; original evaluation follows unchanged.
    if let Ok(directory) = std::env::var("KEYLESS_EXPORT_DIR") {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use crate::constraint_system::Element;
        static STAGE: AtomicUsize = AtomicUsize::new(0);
        let stage = STAGE.fetch_add(1, Ordering::SeqCst);
        let element_bytes = |element: &Element| -> Vec<u8> {
            match element {
                Element::Str(v) => v.clone(),
                Element::Num(value) => {
                    if *value == 0 { return Vec::new(); }
                    let negative = *value < 0;
                    let mut absolute = (*value as i64).unsigned_abs();
                    let mut bytes = Vec::new();
                    while absolute != 0 { bytes.push((absolute & 255) as u8); absolute >>= 8; }
                    if bytes.last().unwrap() & 128 != 0 { bytes.push(if negative {128} else {0}); }
                    else if negative { *bytes.last_mut().unwrap() |= 128; }
                    bytes
                }
            }
        };
        let hints: Vec<Vec<u8>> = program.hint.iter().map(element_bytes).collect();
        let inputs: Vec<Vec<u8>> = program.input.iter().map(element_bytes).collect();
        let hex = |data: &[u8]| data.iter().map(|b| format!("{:02x}",b)).collect::<String>();
        let json_hexes = |items: &[Vec<u8>]| items.iter().map(|v| format!("\"{}\"",hex(v))).collect::<Vec<_>>().join(",");
        let compact = |n: usize| if n < 253 {1usize} else if n <= 65535 {3} else {5};
        let hint_bytes: usize = hints.iter().map(|v| compact(v.len())+v.len()).sum();
        let input_bytes: usize = inputs.iter().map(|v| compact(v.len())+v.len()).sum();
        let items = hints.len()+inputs.len();
        let max_item = hints.iter().chain(inputs.iter()).map(|v| v.len()).max().unwrap_or(0);
        let record = format!("{{\"stage\":{},\"script_hex\":\"{}\",\"hint_hex\":[{}],\"input_hex\":[{}],\"expected_output_hex\":[{}],\"script_bytes\":{},\"hint_items\":{},\"input_items\":{},\"witness_items_without_script_control\":{},\"serialized_hint_bytes\":{},\"serialized_input_bytes\":{},\"max_witness_item_bytes\":{}}}\n",
            stage,hex(program.script.as_bytes()),json_hexes(&hints),json_hexes(&inputs),
            json_hexes(&expected_final_stack),program.script.len(),hints.len(),inputs.len(),
            items,hint_bytes,input_bytes,max_item);
        std::fs::create_dir_all(&directory)?;
        std::fs::write(std::path::Path::new(&directory).join(format!("stage-{:03}.json",stage)),record)?;
        println!("KEYLESS_STAGE {} script={} hints={} inputs={} serialized_witness={} max_item={}",
            stage,program.script.len(),hints.len(),inputs.len(),hint_bytes+input_bytes,max_item);
    }
'''
source.write_text(text.replace(anchor,instrument+anchor))
print(json.dumps({'instrumented_package':package['name'],'version':package['version'],
                  'source':package['source'],'measurement_only':True},indent=2))

#!/usr/bin/env python3
"""Instrument pinned bitcoin-script-dsl 0.2.0 test execution without changing
constraints, proof generation, or Script evaluation. Export program bytes and
witness items separately from the upstream inline-push test scripts.
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
    raise SystemExit(f'Unexpected DSL version: {package["version"]}')
source = Path(package['manifest_path']).parent/'src/lib.rs'
text = source.read_text()
anchor = '    for elem in expected_final_stack.iter().rev() {'
if text.count(anchor) != 1:
    raise SystemExit('Upstream DSL source changed: expected one measurement anchor')
instrument = r'''
    // BIPSpace measurement only. The original Script execution follows.
    if let Ok(directory) = std::env::var("KEYLESS_EXPORT_DIR") {
        use std::sync::atomic::{AtomicUsize, Ordering};
        static STAGE: AtomicUsize = AtomicUsize::new(0);
        let stage = STAGE.fetch_add(1, Ordering::SeqCst);
        let hex = |data: &[u8]| data.iter().map(|b| format!("{:02x}", b)).collect::<String>();
        let json_hexes = |items: &[Vec<u8>]| items.iter().map(|v| format!("\"{}\"", hex(v))).collect::<Vec<_>>().join(",");
        let compact = |n: usize| if n < 253 { 1usize } else if n <= 65535 { 3 } else { 5 };
        let hint_bytes: usize = program.hint.iter().map(|v| compact(v.len()) + v.len()).sum();
        let input_bytes: usize = program.input.iter().map(|v| compact(v.len()) + v.len()).sum();
        let items = program.hint.len() + program.input.len();
        let max_item = program.hint.iter().chain(program.input.iter()).map(|v| v.len()).max().unwrap_or(0);
        let record = format!("{{\"stage\":{},\"script_hex\":\"{}\",\"hint_hex\":[{}],\"input_hex\":[{}],\"expected_output_hex\":[{}],\"script_bytes\":{},\"hint_items\":{},\"input_items\":{},\"witness_items_without_script_control\":{},\"serialized_hint_bytes\":{},\"serialized_input_bytes\":{},\"max_witness_item_bytes\":{}}}\n",
            stage, hex(program.script.as_bytes()), json_hexes(&program.hint), json_hexes(&program.input),
            json_hexes(&expected_final_stack), program.script.len(), program.hint.len(), program.input.len(),
            items, hint_bytes, input_bytes, max_item);
        std::fs::create_dir_all(&directory)?;
        std::fs::write(std::path::Path::new(&directory).join(format!("stage-{:03}.json", stage)), record)?;
        println!("KEYLESS_STAGE {} script={} hints={} inputs={} serialized_witness={} max_item={}",
            stage, program.script.len(), program.hint.len(), program.input.len(), hint_bytes + input_bytes, max_item);
    }
'''
source.write_text(text.replace(anchor,instrument+anchor))
print(json.dumps({'instrumented_package':package['name'],'version':package['version'],
                  'source':package['source'],'measurement_only':True},indent=2))

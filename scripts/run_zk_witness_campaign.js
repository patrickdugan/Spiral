#!/usr/bin/env node

// Deliberately non-executable placeholder. The recovered task recorded local
// out-of-memory failures during ZK work. This script exits without allocating a
// proving system and points users to the hash-only witness receipts instead.

console.error("ZK witness generation is disabled in this bounded reconstruction.");
console.error("Use output/experiments/proof_cards.json and SHA-256 receipts instead.");
process.exitCode = 2;


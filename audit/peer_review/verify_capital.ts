import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { CapitalAccountingMachine, checkJournal } from "../../model/capital.ts";
import { fixtureConfig } from "../../model/capital.fixtures.ts";

// Run from the repository root. Optional compiler and declaration paths are
// intentionally external; the model has no runtime dependency installation.
const tests = readdirSync("model").filter(p => p.endsWith(".test.ts")).sort().map(p => `model/${p}`);
const testRun = spawnSync(process.execPath, ["--experimental-strip-types", "--test", "--test-reporter=tap", ...tests], { encoding: "utf8" });
const output = testRun.stdout + testRun.stderr;
writeFileSync("audit/peer_review/capital/tests.tap", output);
const sourceFiles = [...readdirSync("model").filter(p => p.startsWith("capital") && p.endsWith(".ts")).map(p => `model/${p}`),
  "model/server.ts", "model/server.retained.test.ts", "audit/peer_review/capital_comparison.ts", "audit/peer_review/capital_fixed_budget.ts",
  "audit/peer_review/capital_artifacts.ts", "audit/peer_review/verify_capital.ts", "audit/peer_review/regtest/normalize.ts", "audit/peer_review/regtest/normalize-failure.ts", "audit/peer_review/regtest/normalize-inbound.ts", "audit/peer_review/regtest/normalize-offboard.ts"];
const compiler = process.argv[2], typeRoots = process.argv[3];
let typecheck: { status: number | null; version?: string; diagnostics?: string } = { status: null };
if (compiler && typeRoots) {
  const result = spawnSync(process.execPath, [resolve(compiler), "--noEmit", "--strict", "--target", "es2022", "--module", "nodenext",
    "--allowImportingTsExtensions", "--skipLibCheck", "--typeRoots", resolve(typeRoots), ...sourceFiles], { encoding: "utf8" });
  typecheck = { status: result.status, version: execFileSync(process.execPath, [resolve(compiler), "--version"], { encoding: "utf8" }).trim(), diagnostics: result.stdout + result.stderr };
}
const journal = readFileSync("audit/peer_review/capital/lifecycle.jsonl", "utf8").trim().split(/\r?\n/).map(l => JSON.parse(l));
const check = checkJournal(fixtureConfig, journal), replay = CapitalAccountingMachine.replay(fixtureConfig, journal);
const unresolvedJournal = readFileSync("audit/peer_review/capital/deep-reorg-unresolved.jsonl", "utf8").trim().split(/\r?\n/).map(l => JSON.parse(l));
const unresolved = CapitalAccountingMachine.replay(fixtureConfig, unresolvedJournal).report();
const result = { node: process.version, test_command: "node --experimental-strip-types --test --test-reporter=tap model/*.test.ts",
  test_exit_code: testRun.status, tests: Number(output.match(/^# tests (\d+)$/m)?.[1]), passes: Number(output.match(/^# pass (\d+)$/m)?.[1]),
  failures: Number(output.match(/^# fail (\d+)$/m)?.[1]), typecheck, journal_check: check, replay_state_hash: replay.stateHash(),
  randomized: { seeds: 128, commands_per_seed: 32, shrinking: "deletion to 1-minimal command sequence on failure" },
  unresolved_reorg: { check: checkJournal(fixtureConfig, unresolvedJournal), reconciliation_required: unresolved.reconciliation_required },
  source_sha256: Object.fromEntries(sourceFiles.map(path => [path, createHash("sha256").update(readFileSync(path)).digest("hex")])) };
writeFileSync("audit/peer_review/capital/verification.json", JSON.stringify(result, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
if (testRun.status !== 0 || (compiler && typecheck.status !== 0) || !check.ok) process.exitCode = 1;

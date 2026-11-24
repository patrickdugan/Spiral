import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deserializeProofs, serializeProofs } from '@cashu/cashu-ts';
import { auditProtected, verifyProtectedReceipt } from './protected.mjs';

const [file, expectedBundle, expectedSha, expectedAmount] = process.argv.slice(2);
assert.match(expectedBundle ?? '', /^[a-f0-9]{64}$/);
assert.match(expectedSha ?? '', /^[a-f0-9]{64}$/);
assert.ok(statSync(file).size < 2 * 1024 * 1024);
const raw = readFileSync(file);
const sha256 = createHash('sha256').update(raw).digest('hex');
assert.equal(sha256, expectedSha);
const certificate = JSON.parse(raw);
assert.equal(certificate.schema, 'proof-grove/protected-cdk-issuance-fixture/v1');
assert.equal(new URL(certificate.mint_url).hostname, '127.0.0.1');
assert.equal(certificate.operation.protection.bundle_id, expectedBundle);
const verified = await auditProtected(certificate.operation, certificate.mint_url);
const altered = structuredClone(certificate.operation);
const proofs = deserializeProofs(altered.proofs);
const secret = JSON.parse(proofs[0].secret);
const nonce = secret[1].nonce;
assert.match(nonce, /^[a-f0-9]{64}$/);
secret[1].nonce = (nonce[0] === '0' ? '1' : '0') + nonce.slice(1);
proofs[0].secret = JSON.stringify(secret);
altered.proofs = serializeProofs(proofs);
await assert.rejects(() => auditProtected(altered, certificate.mint_url), /DLEQ/);
let portableAudit;
if (expectedAmount !== undefined) {
  const portablePath = join(dirname(file), 'protected-issuance-receipt.json');
  const portable = JSON.parse(readFileSync(portablePath, 'utf8'));
  const trusted = JSON.parse(readFileSync(join(dirname(file), 'protected-mint-pin.json'), 'utf8'));
  const pin = {mint: trusted.mint, bundleId: expectedBundle, keysetsSha256: trusted.keysets_sha256,
    amount: Number(expectedAmount)};
  const walletCli = fileURLToPath(new URL('cli.mjs', import.meta.url));
  const recorded = JSON.parse(execFileSync(process.execPath, [walletCli, 'protected-verify-receipt',
    '--receipt', portablePath, '--mint', pin.mint, '--bundle-id', pin.bundleId,
    '--keysets-sha256', pin.keysetsSha256, '--amount', expectedAmount], {encoding: 'utf8', timeout: 20_000}));
  assert.equal(recorded.proofs_sha256, verified.proofs_sha256);
  const keySubstitution = structuredClone(portable);
  const keys = keySubstitution.operation.protectedMintCache.keys.keysets.find(entry => entry.id === recorded.keyset_ids[0]).keys;
  const [first, second] = Object.keys(keys);
  keys[first] = keys[second];
  await assert.rejects(() => verifyProtectedReceipt(keySubstitution, pin), /keyset pin mismatch/);
  await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, amount: pin.amount + 1}), /pinned mint or reserve/);
  await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, bundleId: 'ab'.repeat(32)}), /pinned mint or reserve/);
  await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, mint: 'http://127.0.0.1:1'}), /pinned mint or reserve/);
  const repeated = structuredClone(portable);
  repeated.operation.proofs.push(repeated.operation.proofs[0]);
  await assert.rejects(() => verifyProtectedReceipt(repeated, pin), /Duplicate protected Cashu proof/);
  portableAudit = {keysets_sha256: recorded.keysets_sha256, proof_count: recorded.proof_count,
    receipt_sha256: createHash('sha256').update(readFileSync(portablePath)).digest('hex'),
    rejected: ['key-substitution', 'wrong-amount', 'wrong-bundle', 'wrong-mint', 'repeated-note']};
}
console.log(JSON.stringify({...verified, certificate_sha256:sha256, changed_secret_rejected:true, portable_audit:portableAudit}));

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { blindMessage, createDLEQProof, deserializeProofs, getPubKeyFromPrivKey, OutputData,
  pointFromHex, serializeProofs, verifyDLEQProof_reblind } from '@cashu/cashu-ts';
import { auditProtected, checkBatchOpening, verifyProtectedReceipt } from './protected.mjs';

function rejectValidAlternateBatch(lockKey) {
  const mintSecret = Buffer.from('07'.padStart(64, '0'), 'hex');
  const mintKey = Buffer.from(getPubKeyFromPrivKey(mintSecret)).toString('hex');
  const id = '0011223344556677';
  const committed = OutputData.createSingleP2PKData({pubkey: lockKey, blindKeys: false}, 1, id);
  const alternate = OutputData.createSingleP2PKData({pubkey: lockKey, blindKeys: false}, 1, id);
  const B_ = blindMessage(alternate.secret, alternate.blindingFactor).B_;
  const C_ = B_.multiply(7n).toHex(true);
  const dleq = createDLEQProof(B_, mintSecret);
  const encodedDleq = {e: Buffer.from(dleq.e).toString('hex'), s: Buffer.from(dleq.s).toString('hex')};
  const proof = alternate.toProof({amount: alternate.blindedMessage.amount, id, C_, dleq: encodedDleq},
    {id, keys: {'1': mintKey}});
  assert.ok(verifyDLEQProof_reblind(alternate.secret, {...dleq, r: alternate.blindingFactor},
    pointFromHex(proof.C), pointFromHex(mintKey)));
  const output = {amount: 1, id, B_: committed.blindedMessage.B_};
  assert.throws(() => checkBatchOpening([proof], [output]), /batch opening mismatch/);
}

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
await assert.rejects(() => auditProtected(altered, certificate.mint_url), /DLEQ|batch opening mismatch/);
let portableAudit;
if (expectedAmount !== undefined) {
  const portablePath = join(dirname(file), 'protected-issuance-receipt.json');
  const portable = JSON.parse(readFileSync(portablePath, 'utf8'));
  const trusted = JSON.parse(readFileSync(join(dirname(file), 'protected-mint-pin.json'), 'utf8'));
  const pin = {mint: trusted.mint, bundleId: expectedBundle, keysetsSha256: trusted.keysets_sha256,
    amount: Number(expectedAmount)};
  const batch = portable.operation.protection.batch;
  const bundlePath = join(dirname(file), 'protected-bundle.json');
  if (batch) pin.bundle = JSON.parse(readFileSync(bundlePath, 'utf8'));
  const walletCli = fileURLToPath(new URL('cli.mjs', import.meta.url));
  const recorded = JSON.parse(execFileSync(process.execPath, [walletCli, 'protected-verify-receipt',
    '--receipt', portablePath, '--mint', pin.mint, '--bundle-id', pin.bundleId,
    '--keysets-sha256', pin.keysetsSha256, '--amount', expectedAmount,
    ...(batch ? ['--bundle', bundlePath] : [])], {encoding: 'utf8', timeout: 20_000}));
  assert.equal(recorded.proofs_sha256, verified.proofs_sha256);
  assert.equal(recorded.batch_bound, Boolean(batch));
  const keySubstitution = structuredClone(portable);
  const keys = keySubstitution.operation.protectedMintCache.keys.keysets.find(entry => entry.id === recorded.keyset_ids[0]).keys;
  const [first, second] = Object.keys(keys);
  keys[first] = keys[second];
  await assert.rejects(() => verifyProtectedReceipt(keySubstitution, pin), /keyset pin mismatch/);
  const pinMismatch = /pinned mint or reserve|bundle does not match the observer pin/;
  await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, amount: pin.amount + 1}), pinMismatch);
  await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, bundleId: 'ab'.repeat(32)}), pinMismatch);
  await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, mint: 'http://127.0.0.1:1'}), /pinned mint or reserve/);
  const repeated = structuredClone(portable);
  repeated.operation.proofs.push(repeated.operation.proofs[0]);
  await assert.rejects(() => verifyProtectedReceipt(repeated, pin), /Duplicate protected Cashu proof/);
  const rejected = ['key-substitution', 'wrong-amount', 'wrong-bundle', 'wrong-mint', 'repeated-note'];
  if (batch) {
    const downgraded = structuredClone(portable);
    downgraded.schema = 'proof-grove/protected-issuance-receipt/v1';
    delete downgraded.operation.protection.batch;
    await assert.rejects(() => verifyProtectedReceipt(downgraded, pin), /pinned mint or reserve/);
    await assert.rejects(() => verifyProtectedReceipt(portable, {...pin, bundle:undefined}), /pinned mint or reserve/);
    const reordered = structuredClone(portable);
    reordered.operation.protection.batch.outputs.reverse();
    await assert.rejects(() => verifyProtectedReceipt(reordered, pin), /on-chain issuance batch/);
    const changedR = structuredClone(portable);
    const reopened = deserializeProofs(changedR.operation.proofs);
    reopened[0].dleq.r = '01'.padStart(64, '0');
    changedR.operation.proofs = serializeProofs(reopened);
    await assert.rejects(() => verifyProtectedReceipt(changedR, pin), /batch opening mismatch/);
    rejectValidAlternateBatch(portable.operation.protection.lock_key);
    rejected.push('profile-downgrade', 'missing-v3-bundle', 'reordered-blinded-outputs',
      'substituted-blinding-factor', 'valid-alternate-synthetic-batch');
  }
  portableAudit = {keysets_sha256: recorded.keysets_sha256, proof_count: recorded.proof_count,
    ...(batch ? {batch_bound: true} : {}),
    receipt_sha256: createHash('sha256').update(readFileSync(portablePath)).digest('hex'),
    rejected};
}
console.log(JSON.stringify({...verified, certificate_sha256:sha256, changed_secret_rejected:true, portable_audit:portableAudit}));

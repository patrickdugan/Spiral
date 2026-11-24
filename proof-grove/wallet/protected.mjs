import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { deserializeProofs, hashToCurve, Mint, sumProofs, Wallet } from '@cashu/cashu-ts';

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const appRoot = fileURLToPath(new URL('../', import.meta.url));

export function issueIntentDomain(intentId, protection) {
  return protection ? `${intentId}#protected:${protection.bundle_id}` : intentId;
}

function protectedLockKey(bundleId) {
  if (!/^[0-9a-f]{64}$/.test(bundleId ?? '')) throw new Error('Invalid protected bundle ID');
  return hashToCurve(Buffer.from('proof-grove/protected-cashu-nut11/v1:' + bundleId)).toHex(true);
}

export function observeProtection(operation, options) {
  const {bundlePath, bundleId, coreConfig, python = 'python3'} = options;
  if (!operation.intent || operation.intent.network !== 'regtest' ||
      !bundlePath || !coreConfig || !/^[0-9a-f]{64}$/.test(bundleId ?? '')) {
    throw new Error('Invalid protected reserve parameters');
  }
  if (statSync(bundlePath).size > 32768) throw new Error('Protected reserve bundle is too large');
  const rawBundle = readFileSync(bundlePath, 'utf8');
  const bundle = JSON.parse(rawBundle);
  let status;
  try {
    status = JSON.parse(execFileSync(python, ['-m', 'proofdesk', 'protected-status',
      '--config', coreConfig, '--bundle', bundlePath, '--bundle-id', bundleId],
      {cwd: appRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30_000}));
  } catch {
    throw new Error('Protected reserve could not be verified against Bitcoin Core');
  }
  // Use only the bytes which were checked. The server independently verifies
  // the same pinned bundle before it forwards the blind signature request.
  if (rawBundle !== readFileSync(bundlePath, 'utf8') || bundle.bundle_id !== bundleId || status.state !== 'unspent' ||
      bundle.plan?.reserve_sats !== operation.amount_sats ||
      bundle.plan?.claim_commitment !== digest('proof-grove/protected-issuance-intent/v1:' + operation.intent.id)) {
    throw new Error('Protected reserve does not match the issuance intent');
  }
  const lockKey = protectedLockKey(bundleId);
  return {bundle, bundle_id: bundleId, lock_key: lockKey};
}

export function requireProtectedSecrets(proofs, lockKey) {
  for (const proof of proofs) {
    const [kind, secret] = JSON.parse(proof.secret);
    const tags = secret?.tags ?? [];
    if (kind !== 'P2PK' || ![lockKey, lockKey.slice(2)].includes(secret?.data) || !Array.isArray(tags) ||
        tags.some(tag => !Array.isArray(tag) || tag.length !== 2 ||
          !((tag[0] === 'sigflag' && tag[1] === 'SIG_INPUTS') || (tag[0] === 'n_sigs' && tag[1] === '1')))) {
      throw new Error('Protected Cashu output lock mismatch');
    }
  }
}

export async function auditProtected(operation, mintUrl) {
  if (operation.state !== 'protected-issued' || !operation.protection || !operation.protectedMintCache) {
    throw new Error('No protected issuance receipt for this operation');
  }
  if (protectedLockKey(operation.protection.bundle_id) !== operation.protection.lock_key) {
    throw new Error('Protected issuance receipt lock mismatch');
  }
  const offline = () => { throw new Error('Protected issuance audit requires cached mint keys'); };
  const wallet = new Wallet(new Mint(mintUrl, {customRequest: offline}));
  wallet.loadMintFromCache(operation.protectedMintCache.info, operation.protectedMintCache.keys);
  const proofs = deserializeProofs(operation.proofs);
  requireProtectedSecrets(proofs, operation.protection.lock_key);
  const checked = await wallet.verifyMintSignatures(proofs, {require: true});
  if (checked.invalid.length || checked.valid.length !== proofs.length ||
      Number(sumProofs(proofs).toString()) !== operation.amount_sats) {
    throw new Error('Protected issuance DLEQ audit failed');
  }
  return {
    state: operation.state, evidence_level: operation.evidence_level,
    amount_sats: operation.amount_sats, proof_count: proofs.length,
    bundle_id: operation.protection.bundle_id, lock_key: operation.protection.lock_key,
    request_sha256: operation.request_sha256, proofs_sha256: digest(JSON.stringify(operation.proofs)),
    dleq_verified: true, offline_keyset_audit: true,
  };
}

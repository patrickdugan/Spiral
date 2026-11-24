import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deserializeProofs, hashToCurve, Mint, sumProofs, Wallet } from '@cashu/cashu-ts';
import { normalizeWalletUrl, singleAttemptRequest } from './transport.mjs';

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const appRoot = fileURLToPath(new URL('../', import.meta.url));
const fundedIssuancePlan = 'proof-grove/protected-reserve-plan/v2';
const receiptSchema = 'proof-grove/protected-issuance-receipt/v1';
const receiptFields = ['state', 'amount_sats', 'protection', 'protectedMintCache', 'proofs',
  'request_sha256', 'evidence_level'];
const SHA256 = /^[0-9a-f]{64}$/;
const KEYSET_ID = /^(?:[0-9a-f]{16}|[0-9a-f]{66})$/;

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
  if (bundle.plan.schema !== fundedIssuancePlan && operation.protection?.bundle_id !== bundleId) {
    throw new Error('New protected issuance requires an on-chain commitment to the reserve terms');
  }
  const lockKey = protectedLockKey(bundleId);
  return {bundle, bundle_id: bundleId, lock_key: lockKey};
}

export function exportCooperativePsbt({bundlePath, bundleId, coreConfig, output, python = 'python3'}, expectedTxid) {
  const args = ['-m', 'proofdesk', 'protected-psbt', '--route', 'cooperative',
    '--config', resolve(coreConfig), '--bundle', resolve(bundlePath), '--bundle-id', bundleId,
    '--output', resolve(output)];
  let local;
  try {
    local = JSON.parse(execFileSync(python, args, {
      cwd: appRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30_000,
    }));
  } catch {
    throw new Error('Could not export a locally verified cooperative PSBT');
  }
  if (local.txid !== expectedTxid) throw new Error('Desk and holder Core disagree on the cooperative transaction');
  return local;
}

export function requireProtectedSecrets(proofs, lockKey) {
  const secrets = new Set();
  for (const proof of proofs) {
    if (secrets.has(proof.secret)) throw new Error('Duplicate protected Cashu proof');
    secrets.add(proof.secret);
    let condition;
    try {
      condition = JSON.parse(proof.secret);
    } catch {
      throw new Error('Invalid protected Cashu output lock');
    }
    if (!Array.isArray(condition) || condition.length !== 2) throw new Error('Invalid protected Cashu output lock');
    const [kind, secret] = condition;
    const tags = secret?.tags ?? [];
    if (kind !== 'P2PK' || ![lockKey, lockKey.slice(2)].includes(secret?.data) || !Array.isArray(tags) ||
        tags.some(tag => !Array.isArray(tag) || tag.length !== 2 ||
          !((tag[0] === 'sigflag' && tag[1] === 'SIG_INPUTS') || (tag[0] === 'n_sigs' && tag[1] === '1')))) {
      throw new Error('Protected Cashu output lock mismatch');
    }
  }
}

function receiptProofs(operation) {
  const encoded = operation?.proofs;
  if (!Array.isArray(encoded) || !encoded.length || encoded.length > 128 ||
      encoded.some(proof => typeof proof !== 'string' || proof.length > 4096)) {
    throw new Error('Invalid protected Cashu proof list');
  }
  try {
    return deserializeProofs(encoded);
  } catch {
    throw new Error('Invalid protected Cashu proof encoding');
  }
}

function orderedKeysetIds(ids) {
  const unique = [...new Set(ids)].sort();
  if (!unique.length || unique.length > 128 || unique.some(id => typeof id !== 'string' || !KEYSET_ID.test(id))) {
    throw new Error('Expected one or more Cashu keyset IDs');
  }
  return unique;
}

function issuerKeyPin(mintUrl, cache, ids) {
  if (!Array.isArray(cache?.keysets) || normalizeWalletUrl(cache.mintUrl) !== mintUrl) {
    throw new Error('Protected receipt mint URL does not match its keyset cache');
  }
  const keysets = orderedKeysetIds(ids).map(id => {
    const matching = cache.keysets.filter(entry => entry?.id === id);
    if (matching.length !== 1 || matching[0].unit !== 'sat' || !matching[0].keys) {
      throw new Error('Protected receipt requires unique satoshi mint keysets');
    }
    const denominations = Object.entries(matching[0].keys).sort(([left], [right]) => left < right ? -1 : 1);
    if (!denominations.length || denominations.length > 128 || denominations.some(([amount, key]) =>
      !/^[1-9][0-9]{0,19}$/.test(amount) || !/^(02|03)[0-9a-f]{64}$/.test(key))) {
      throw new Error('Invalid protected mint denomination keys');
    }
    return [id, denominations];
  });
  return {mint: mintUrl, keyset_ids: keysets.map(([id]) => id),
    keysets_sha256: digest(JSON.stringify(['proof-grove/protected-mint-keys/v1', mintUrl, keysets]))};
}

export async function pinProtectedMint(endpoint, requestedKeysets) {
  const mint = normalizeWalletUrl(endpoint);
  const ids = orderedKeysetIds(requestedKeysets);
  const wallet = new Wallet(new Mint(mint, {customRequest: singleAttemptRequest}));
  await wallet.loadMint();
  await wallet.ensureOperableKeysets(ids);
  return issuerKeyPin(mint, wallet.keyChain.cache, ids);
}

export async function exportProtectedReceipt(operation, endpoint) {
  const mint_url = normalizeWalletUrl(endpoint);
  await auditProtected(operation, mint_url);
  const pin = issuerKeyPin(mint_url, operation.protectedMintCache.keys, receiptProofs(operation).map(proof => proof.id));
  const receipt = {schema: receiptSchema, mint_url,
    operation: Object.fromEntries(receiptFields.map(key => [key, operation[key]]))};
  return {receipt, pin};
}

export async function verifyProtectedReceipt(receipt, {mint, bundleId, keysetsSha256, amount}) {
  const mintUrl = normalizeWalletUrl(mint);
  if (!SHA256.test(bundleId ?? '') || !SHA256.test(keysetsSha256 ?? '') ||
      !Number.isSafeInteger(amount) || amount <= 0 || amount > 2_100_000_000_000_000) {
    throw new Error('Expected trusted reserve and mint keyset pins and reserve amount');
  }
  if (receipt?.schema !== receiptSchema || receipt.mint_url !== mintUrl ||
      receipt.operation?.protection?.bundle_id !== bundleId || receipt.operation.amount_sats !== amount) {
    throw new Error('Protected receipt differs from the pinned mint or reserve');
  }
  const operation = receipt.operation;
  const pin = issuerKeyPin(mintUrl, operation.protectedMintCache?.keys, receiptProofs(operation).map(proof => proof.id));
  if (pin.keysets_sha256 !== keysetsSha256) throw new Error('Protected receipt mint keyset pin mismatch');
  const {amount_sats, proof_count, bundle_id, lock_key, proofs_sha256, dleq_verified, offline_keyset_audit} =
    await auditProtected(operation, mintUrl);
  return {amount_sats, proof_count, bundle_id, lock_key, proofs_sha256, dleq_verified, offline_keyset_audit, ...pin};
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
  const proofs = receiptProofs(operation);
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

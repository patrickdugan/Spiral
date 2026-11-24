import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { deserializeProofs, Mint, sumProofs, Wallet } from '@cashu/cashu-ts';
import { Vault } from './vault.mjs';

const [mintUrl, vaultPath, operationId, address, evidenceFile] = process.argv.slice(2);
const endpoint = new URL(mintUrl);
assert.equal(endpoint.hostname, '127.0.0.1');
const vault = new Vault(vaultPath, process.env.PROOF_GROVE_WALLET_PASSWORD);
try {
  const operation = vault.load().operations[operationId];
  assert.equal(operation.state, 'protected-issued');
  const wallet = new Wallet(new Mint(mintUrl));
  await wallet.loadMint();
  const proofs = deserializeProofs(operation.proofs);
  assert.equal(Number(sumProofs(proofs).toString()), 25000);
  const before = await wallet.checkProofsStates(proofs);
  assert.ok(before.every(row => row.state === 'UNSPENT'));
  const quote = await wallet.createMeltQuoteOnchain(address, 24000);
  const fee = quote.fee_options.find(option => Number(option.fee_reserve.toString()) <= 1000);
  assert.ok(fee, 'No affordable onchain fee option for the melt control');
  const inputs = proofs.map(({amount, id, secret, C}) => ({amount:Number(amount.toString()), id, secret, C}));
  const response = await fetch(mintUrl + '/v1/melt/onchain', {
    method:'POST', redirect:'error', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({quote:quote.quote,fee_index:fee.fee_index,inputs}), signal:AbortSignal.timeout(30_000),
  });
  const rejection = await response.json();
  assert.equal(response.ok, false);
  assert.match(String(rejection.detail ?? rejection.error ?? ''), /witness|signature|spending condition|p2pk/i);
  const after = await wallet.checkProofsStates(proofs);
  assert.ok(after.every(row => row.state === 'UNSPENT'));
  // The fixture archive includes the signed, locked notes and public keys only.
  const keys = ['state','amount_sats','protection','protectedMintCache','proofs','request_sha256','evidence_level'];
  const certificate = JSON.stringify({schema:'proof-grove/protected-cdk-issuance-fixture/v1', mint_url:mintUrl,
    operation:Object.fromEntries(keys.map(key=>[key,operation[key]]))});
  writeFileSync(evidenceFile, certificate, {flag:'wx', mode:0o600});
  console.log(JSON.stringify({http_status:response.status, code:rejection.code,
    refused_protected_inputs:true, unspent_after_rejection:true,
    certificate_sha256:createHash('sha256').update(certificate).digest('hex')}));
} finally {
  vault.close();
}

import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,readFileSync } from 'node:fs';
import { resolve,join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { Vault } from '../wallet/vault.mjs';
import { authorizeIssue,authorizeBinding,verifyBinding } from '../wallet/authorization.mjs';
import { createRandomSecretKey,getPubKeyFromPrivKey,signMintQuote } from '../wallet/node_modules/@cashu/cashu-ts/lib/cashu-ts.es.js';

const root=resolve('.runtime');
test('encrypted wallet survives restart and rejects a different passphrase',async()=>{
  const directory=mkdtempSync(join(root,'wallet-test-')),file=join(directory,'vault.sqlite');
  let vault=new Vault(file,'test-passphrase-32-characters');
  const secret='test-secret-that-must-not-appear-on-disk';
  await vault.exclusive(()=>{const state=vault.load();state.secret=secret;vault.save(state)});vault.close();
  vault=new Vault(file,'test-passphrase-32-characters');assert.equal(vault.load().secret,secret);vault.close();
  assert.equal(readFileSync(file).includes(Buffer.from(secret)),false);
  vault=new Vault(file,'different-test-passphrase-32');assert.throws(()=>vault.load(),/incorrect|modified/);vault.close();
});
test('a second wallet process cannot take an active mutation lease',async()=>{
  const file=join(mkdtempSync(join(root,'wallet-test-')),'vault.sqlite');
  const a=new Vault(file,'test-passphrase-32-characters'),b=new Vault(file,'test-passphrase-32-characters');
  try {await a.exclusive(async()=>{await assert.rejects(b.exclusive(()=>{}),/active/)});}
  finally{a.close();b.close();}
});
test('public verifier checks SDK-backed application authorization and rejects substitution',()=>{
  const key=createRandomSecretKey(),pubkey=Buffer.from(getPubKeyFromPrivKey(key)).toString('hex');
  const outputs=[{id:'0011223344556677',amount:1,B_:pubkey}],quote='private-test-quote';
  const signature=signMintQuote(Buffer.from(key).toString('hex'),quote,outputs);
  const intent_id='cashu:unit-test-intent';
  const authorization=authorizeIssue(Buffer.from(key).toString('hex'),intent_id,{quote,outputs,signature});
  const check=payload=>{
    const cp=spawnSync(process.execPath,['wallet/public-verify.mjs'],{input:JSON.stringify({pubkey,payload,intent_id,authorization}),encoding:'utf8'});
    assert.equal(cp.status,0,cp.stderr);return JSON.parse(cp.stdout).valid;
  };
  assert.equal(check({quote,outputs,signature}),true);
  assert.equal(check({quote:'different-quote',outputs,signature}),false);
  assert.equal(check({quote,outputs:[{...outputs[0],amount:2}],signature}),false);
});
test('quote registration authorization binds the receiving address and amount',()=>{
  const key=createRandomSecretKey(),privkey=Buffer.from(key).toString('hex'),pubkey=Buffer.from(getPubKeyFromPrivKey(key)).toString('hex');
  const binding={quote:'private-test-id',request:'bcrt1-test-address',pubkey,amount_sats:25000};
  const authorization=authorizeBinding(privkey,binding);
  assert.equal(verifyBinding(pubkey,binding,authorization),true);
  assert.equal(verifyBinding(pubkey,{...binding,request:'different-address'},authorization),false);
  assert.equal(verifyBinding(pubkey,{...binding,amount_sats:25001},authorization),false);
});

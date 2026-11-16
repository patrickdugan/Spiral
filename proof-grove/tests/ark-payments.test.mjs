import test from 'node:test';
import assert from 'node:assert/strict';
import {createArkPayment,payArk,reconcileArk} from '../wallet/ark-payments.mjs';

// The native integration verifies cryptography. These tests target dispatch
// boundaries and durable reservations, including restarts with no reply.
function fixture(){
  let persisted={operations:{source:{id:'source',state:'spendable',evidence_level:'core-regtest',
    proofs:[{id:'0011223344556677',amount:'25000',secret:'public-test-secret',C:'02'+'11'.repeat(32)}]}}};
  let state=structuredClone(persisted),mode='regtest',sends=0;
  const quote={quote:'test-quote',amount:10000,fee_reserve:0,state:'UNPAID',expiry:Math.floor(Date.now()/1000)+600,method:'arkoor',unit:'sat',request:'ark-regtest-destination'};
  const sdk={checkProofsStates:async proofs=>proofs.map(()=>({state:'UNSPENT'})),getFeesForProofs:()=>0,
    createMeltQuote:async()=>({...quote}),checkMeltQuote:async()=>({...quote}),
    prepareMelt:async(_method,_quote,inputs)=>({inputs,outputData:[],keysetId:'0011223344556677'}),
    completeMelt:async()=>{sends++;assert.equal(persisted.operations.source.state,'melt_pending');assert.equal(Object.values(persisted.payments)[0].state,'dispatching');throw new Error('lost reply');}};
  const host={vault:{exclusive:async fn=>fn(),save:value=>{persisted=structuredClone(value);}},
    read:async()=>({mode}),state:()=>state,operation:(s,id)=>s.operations[id],wallet:async()=>sdk};
  return {host,quote,sdk,source:()=>state.operations.source,sends:()=>sends,
    setMode:value=>mode=value,restart:()=>{state=structuredClone(persisted);}};
}

test('withdrawal saves its reservation before sending and never repeats an uncertain send',async()=>{
  const f=fixture(),payment=await createArkPayment(f.host,'source','ark-regtest-destination',10000,0);
  assert.equal((await payArk(f.host,payment.payment_id)).state,'uncertain');
  f.restart();
  assert.equal((await payArk(f.host,payment.payment_id)).state,'uncertain');
  assert.equal((await reconcileArk(f.host,payment.payment_id)).state,'uncertain');
  assert.equal(f.sends(),1);assert.equal(f.source().state,'melt_pending');
  assert.equal(f.source().locked_by,payment.payment_id);
  await assert.rejects(createArkPayment(f.host,'source','ark-regtest-destination',1000,0),/unavailable|reserved/);
});

test('dispatch rechecks profile, quote destination, and fee budget before reserving proofs',async()=>{
  const f=fixture(),payment=await createArkPayment(f.host,'source','ark-regtest-destination',10000,0);
  f.setMode('live');await assert.rejects(payArk(f.host,payment.payment_id),/regtest/);
  f.setMode('regtest');f.quote.request='substituted-destination';await assert.rejects(payArk(f.host,payment.payment_id),/differs/);
  f.quote.request='ark-regtest-destination';f.quote.fee_reserve=1;await assert.rejects(payArk(f.host,payment.payment_id),/differs|budget/);
  assert.equal(f.sends(),0);assert.equal(f.source().state,'spendable');
});

test('an expired quote and changed input fees cannot trigger a payment',async()=>{
  const f=fixture(),payment=await createArkPayment(f.host,'source','ark-regtest-destination',10000,0);
  f.sdk.getFeesForProofs=()=>1;
  await assert.rejects(payArk(f.host,payment.payment_id),/budget/);
  f.sdk.getFeesForProofs=()=>0;
  // The saved quote's expiry is authoritative, even if the mint extends its reply.
  f.host.state().payments[payment.payment_id].expiry=1;
  await assert.rejects(payArk(f.host,payment.payment_id),/payable/);
  assert.equal(f.sends(),0);
});

test('a payment that was only quoted is not marked redeemed by a mint report',async()=>{
  const f=fixture(),payment=await createArkPayment(f.host,'source','ark-regtest-destination',10000,0);
  f.quote.state='PAID';
  assert.equal((await reconcileArk(f.host,payment.payment_id)).state,'quoted');
  assert.equal(f.source().state,'spendable');assert.equal(f.sends(),0);
});

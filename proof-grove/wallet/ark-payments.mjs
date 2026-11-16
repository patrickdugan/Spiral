import {randomUUID} from 'node:crypto';
import {OutputData,serializeProofs,deserializeProofs,sumProofs} from '@cashu/cashu-ts';

const number=value=>{
  const n=Number(value?.toString?.()??value);
  if(!Number.isSafeInteger(n)||n<0||n>2_100_000_000_000_000)throw new Error('Invalid payment amount');
  return n;
};
const amount=value=>{const n=number(value);if(!n)throw new Error('Payment amount must be positive');return n;};
const brief=payment=>({payment_id:payment.id,source_operation:payment.source,destination:payment.destination,
  amount_sats:payment.amount_sats,max_fee_sats:payment.max_fee_sats,state:payment.state,
  mint_state:payment.mint_state,actual_fee_sats:payment.actual_fee_sats,change_sats:payment.change_sats,
  evidence_level:'mint-report',meaning:'Mint redemption and wallet change only; verify the receiving Ark wallet separately.'});
const quoteBound=(quote,payment)=>{
  if(quote.quote!==payment.quote_id||number(quote.amount)!==payment.amount_sats||
     (quote.request&&quote.request!==payment.destination)||(quote.unit&&quote.unit!=='sat')||
     (quote.method&&quote.method!=='arkoor')||number(quote.fee_reserve??0)>payment.max_fee_sats)
    throw new Error('Ark melt quote differs from the saved payment');
};
const paymentFrom=(state,id)=>{const payment=state.payments?.[id];if(!payment)throw new Error('Unknown Ark payment');return payment;};

export async function createArkPayment(host,sourceId,destination,value,maxFee=0){
  const sats=amount(value),fee=number(maxFee);
  if(typeof destination!=='string'||destination!==destination.trim()||destination.length<10||destination.length>1024)
    throw new Error('Invalid Ark destination');
  return host.vault.exclusive(async()=>{
    const status=await host.read('/api/status');
    if(status.mode!=='regtest')throw new Error('Ark withdrawal currently requires the regtest profile');
    const state=host.state(),source=host.operation(state,sourceId),wallet=await host.wallet();
    if(source.state!=='spendable'||source.locked_by||!source.proofs?.length)throw new Error('Source proofs are unavailable or reserved');
    if(source.evidence_level!=='core-regtest'&&source.admission?.evidence_level!=='core-regtest')throw new Error('Regtest payment admission required');
    const proofs=deserializeProofs(source.proofs),total=number(sumProofs(proofs));
    const states=await wallet.checkProofsStates(proofs);
    if(states.length!==proofs.length||states.some(p=>p.state!=='UNSPENT'))throw new Error('Source proofs are spent or pending');
    const inputFee=number(wallet.getFeesForProofs(proofs));
    const quote=await wallet.createMeltQuote('arkoor',{method:'arkoor',request:destination,amount:sats});
    const payment={id:randomUUID(),source:sourceId,destination,amount_sats:sats,max_fee_sats:fee,
      input_total_sats:total,input_fee_sats:inputFee,quote_id:quote.quote,expiry:quote.expiry,state:'quoted',mint_state:quote.state};
    quoteBound(quote,payment);
    if(inputFee+number(quote.fee_reserve??0)>fee||sats+inputFee+number(quote.fee_reserve??0)>total)throw new Error('Payment exceeds its fee or proof budget');
    if(quote.state!=='UNPAID'||!Number.isSafeInteger(quote.expiry)||quote.expiry<=Date.now()/1000)throw new Error('Melt quote is not payable');
    state.payments??={};state.payments[payment.id]=payment;host.vault.save(state);
    return brief(payment);
  });
}

export async function payArk(host,id){
  return host.vault.exclusive(async()=>{
    const state=host.state(),payment=paymentFrom(state,id),source=host.operation(state,payment.source);
    if(payment.state!=='quoted')return brief(payment); // Uncertain dispatch is reconciled, never resent here.
    if((await host.read('/api/status')).mode!=='regtest')throw new Error('Ark withdrawal currently requires the regtest profile');
    const wallet=await host.wallet(),quote=await wallet.checkMeltQuote('arkoor',payment.quote_id);
    quoteBound(quote,payment);
    if(quote.state!=='UNPAID'||payment.expiry<=Date.now()/1000)throw new Error('Melt quote is no longer payable');
    if(source.state!=='spendable'||source.locked_by)throw new Error('Source proofs are unavailable or reserved');
    const inputs=deserializeProofs(source.proofs),states=await wallet.checkProofsStates(inputs);
    if(number(sumProofs(inputs))!==payment.input_total_sats||states.length!==inputs.length||states.some(p=>p.state!=='UNSPENT'))throw new Error('Source proofs changed or are unavailable');
    const inputFee=number(wallet.getFeesForProofs(inputs));
    if(inputFee+number(quote.fee_reserve??0)>payment.max_fee_sats)throw new Error('Current input fees exceed the saved budget');
    const preview=await wallet.prepareMelt('arkoor',quote,inputs);
    payment.preview={inputs:serializeProofs(preview.inputs),outputData:preview.outputData.map(OutputData.serialize),keysetId:preview.keysetId};
    payment.state='dispatching';source.locked_by=payment.id;source.state='melt_pending';host.vault.save(state);
    try{
      const response=await wallet.completeMelt(preview);
      payment.mint_state=response.quote.state;payment.state='response_received';host.vault.save(state);
    }catch{
      payment.state='uncertain';host.vault.save(state);
      return brief(payment);
    }
    // Reconciliation uses the same persisted preview even after a successful reply.
    return reconcileUnlocked(host,state,payment,wallet);
  });
}

async function reconcileUnlocked(host,state,payment,wallet){
  if(payment.state==='cashu_redeemed')return brief(payment);
  const quote=await wallet.checkMeltQuote('arkoor',payment.quote_id);quoteBound(quote,payment);
  if(payment.state==='quoted')return brief(payment); // No saved inputs were ever submitted by this wallet.
  payment.mint_state=quote.state;
  if(!payment.preview||quote.state!=='PAID'){
    payment.state=payment.preview?(quote.state==='PENDING'?'pending':'uncertain'):'quoted';host.vault.save(state);return brief(payment);
  }
  const inputs=deserializeProofs(payment.preview.inputs),inputStates=await wallet.checkProofsStates(inputs);
  if(inputStates.length!==inputs.length||inputStates.some(p=>p.state!=='SPENT'))throw new Error('Paid quote does not have fully spent inputs; keep its reservation');
  let outputData=payment.preview.outputData.map(OutputData.deserialize),signatures=quote.change||[];
  if(!signatures.length&&payment.input_total_sats-payment.amount_sats>payment.max_fee_sats){
    const restored=await wallet.mint.restore({outputs:outputData.map(o=>o.blindedMessage)});
    if(restored.outputs.length!==restored.signatures.length)throw new Error('Melt change restoration is inconsistent');
    const own=new Map(outputData.map(o=>[o.blindedMessage.B_,o])),seen=new Set();
    outputData=restored.outputs.map(o=>{
      const data=own.get(o.B_);if(!data||seen.has(o.B_)||data.blindedMessage.id!==o.id)throw new Error('Melt change restoration returned unknown outputs');
      seen.add(o.B_);return data;
    });
    signatures=restored.signatures;
  }
  await wallet.ensureOperableKeysets(signatures.map(s=>s.id));
  const change=wallet.createMeltChangeProofs(outputData,signatures);
  const checked=await wallet.verifyMintSignatures(change,{require:true});
  if(checked.invalid.length||checked.valid.length!==change.length)throw new Error('Melt change DLEQ verification failed');
  const changeStates=await wallet.checkProofsStates(change);
  if(changeStates.length!==change.length||changeStates.some(p=>p.state!=='UNSPENT'))throw new Error('Melt change is spent or pending');
  const changeValue=number(sumProofs(change)),actualFee=payment.input_total_sats-payment.amount_sats-changeValue;
  if(actualFee<0||actualFee>payment.max_fee_sats)throw new Error('Actual melt cost exceeds the saved budget; retain recovery data');
  const source=host.operation(state,payment.source);
  if(source.locked_by!==payment.id)throw new Error('Melt proof reservation changed');
  source.proofs=serializeProofs(change);source.state=change.length?'spendable':'spent';delete source.locked_by;
  payment.state='cashu_redeemed';payment.actual_fee_sats=actualFee;payment.change_sats=changeValue;
  payment.payment_proof=quote.payment_preimage;payment.change_dleq_verified=true;host.vault.save(state);
  return brief(payment);
}

export async function reconcileArk(host,id){
  return host.vault.exclusive(async()=>{
    const state=host.state(),payment=paymentFrom(state,id);
    if(payment.state==='cashu_redeemed')return brief(payment);
    return reconcileUnlocked(host,state,payment,await host.wallet());
  });
}
export function listArkPayments(host){return Object.values(host.state().payments||{}).map(brief);}

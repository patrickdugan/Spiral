import { Wallet, Mint, OutputData, createRandomSecretKey, getPubKeyFromPrivKey,
  serializeProofs, deserializeProofs, getEncodedToken, sumProofs } from '@cashu/cashu-ts';
import { randomUUID } from 'node:crypto';
import { authorizeIssue,authorizeBinding } from './authorization.mjs';
import {createArkPayment,payArk,reconcileArk,listArkPayments} from './ark-payments.mjs';
import {singleAttemptRequest} from './transport.mjs';
import {auditProtected, issueIntentDomain, observeProtection, requireProtectedSecrets} from './protected.mjs';

const hex = bytes => Buffer.from(bytes).toString('hex');
const normalizeUrl = value => { const url=new URL(value); if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error('Invalid wallet endpoint'); if(url.protocol==='http:'&&!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw new Error('Remote endpoints require HTTPS'); return url.href.replace(/\/$/,''); };

export class ProofWallet {
  constructor({mintUrl,deskUrl,vault,deskToken}) {
    this.mintUrl=normalizeUrl(mintUrl);this.deskUrl=normalizeUrl(deskUrl);this.vault=vault;
    if(deskToken!==undefined&&!/^[A-Za-z0-9_-]{43,128}$/.test(deskToken))throw new Error('Invalid backend operator token');
    this.deskToken=deskToken;
  }
  deskHeaders(){return {'Content-Type':'application/json','X-Proof-Grove':'1',...(this.deskToken?{Authorization:'Bearer '+this.deskToken}:{})};}
  async request(path,body) {
    const response=await fetch(this.deskUrl+path,{method:'POST',redirect:'error',headers:this.deskHeaders(),body:JSON.stringify(body),signal:AbortSignal.timeout(90_000)});
    const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Proof desk request failed');
    return data;
  }
  async wallet() { const wallet=new Wallet(new Mint(this.mintUrl,{customRequest:singleAttemptRequest}));await wallet.loadMint();return wallet; }
  async read(path) {
    const response=await fetch(this.deskUrl+path,{redirect:'error',headers:this.deskHeaders(),signal:AbortSignal.timeout(30_000)});
    if(!response.ok)throw new Error('Proof desk read failed');return response.json();
  }
  createArkPayment(id,destination,amount,maxFee){return createArkPayment(this,id,destination,amount,maxFee);}
  payArk(id){return payArk(this,id);}
  reconcileArk(id){return reconcileArk(this,id);}
  listArkPayments(){return listArkPayments(this);}
  state() {
    const state=this.vault.load();
    if(state.mintUrl && (state.mintUrl!==this.mintUrl || state.deskUrl!==this.deskUrl))throw new Error('Wallet endpoints cannot change for an existing vault');
    state.mintUrl=this.mintUrl;state.deskUrl=this.deskUrl;return state;
  }
  operation(state,id) { const operation=state.operations[id];if(!operation)throw new Error('Unknown wallet operation');return operation; }
  summary(operation) { return {operation_id:operation.id,intent_id:operation.intent?.id,amount_sats:operation.amount_sats,state:operation.state,
    balance_sats:operation.proofs&&!operation.protection?Number(sumProofs(deserializeProofs(operation.proofs)).toString()):undefined,
    protected_bundle_id:operation.protection?.bundle_id,
    request:operation.intent ? operation.quote?.request : undefined,pubkey:operation.pubkey,payment_expiry:operation.quote?.expiry,
    proof_admission_expiry:operation.intent?.expires_at,unit:'sat',mint:this.mintUrl}; }
  async createDeposit(amount) {
    if(!Number.isSafeInteger(amount)||amount<=0||amount>2_100_000_000_000_000)throw new Error('Invalid satoshi amount');
    return this.vault.exclusive(async()=>{
      const wallet=await this.wallet(),state=this.state(),key=createRandomSecretKey();
      const operation={id:randomUUID(),amount_sats:amount,privkey:hex(key),pubkey:hex(getPubKeyFromPrivKey(key)),state:'creating_quote'};
      state.operations[operation.id]=operation;this.vault.save(state);
      const quote=await wallet.createMintQuoteOnchain(operation.pubkey);
      operation.quote={quote:quote.quote,pubkey:quote.pubkey,request:quote.request,expiry:quote.expiry,unit:quote.unit,method:quote.method};
      operation.state='binding_quote';this.vault.save(state);
      const authorization=authorizeBinding(operation.privkey,{quote:quote.quote,request:quote.request,pubkey:operation.pubkey,amount_sats:amount});
      const binding=await this.request('/api/cashu/bind',{quote_id:quote.quote,pubkey:operation.pubkey,amount_sats:amount,authorization});
      operation.intent=binding.intent;operation.state='awaiting_payment';this.vault.save(state);
      return this.summary(operation);
    });
  }
  async admitRegtest(id,txid,vout) {
    return this.vault.exclusive(async()=>{
      const state=this.state(),operation=this.operation(state,id);
      if(!operation.intent)throw new Error('Quote has not been bound');
      const result=await this.request('/api/verify',{intent_id:operation.intent.id,txid,vout});
      if(result.evidence_level!=='core-regtest')throw new Error('Unexpected regtest admission evidence');
      operation.admission={id:result.decision.receipt.id,evidence_level:result.evidence_level};
      this.vault.save(state);return {accepted:result.decision.accepted,evidence_level:result.evidence_level};
    });
  }
  async bind(id) {
    return this.vault.exclusive(async()=>{
      const state=this.state(),operation=this.operation(state,id);
      if(!operation.quote)throw new Error('No quote response was saved for this operation');
      const authorization=authorizeBinding(operation.privkey,{quote:operation.quote.quote,request:operation.quote.request,pubkey:operation.pubkey,amount_sats:operation.amount_sats});
      const binding=await this.request('/api/cashu/bind',{quote_id:operation.quote.quote,pubkey:operation.pubkey,amount_sats:operation.amount_sats,authorization});
      operation.intent=binding.intent;operation.state='awaiting_payment';this.vault.save(state);return this.summary(operation);
    });
  }
  async claim(id, protectedOptions) {
    return this.vault.exclusive(async()=>{
      const state=this.state(),operation=this.operation(state,id);
      const protection=protectedOptions ? observeProtection(operation, protectedOptions) : null;
      if ((operation.preview || operation.proofs || operation.protection) &&
          operation.protection?.bundle_id !== protection?.bundle_id) {
        throw new Error('Saved issuance protection cannot change');
      }
      if (operation.proofs && protection) {
        return {...await auditProtected(operation, this.mintUrl), idempotent_replay: true};
      }
      const wallet=await this.wallet();
      if(operation.proofs){
        if(operation.state!=='spendable')throw new Error('Issued proofs are spent or reserved; no new issuance requested');
        const proofs=deserializeProofs(operation.proofs),states=await wallet.checkProofsStates(proofs);
        if(states.length!==proofs.length||states.some(p=>p.state!=='UNSPENT'))throw new Error('Issued proofs are spent or pending; no new issuance requested');
        return {state:'spendable',amount_sats:Number(sumProofs(proofs).toString()),idempotent_replay:true};
      }
      if(!operation.intent)throw new Error('Quote has not been bound');
      if(!operation.preview) {
        const quote=await wallet.checkMintQuoteOnchain(operation.quote.quote);
        if (protection && !wallet.getMintInfo().isSupported(11).supported) {
          throw new Error('Mint does not advertise NUT-11');
        }
        const outputType=protection ? {type:'p2pk',options:{pubkey:protection.lock_key,blindKeys:false}} : undefined;
        const preview=await wallet.prepareMint('onchain',operation.amount_sats,quote,{privkey:operation.privkey},outputType);
        const payload={quote:preview.payload.quote,signature:preview.payload.signature,outputs:preview.payload.outputs.map(o=>({amount:Number(o.amount.toString()),id:o.id,B_:o.B_}))};
        operation.preview={payload,authorization:authorizeIssue(operation.privkey,issueIntentDomain(operation.intent.id,protection),payload),outputData:preview.outputData.map(OutputData.serialize)};
        if (protection) operation.protection={bundle_id:protection.bundle_id,lock_key:protection.lock_key};
        operation.state='outputs_prepared';this.vault.save(state);
      }
      const result=await this.request('/api/cashu/issue',{intent_id:operation.intent.id,payload:operation.preview.payload,authorization:operation.preview.authorization,
        ...(protection ? {protection:{bundle:protection.bundle,bundle_id:protection.bundle_id}} : {})});
      if(result.state!=='blind-signatures-received'||!Array.isArray(result.signatures))throw new Error('Unexpected mint response');
      const outputData=operation.preview.outputData.map(OutputData.deserialize);
      if(outputData.length!==result.signatures.length)throw new Error('Mint signature count mismatch');
      await wallet.ensureOperableKeysets(result.signatures.map(s=>s.id));
      const proofs=outputData.map((output,index)=>output.toProof(result.signatures[index],wallet.getKeyset(result.signatures[index].id)));
      const verified=await wallet.verifyMintSignatures(proofs,{require:true});
      if(verified.invalid.length||verified.valid.length!==proofs.length)throw new Error('Mint signature DLEQ verification failed');
      if (protection) {
        if (result.protected_bundle_id !== protection.bundle_id) throw new Error('Mint response reserve binding mismatch');
        requireProtectedSecrets(proofs, protection.lock_key);
        observeProtection(operation, protectedOptions);
        const cache={info:wallet.getMintInfo().cache,keys:wallet.keyChain.cache};
        operation.protectedMintCache=JSON.parse(JSON.stringify(cache, (_,value)=>typeof value==='bigint'?value.toString():value));
      }
      const states=await wallet.checkProofsStates(proofs);
      if(states.length!==proofs.length||states.some(p=>p.state!=='UNSPENT'))throw new Error('Mint does not report every issued proof as unspent');
      if(Number(sumProofs(proofs).toString())!==operation.amount_sats)throw new Error('Mint returned the wrong token amount');
      operation.proofs=serializeProofs(proofs);operation.state=protection?'protected-issued':'spendable';operation.request_sha256=result.request_sha256;operation.evidence_level=result.evidence_level;this.vault.save(state);
      if (protection) return {...await auditProtected(operation, this.mintUrl), idempotent_replay:result.idempotent_replay};
      return {state:'spendable',amount_sats:operation.amount_sats,proof_count:proofs.length,dleq_verified:true,evidence_level:result.evidence_level,idempotent_replay:result.idempotent_replay};
    });
  }
  protectedAudit(id) { return auditProtected(this.operation(this.state(), id), this.mintUrl); }
  protectedMelt(id, action, bundle, psbt) {
    const operation = this.operation(this.state(), id);
    if (operation.state !== 'protected-issued' || !operation.protection ||
        operation.protection.bundle_id !== bundle?.bundle_id) {
      throw new Error('Reserve bundle does not match the issued protected claim');
    }
    return this.request(`/api/cashu/protected/${action}`, {
      intent_id:operation.intent.id, bundle_id:operation.protection.bundle_id, bundle, psbt,
    });
  }
  token(id) {
    const state=this.state(),operation=this.operation(state,id);
    if(operation.state!=='spendable'||!operation.proofs)throw new Error('No spendable token for this operation');
    return getEncodedToken({mint:this.mintUrl,unit:'sat',proofs:deserializeProofs(operation.proofs)});
  }
  list() { const state=this.state();return Object.values(state.operations).map(op=>this.summary(op)); }
}

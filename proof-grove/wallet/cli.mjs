import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { sumProofs } from '@cashu/cashu-ts';
import { Vault } from './vault.mjs';
import { ProofWallet } from './client.mjs';

const [command,...argv]=process.argv.slice(2),options={};
for(let i=0;i<argv.length;i+=2){if(!argv[i]?.startsWith('--')||argv[i+1]===undefined)throw new Error('Expected --option value');options[argv[i].slice(2)]=argv[i+1];}
let vault;
try {
  if(!options.vault||!options.mint||!options.desk)throw new Error('Use --vault FILE --mint URL --desk URL');
  vault=new Vault(resolve(options.vault),process.env.PROOF_GROVE_WALLET_PASSWORD);
  const wallet=new ProofWallet({mintUrl:options.mint,deskUrl:options.desk,vault,deskToken:process.env.PROOF_GROVE_DESK_TOKEN});
  let result;
  if(command==='deposit')result=await wallet.createDeposit(Number(options.amount));
  else if(command==='bind')result=await wallet.bind(options.id);
  else if(command==='admit-regtest')result=await wallet.admitRegtest(options.id,options.txid,Number(options.vout));
  else if(command==='claim')result=await wallet.claim(options.id);
  else if(command==='list')result=wallet.list();
  else if(command==='ark-quote')result=await wallet.createArkPayment(options.id,options.destination,Number(options.amount),Number(options['max-fee']||0));
  else if(command==='ark-pay')result=await wallet.payArk(options.payment);
  else if(command==='ark-status')result=await wallet.reconcileArk(options.payment);
  else if(command==='ark-list')result=wallet.listArkPayments();
  else if(command==='audit'){
    const token=wallet.token(options.id),sdk=await wallet.wallet(),decoded=sdk.decodeToken(token);
    result={state:'spendable',amount_sats:Number(sumProofs(decoded.proofs).toString()),proof_count:decoded.proofs.length,token_sha256:createHash('sha256').update(token).digest('hex'),mint:decoded.mint};
  } else if(command==='export') {
    if(!options.output)throw new Error('Export requires --output FILE; the file is a bearer token');
    writeFileSync(resolve(options.output),wallet.token(options.id),{flag:'wx',mode:0o600});
    result={exported:true};
  } else throw new Error('Commands: deposit, bind, admit-regtest, claim, list, audit, export, ark-quote, ark-pay, ark-status, ark-list');
  console.log(JSON.stringify(result));
} catch(error){console.log(JSON.stringify({error:error.message}));process.exitCode=1;}
finally{vault?.close();}

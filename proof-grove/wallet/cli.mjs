import { resolve } from 'node:path';
import { closeSync, fstatSync, openSync, readFileSync, readSync, statSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { sumProofs } from '@cashu/cashu-ts';
import { Vault } from './vault.mjs';
import { ProofWallet } from './client.mjs';
import { exportCooperativePsbt, pinProtectedMint, verifyProtectedReceipt } from './protected.mjs';

const [command,...argv]=process.argv.slice(2),options={};
for(let i=0;i<argv.length;i+=2){if(!argv[i]?.startsWith('--')||argv[i+1]===undefined)throw new Error('Expected --option value');options[argv[i].slice(2)]=argv[i+1];}

function readProtectedReceipt(path, limit = 2 * 1024 * 1024) {
  if (!path) throw new Error('Verify requires --receipt FILE');
  const file = openSync(path, 'r');
  try {
    const metadata = fstatSync(file);
    if (!metadata.isFile() || metadata.size > limit) throw new Error('Protected receipt is too large');
    const buffer = Buffer.alloc(limit + 1);
    let length = 0;
    while (length < buffer.length) {
      const read = readSync(file, buffer, length, buffer.length - length, null);
      if (read === 0) break;
      length += read;
    }
    if (length > limit) throw new Error('Protected receipt is too large');
    try {
      return JSON.parse(buffer.toString('utf8', 0, length));
    } catch {
      throw new Error('Invalid protected issuance receipt JSON');
    }
  } finally {
    closeSync(file);
  }
}

let vault;
try {
  let wallet, result;
  if (!['protected-pin-mint', 'protected-verify-receipt'].includes(command)) {
    if(!options.vault||!options.mint||!options.desk)throw new Error('Use --vault FILE --mint URL --desk URL');
    vault=new Vault(resolve(options.vault),process.env.PROOF_GROVE_WALLET_PASSWORD);
    wallet=new ProofWallet({mintUrl:options.mint,deskUrl:options.desk,vault,deskToken:process.env.PROOF_GROVE_DESK_TOKEN});
  }
  if (command === 'protected-pin-mint') {
    result = await pinProtectedMint(options.mint, (options.keysets ?? '').split(','));
  } else if (command === 'protected-verify-receipt') {
    result = await verifyProtectedReceipt(readProtectedReceipt(options.receipt), {
      mint: options.mint, bundleId: options['bundle-id'], keysetsSha256: options['keysets-sha256'],
      amount: Number(options.amount), bundle: options.bundle ? readProtectedReceipt(options.bundle, 32_768) : undefined,
    });
  } else if (command === 'protected-export-receipt') {
    if (!options.output) throw new Error('Export requires --output FILE');
    const {receipt, pin} = await wallet.protectedReceipt(options.id);
    writeFileSync(resolve(options.output), JSON.stringify(receipt), {flag:'wx', mode:0o600});
    result = pin;
  }
  else if(command==='deposit')result=await wallet.createDeposit(Number(options.amount));
  else if(command==='protected-draft')result=await wallet.draftProtectedBatch(options.id);
  else if(command==='bind')result=await wallet.bind(options.id);
  else if(command==='admit-regtest')result=await wallet.admitRegtest(options.id,options.txid,Number(options.vout));
  else if(command==='claim')result=await wallet.claim(options.id);
  else if(command==='protected-claim')result=await wallet.claim(options.id,{
    bundlePath:options.bundle,bundleId:options['bundle-id'],coreConfig:options['core-config'],python:options.python,
  });
  else if(command==='protected-audit')result=await wallet.protectedAudit(options.id);
  else if(['protected-melt-prepare','protected-melt-settle','protected-melt-status'].includes(command)) {
    const action=command.slice('protected-melt-'.length);
    if(!options.bundle||statSync(options.bundle).size>32_768)throw new Error('A bounded --bundle is required');
    if(action==='prepare'&&(!options.output||!options['core-config']))throw new Error('Prepare requires --output FILE and --core-config FILE');
    if(action==='settle'&&(!options.psbt||statSync(options.psbt).size>16_384))throw new Error('A bounded --psbt is required');
    const bundle=JSON.parse(readFileSync(options.bundle,'utf8'));
    const signature=action==='settle' ? readFileSync(options.psbt,'ascii').trim() : undefined;
    result=await wallet.protectedMelt(options.id,action,bundle,signature);
    if(action==='prepare') {
      result=exportCooperativePsbt({bundlePath:options.bundle,bundleId:bundle.bundle_id,
        coreConfig:options['core-config'],output:options.output,python:options.python}, result.txid);
    }
  }
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
  } else throw new Error('Commands: deposit, bind, admit-regtest, claim, protected-draft, protected-claim, protected-audit, protected-export-receipt, protected-pin-mint, protected-verify-receipt, protected-melt-prepare, protected-melt-settle, protected-melt-status, list, audit, export, ark-quote, ark-pay, ark-status, ark-list');
  console.log(JSON.stringify(result));
} catch(error){console.log(JSON.stringify({error:error.message}));process.exitCode=1;}
finally{vault?.close();}

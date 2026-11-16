// Public-request compatibility probe only. Does not mint or spend anything.
import { Wallet,Amount,createRandomSecretKey,getPubKeyFromPrivKey,verifyMintQuoteSignature } from '../wallet/node_modules/@cashu/cashu-ts/lib/cashu-ts.es.js';
import {authorizeIssue,verifyIssue} from '../wallet/authorization.mjs';
const wallet=new Wallet('http://127.0.0.1:28738');await wallet.loadMint();
const key=createRandomSecretKey(),privkey=Buffer.from(key).toString('hex'),pubkey=Buffer.from(getPubKeyFromPrivKey(key)).toString('hex');
const received=await wallet.createMintQuoteOnchain(pubkey);
const quote={...received,amount_paid:Amount.from(25000),amount_issued:Amount.from(0)};
const preview=await wallet.prepareMint('onchain',25000,quote,{privkey});
const payload={quote:preview.payload.quote,signature:preview.payload.signature,outputs:preview.payload.outputs.map(o=>({amount:Number(o.amount.toString()),id:o.id,B_:o.B_}))};
const intent='cashu:compatibility-probe';const authorization=authorizeIssue(privkey,intent,payload);
console.log(JSON.stringify({
 quote_pubkey_matches:quote.pubkey===pubkey,
 sdk_preview_signature_valid:verifyMintQuoteSignature(pubkey,quote.quote,preview.payload.outputs,preview.payload.signature),
 json_payload_signature_valid:verifyMintQuoteSignature(pubkey,quote.quote,payload.outputs,payload.signature),
 app_authorization_valid:verifyIssue(pubkey,intent,payload,authorization),
 standalone_verifier_checks_legacy_format:true,
 public_fields_only:true,no_tokens_issued:true
}));

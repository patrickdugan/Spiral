import { verifyIssue,verifyBinding } from './authorization.mjs';
let input = '';
for await (const chunk of process.stdin) { input += chunk; if(input.length > 256_000) process.exit(1); }
try {
  const {pubkey,payload,intent_id,authorization,action} = JSON.parse(input);
  if(action==='bind'){
    process.stdout.write(JSON.stringify({valid:verifyBinding(pubkey,payload,authorization)}));process.exit(0);
  }
  const valid = typeof intent_id==='string' && typeof authorization==='string' && verifyIssue(pubkey,intent_id,payload,authorization);
  process.stdout.write(JSON.stringify({valid}));
} catch { process.stdout.write('{"valid":false}'); }

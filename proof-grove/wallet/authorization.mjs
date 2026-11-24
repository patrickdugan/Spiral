import { createHash } from 'node:crypto';
import { signMintQuote,verifyMintQuoteSignature } from '@cashu/cashu-ts';

// Use the SDK's matched public signing/verifying primitives for an application
// domain. The mint validates its own NUT-20 wire format (the SDK's prepared mint
// uses the amended format, while its standalone helpers implement the legacy
// format). App authorization covers the complete, untouched prepared request.
export function canonical(value) {
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export function issueDomain(intentId,payload) {
  return 'proof-grove/cashu-issue/v1:'+intentId+':'+createHash('sha256').update(canonical(payload)).digest('hex');
}
export const authorizeIssue = (privkey,intentId,payload) => signMintQuote(privkey,issueDomain(intentId,payload),payload.outputs);
export const verifyIssue = (pubkey,intentId,payload,authorization) =>
  verifyMintQuoteSignature(pubkey,issueDomain(intentId,payload),payload.outputs,authorization);
const bindingDomain = binding => 'proof-grove/cashu-bind/v1:'+createHash('sha256').update(canonical(binding)).digest('hex');
export const authorizeBinding = (privkey,binding) => signMintQuote(privkey,bindingDomain(binding),[]);
export const verifyBinding = (pubkey,binding,authorization) => verifyMintQuoteSignature(pubkey,bindingDomain(binding),[],authorization);

import {JSONInt,MintOperationError,HttpResponseError,NetworkError} from '@cashu/cashu-ts';

// NUT-19 advertises retryable endpoints. A durable local payment reservation
// deliberately uses one attempt, then reconciles the saved quote after restart.
export async function singleAttemptRequest(options){
  const signal=options.signal?AbortSignal.any([options.signal,AbortSignal.timeout(60_000)]):AbortSignal.timeout(60_000);
  let response,text;
  try{
    response=await fetch(options.endpoint,{method:options.method||'GET',signal,redirect:'error',
      cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',
      headers:{'Content-Type':'application/json','User-Agent':'Proof Grove',...(options.headers||{})},
      body:options.requestBody===undefined?undefined:JSONInt.stringify(options.requestBody)});
    text=await response.text();
  }catch(cause){throw new NetworkError('Mint connection failed',{cause});}
  let data;
  try{data=text?JSONInt.parse(text):null;}
  catch{throw new HttpResponseError('Mint returned invalid JSON',response.status);}
  if(!response.ok){
    // Do not echo a provider body: it might contain the submitted bearer proofs.
    if(Number.isSafeInteger(data?.code))throw new MintOperationError(data.code,'Mint rejected the request');
    throw new HttpResponseError('Mint request failed',response.status);
  }
  return data;
}

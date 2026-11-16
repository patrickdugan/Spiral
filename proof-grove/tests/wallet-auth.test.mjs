import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {ProofWallet} from '../wallet/client.mjs';

test('operator authorization goes only to the desk and is not added to vault state',async()=>{
  const seen=[];const token='a'.repeat(43);
  const server=createServer((request,response)=>{seen.push({authorization:request.headers.authorization,url:request.url});request.resume();response.setHeader('Content-Type','application/json');response.end('{}');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const state={operations:{}};
  const wallet=new ProofWallet({mintUrl:'https://mint.example',deskUrl:`http://127.0.0.1:${server.address().port}`,deskToken:token,vault:{load:()=>state}});
  try{
    await wallet.read('/api/status');await wallet.request('/api/cashu/bind',{quote_id:'public-test-id'});
    assert.equal(seen.length,2);assert.ok(seen.every(request=>request.authorization==='Bearer '+token));
    assert.ok(seen.every(request=>!request.url.includes(token)));
    assert.doesNotMatch(JSON.stringify(wallet.state()),new RegExp(token));
  }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});

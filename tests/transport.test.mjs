import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {singleAttemptRequest} from '../wallet/transport.mjs';

async function fixture(handler,check){
  const server=createServer(handler);await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try{await check(`http://127.0.0.1:${server.address().port}`);}
  finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
}

test('a lost POST response is not replayed even when NUT-19 advertises caching',async()=>{
  let posts=0;
  await fixture((request,response)=>{posts++;request.resume();request.on('end',()=>response.destroy());},async base=>{
    await assert.rejects(singleAttemptRequest({endpoint:base+'/v1/melt/arkoor',method:'POST',requestBody:{quote:'test'},
      cached_endpoints:[{path:'/v1/melt/arkoor',method:'POST'}],ttl:Infinity}),/Mint connection failed/);
    assert.equal(posts,1);
  });
});

test('mint errors retain their numeric code without echoing provider content',async()=>{
  await fixture((_request,response)=>{response.writeHead(400,{'Content-Type':'application/json'});response.end(JSON.stringify({code:12001,detail:'PRIVATE_PROOF_MUST_NOT_BE_PRINTED'}));},async base=>{
    await assert.rejects(singleAttemptRequest({endpoint:base,method:'GET'}),error=>{
      assert.equal(error.code,12001);assert.doesNotMatch(error.message,/PRIVATE_PROOF/);return true;
    });
  });
});

test('a redirect cannot replay a request body at another endpoint',async()=>{
  let target=0;
  await fixture((request,response)=>{
    if(request.url==='/target'){target++;response.end('{}');}
    else{response.writeHead(307,{Location:'/target'});response.end();}
  },async base=>{
    await assert.rejects(singleAttemptRequest({endpoint:base+'/start',method:'POST',requestBody:{proof:'private-fixture'}}),/Mint connection failed/);
    assert.equal(target,0);
  });
});

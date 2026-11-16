'use strict';
// Endpoint configuration is public. The operator token exists only in this tab.
(() => {
  const $=id=>document.getElementById(id);
  let endpoint='',token='';
  const connection={connected:false,onConnect:null,onDisconnect:null};
  function disconnect(message='Disconnected. No backend data is being fetched.'){
    endpoint='';token='';connection.connected=false;$('backend-token').value='';
    $('backend-form').hidden=false;$('disconnect-backend').hidden=true;
    $('backend-status').textContent=message;$('mode-badge').textContent='BACKEND DISCONNECTED';
    document.querySelectorAll('[data-tab]').forEach(button=>button.disabled=true);
    document.querySelectorAll('.page').forEach(page=>page.hidden=true);
    $('chainstate-panel').hidden=true;connection.onDisconnect?.();
  }
  function normalizeEndpoint(value){
    const url=new URL(value);
    if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/')
      throw new Error('Use the HTTPS origin of your Proof Grove backend, without a path or credentials.');
    return url.origin;
  }
  async function request(path,body,blob=false){
    if(!endpoint||!token)throw new Error('Connect an authenticated backend first.');
    if(!path.startsWith('/api/'))throw new Error('Unsupported backend route');
    let response;
    try{response=await fetch(endpoint+path,{method:body===undefined?'GET':'POST',mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',
      headers:{Authorization:'Bearer '+token,'Content-Type':'application/json','X-Proof-Grove':'1'},
      body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(path==='/api/proofs/check'||path==='/api/verify'?180_000:30_000)});}
    catch{throw new Error('Backend unreachable. Check its HTTPS address, allowed origin and service status.');}
    if(response.status===401){disconnect('Backend authentication failed. Reconnect with the operator token.');throw new Error('Backend authentication failed.');}
    if(!response.ok){let code='backend_request_failed';try{code=(await response.json()).error||code;}catch{}throw new Error(code);}
    return blob?response.blob():response.json();
  }
  const api=(path,body)=>request(path,body);api.archive=()=>request('/api/archive',undefined,true);
  globalThis.ProofGroveHosted=api;globalThis.ProofGroveConnection=connection;
  $('backend-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=$('connect-backend');button.disabled=true;
    try{
      endpoint=normalizeEndpoint($('backend-url').value.trim());token=$('backend-token').value;
      if(!/^[A-Za-z0-9_-]{43,128}$/.test(token))throw new Error('Enter the operator token generated on your backend.');
      const status=await api('/api/status');
      if(status.app!=='Proof Grove'||!['live','regtest'].includes(status.mode))throw new Error('A real live or regtest backend is required; fixture backends are refused.');
      connection.connected=true;await connection.onConnect?.();
      $('backend-form').hidden=true;$('backend-token').value='';$('disconnect-backend').hidden=false;
      $('backend-status').textContent='Connected to '+endpoint+' · '+status.mode+'. The token stays in this tab.';
      document.querySelectorAll('[data-tab]').forEach(button=>button.disabled=false);
      $('payments').hidden=false;
    }catch(error){disconnect(error.message);}
    finally{button.disabled=false;}
  });
  $('disconnect-backend').addEventListener('click',()=>disconnect());
  fetch(new URL('./backend-config.json',document.baseURI),{cache:'no-store'})
    .then(response=>response.json()).then(config=>{if(config.api_url)$('backend-url').value=normalizeEndpoint(config.api_url);})
    .catch(()=>{$('backend-status').textContent='Enter your backend HTTPS origin and operator token to connect.';});
  disconnect();
})();

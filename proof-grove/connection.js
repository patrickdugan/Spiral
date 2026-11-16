'use strict';
// Endpoint configuration is public. The operator token exists only in this tab.
(() => {
  const $=id=>document.getElementById(id);
  let endpoint='',token='',profiles=[],generation=0;
  const connection={connected:false,onConnect:null,onDisconnect:null};
  function disconnect(message='Disconnected. No backend data is being fetched.'){
    generation++;
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
    const started=generation;
    if(!endpoint||!token)throw new Error('Connect an authenticated backend first.');
    if(!path.startsWith('/api/'))throw new Error('Unsupported backend route');
    let response;
    try{response=await fetch(endpoint+path,{method:body===undefined?'GET':'POST',mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',
      headers:{Authorization:'Bearer '+token,'Content-Type':'application/json','X-Proof-Grove':'1'},
      body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(path.startsWith('/api/proofs/')||path==='/api/verify'?180_000:30_000)});}
    catch{throw new Error('Backend unreachable. Check its HTTPS address, allowed origin and service status.');}
    if(started!==generation)throw new Error('Backend connection changed; discard the previous response.');
    if(response.status===401){disconnect('Backend authentication failed. Reconnect with the operator token.');throw new Error('Backend authentication failed.');}
    if(!response.ok){let code='backend_request_failed';try{code=(await response.json()).error||code;}catch{}throw new Error(code);}
    const value=blob?await response.blob():await response.json();
    if(started!==generation)throw new Error('Backend connection changed; discard the previous response.');
    return value;
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
  $('backend-profile').addEventListener('change',event=>{
    disconnect();
    const profile=profiles.find(item=>item.id===event.target.value);
    if(profile){$('backend-url').value=profile.api_url;$('backend-status').textContent=profile.description;}
  });
  fetch(new URL('./backend-config.json',document.baseURI),{cache:'no-store'})
    .then(response=>response.json()).then(config=>{
      profiles=(config.profiles||[]).map(profile=>({...profile,api_url:normalizeEndpoint(profile.api_url)}));
      for(const profile of profiles){const option=document.createElement('option');option.value=profile.id;option.textContent=profile.label;$('backend-profile').append(option);}
      if(config.api_url)$('backend-url').value=normalizeEndpoint(config.api_url);
      const selected=profiles.find(profile=>profile.api_url===$('backend-url').value);
      if(selected){$('backend-profile').value=selected.id;$('backend-status').textContent=selected.description;}
    })
    .catch(()=>{$('backend-status').textContent='Enter your backend HTTPS origin and operator token to connect.';});
  disconnect();
})();

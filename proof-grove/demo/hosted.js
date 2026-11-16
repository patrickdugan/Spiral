'use strict';
// Only loaded by the static export. It never calls a wallet, mint or local node.
(() => {
  let current='cashu';
  const ready=fetch(new URL('./demo-data.json',document.baseURI),{cache:'no-store'})
    .then(response=>{if(!response.ok)throw new Error('Hosted demo data could not load');return response.json();});
  const clone=value=>structuredClone(value);
  async function api(path,body){
    const data=await ready;
    if(path==='/api/status')return clone(data.status);
    if(path==='/api/cases')return {cases:clone(data.cases),current:clone(data.runs[current])};
    if(path==='/api/vtxos')return clone(data.vtxos);
    if(path==='/api/sources')return clone(data.sources);
    if(path==='/api/run'){
      if(!Object.hasOwn(data.runs,body?.case))throw new Error('Unknown fixture case');
      current=body.case;return clone(data.runs[current]);
    }
    if(path==='/api/plan'){
      const plans=data.plans[String(body?.tip_height)];
      const plan=plans?.find(plan=>plan.id===body?.vtxo?.id);
      if(!plan)throw new Error('Choose a height within the fixture slider');
      return {plan:clone(plan),evidence_level:'fixture',executed:false};
    }
    if(path==='/api/archive/manifest')return clone(data.archives[current].manifest);
    if(path==='/api/ark/exits')return {exits:[],broadcast_enabled:false};
    if(['/api/cashu/info','/api/bark/history','/api/ark/wallet'].includes(path))return {evidence_level:'not-connected'};
    if(path==='/api/cashu/operations')return {operations:[]};
    throw new Error('This hosted fixture demo cannot sign, verify a native proof or connect to a wallet. Run the local app from GitHub.');
  }
  api.archive=async()=>new Blob([(await ready).archives[current].text],{type:'application/json'});
  globalThis.ProofGroveHosted=api;
})();

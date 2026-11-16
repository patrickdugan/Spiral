/* UI contract test with a deliberately mocked HTTPS backend; not proof QA. */
const {chromium}=require(process.env.PROOF_GROVE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const base=process.env.PROOF_GROVE_BASE||'http://127.0.0.1:8899/Spiral/proof-grove/';
  const browser=await chromium.launch({headless:true,executablePath:process.env.PROOF_GROVE_BROWSER||undefined});
  const checks=[],errors=[];let calls=0,failCore=false,backendMode='live';
  const token='a'.repeat(43);
  try{
    for(const width of [1440,390]){
      calls=0;failCore=false;backendMode='live';
      const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.route('https://backend.proof-grove.test/**',async route=>{
        const request=route.request(),url=new URL(request.url());
        const headers={'Access-Control-Allow-Origin':new URL(base).origin,'Access-Control-Allow-Headers':'Authorization,Content-Type,X-Proof-Grove','Access-Control-Allow-Methods':'GET,POST,OPTIONS'};
        if(request.method()==='OPTIONS'){await route.fulfill({status:204,headers,body:''});return;}
        calls++;assert.equal(request.headers().authorization,'Bearer '+token);
        let body,status=200;
        if(url.pathname==='/api/status')body={app:'Proof Grove',mode:backendMode,intents:[],ark_wallet_configured:false,hosted_access:{enabled:true,mutations:false}};
        else if(url.pathname==='/api/cases')body={cases:[],current:null};
        else if(url.pathname==='/api/vtxos')body={vtxos:[],plans:[]};
        else if(url.pathname==='/api/sources')body={integrations:[],sources:[]};
        else if(url.pathname==='/api/chainstate'){
          status=failCore?503:200;body=failCore?{error:'upstream_unavailable'}:{network:'testnet4',blocks:161597,observed_at:1794790000,initialblockdownload:false,evidence_level:'bitcoin-core'};
        }else if(url.pathname==='/api/proofs/recorded')body={name:'Explicit UI mock record',statement_sha256:'1'.repeat(64),proof_sha256:'2'.repeat(64)};
        else if(url.pathname==='/api/proofs/recorded/check')body={proof_verified:true,payment_admitted:false,chain_observation:{source:'bitcoin-core'},evidence:{value_sats:11600}};
        else{status=404;body={error:'unsupported_mock_route'};}
        await route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
      });
      await page.goto(base,{waitUntil:'networkidle'});
      assert.equal(calls,0);assert.equal(await page.locator('#payments').isVisible(),false);
      assert.equal(await page.locator('#run-case').isVisible(),false);
      await page.fill('#backend-url','https://backend.proof-grove.test');await page.fill('#backend-token',token);await page.click('#connect-backend');
      await page.waitForFunction(()=>document.getElementById('chainstate-status').textContent.includes('161,597'));
      await page.locator('#payments').waitFor({state:'visible'});
      assert.equal(await page.locator('#payments').isVisible(),true);assert.equal(await page.locator('#demo-controls').isVisible(),false);
      assert.equal(await page.locator('#backend-token').inputValue(),'');
      await page.click('#check-recorded-proof');await page.waitForFunction(()=>document.getElementById('decision-label').textContent==='NATIVE M16 PROOF VERIFIED');
      assert.match(await page.locator('#decision-detail').textContent(),/does not admit a payment/);
      failCore=true;await page.click('#refresh-chainstate');
      await page.waitForFunction(()=>document.getElementById('chainstate-status').textContent.includes('unavailable'));
      assert.doesNotMatch(await page.locator('#decision-label').textContent(),/FIXTURE/);
      await page.click('#disconnect-backend');assert.equal(await page.locator('#payments').isVisible(),false);
      assert.equal(await page.locator('#raw-evidence').textContent(),'');
      assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length})),{local:0,session:0});
      backendMode='demo';await page.fill('#backend-token',token);await page.click('#connect-backend');
      await page.waitForFunction(()=>document.getElementById('backend-status').textContent.includes('fixture backends are refused'));
      assert.equal(await page.locator('#payments').isVisible(),false);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      checks.push({width,authenticated_reads:true,fixture_backend_refused:true,proof_check_ui:true,outage_not_fixtures:true,token_not_persisted:true,no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);
    const report={status:'passed',backend:'mocked HTTPS UI contract only',checks,javascript_errors:errors};
    fs.writeFileSync(path.resolve('docs/connected-hosting-browser-check.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

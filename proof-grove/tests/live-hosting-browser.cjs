/* Actual Pages + public HTTPS services. Owner token stays in process/tab memory.
 * No route mocks, browser storage, token URLs, or screenshots of credentials.
 */
const {chromium}=require(process.env.PROOF_GROVE_PLAYWRIGHT||'playwright');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const base=process.env.PROOF_GROVE_BASE||'https://patrickdugan.github.io/Spiral/proof-grove/';
  const token=process.env.PROOF_GROVE_DESK_TOKEN||execFileSync('ssh',['-o','BatchMode=yes','tradelayer-witness',
    'cat /opt/proof-grove/config/operator.env'],{encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim().split('=',2)[1];
  assert.match(token,/^[A-Za-z0-9_-]{43,128}$/);
  const browser=await chromium.launch({headless:true,executablePath:process.env.PROOF_GROVE_BROWSER||undefined});
  const checks=[],errors=[];
  try{
    for(const width of [1440,390]){
      const context=await browser.newContext({viewport:{width,height:1000}});
      const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
      await page.goto(base,{waitUntil:'networkidle'});
      await page.locator('#backend-profile option[value="regtest"]').waitFor({state:'attached'});
      const connect=async profile=>{
        await page.selectOption('#backend-profile',profile);
        await page.fill('#backend-token',token);await page.click('#connect-backend');
        await page.locator('#backend-form').waitFor({state:'hidden',timeout:180000});
        assert.equal(await page.locator('#backend-token').inputValue(),'');
      };
      await connect('testnet4');
      assert.match(await page.locator('#chainstate-status').textContent(),/testnet4.*block/);
      await page.click('#check-recorded-proof');
      await page.waitForFunction(()=>document.getElementById('decision-label').textContent==='NATIVE M16 PROOF VERIFIED',null,{timeout:180000});
      assert.match(await page.locator('#decision-detail').textContent(),/does not admit a payment/);
      const testnet4=await page.locator('#chainstate-status').textContent();
      await page.screenshot({path:'.runtime/live-testnet4-'+width+'.png',fullPage:true});
      await page.click('#disconnect-backend');await connect('regtest');
      assert.match(await page.locator('#chainstate-status').textContent(),/regtest.*block/);
      assert.equal(await page.locator('#proof-files').isVisible(),false);
      assert.equal(await page.locator('#check-recorded-proof').isVisible(),false);
      await page.click('[data-tab="caretaker"]');await page.click('#load-ark');
      await page.waitForFunction(()=>/regtest.*Core block/.test(document.getElementById('ark-wallet-status').textContent),null,{timeout:60000});
      assert.match(await page.locator('#ark-wallet-status').textContent(),/regtest.*Core block/);
      assert.ok(await page.locator('#vtxo-table tr').count()>0);
      assert.match(await page.locator('#vtxo-table').textContent(),/Anchor confirmed/);
      const ark=await page.locator('#ark-wallet-status').textContent();
      await page.screenshot({path:'.runtime/live-ark-'+width+'.png',fullPage:true});
      await page.click('[data-tab="evidence"]');await page.click('#read-cashu');
      await page.waitForFunction(()=>document.getElementById('provider-report').textContent.toLowerCase().includes('cdk'),null,{timeout:60000});
      assert.doesNotMatch(await page.locator('#provider-report').textContent(),/not-connected/);
      await page.click('#disconnect-backend');await connect('testnet4');
      assert.equal(await page.locator('#proof-files').isVisible(),true);
      assert.equal(await page.locator('#regtest-fields').isVisible(),false);
      assert.equal(await page.locator('#ark-connection').isVisible(),false);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.click('#disconnect-backend');
      assert.deepEqual(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length})),{local:0,session:0});
      checks.push({width,testnet4,ark,actual_native_proof:true,actual_cashu_provider:true,actual_core_anchors:true,
        profile_reconnect_resets_controls:true,credential_persisted:false,no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);
    const report={status:'passed',tested_at:new Date().toISOString(),url:base,backend:'actual public HTTPS services; no route mocks',checks,javascript_errors:errors};
    fs.writeFileSync('docs/live-hosting-browser-check.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

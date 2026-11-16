const {chromium}=require(process.env.PROOF_GROVE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.PROOF_GROVE_BROWSER||undefined});
  const errors=[],checks=[],output=path.resolve('.runtime/ark-browser');fs.mkdirSync(output,{recursive:true});
  try{
    for(const width of [1440,390]){
      const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.goto(process.env.PROOF_GROVE_BASE,{waitUntil:'networkidle'});
      await page.waitForFunction(()=>document.getElementById('mode-badge').textContent.includes('REGTEST'));
      await page.click('[data-tab=caretaker]');await page.click('#load-ark');
      await page.waitForFunction(()=>document.getElementById('ark-wallet-status').textContent.includes('Core block'));
      assert.match(await page.locator('#vtxo-table').textContent(),/Anchor confirmed/);
      assert.equal(await page.locator('#ark-refresh-form').isVisible(),true);
      await page.waitForFunction(()=>document.getElementById('ark-operation').textContent.includes('confirmed'));
      if(process.env.PROOF_GROVE_TEST_RECONCILE==='1'){
        await page.click('#ark-reconcile');
        await page.waitForFunction(()=>document.getElementById('ark-operation').textContent.includes('actual_fee_sats'));
      }
      assert.equal(await page.locator('#app-error').isVisible(),false);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:path.join(output,`ark-${width}.png`),fullPage:true});
      checks.push({width,real_bark_vtxos:true,core_anchors:true,saved_refresh_visible:true,reconciled:process.env.PROOF_GROVE_TEST_RECONCILE==='1',no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);
    const result={status:'passed',checks,javascript_errors:errors};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

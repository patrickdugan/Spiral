const { chromium }=require(process.env.PROOF_GROVE_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.PROOF_GROVE_BROWSER||undefined});
  const errors=[],report=[];const output=path.resolve('.runtime/connected-browser');fs.mkdirSync(output,{recursive:true});
  try{
    for(const width of [1440,390]){
      const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}),page=await context.newPage();
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(process.env.PROOF_GROVE_BASE,{waitUntil:'networkidle'});
      await page.waitForFunction(()=>document.getElementById('mode-badge').textContent.includes('REGTEST'));
      assert.equal(await page.locator('#proof-files').isVisible(),false);
      assert.equal(await page.locator('#regtest-fields').isVisible(),true);
      await page.selectOption('#intent-select',process.env.PROOF_GROVE_TEST_INTENT);
      await page.fill('#regtest-txid',process.env.PROOF_GROVE_TEST_TXID);await page.fill('#regtest-vout',process.env.PROOF_GROVE_TEST_VOUT);
      await page.locator('#live-controls button').click();
      await page.waitForFunction(()=>document.getElementById('decision-label').textContent==='CORE REGTEST CHECK ACCEPTED');
      await page.waitForFunction(()=>document.getElementById('metric-state').textContent==='Signatures returned');
      assert.match(await page.locator('#steps').textContent(),/not a ZK proof/);
      await page.screenshot({path:path.join(output,`connected-${width}.png`),fullPage:true});
      await page.click('[data-tab=evidence]');await page.click('#read-issuance');
      await page.waitForFunction(()=>document.getElementById('provider-report').textContent.includes('signatures_received'));
      const downloadPromise=page.waitForEvent('download');await page.click('#download-archive');
      const download=await downloadPromise;await download.saveAs(path.join(output,`receipt-${width}.json`));
      assert.equal(await page.locator('#app-error').isVisible(),false);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      report.push({width,actual_regtest_admission:true,issuance_state_visible:true,archive_download:true,no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);
    const result={status:'passed',checks:report,javascript_errors:errors,evidence:'Real isolated regtest stack; not M16/ZK'};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

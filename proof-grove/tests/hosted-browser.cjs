/* Static hosting QA: a real /Spiral/proof-grove/ subpath, no local API. */
const {chromium}=require(process.env.PROOF_GROVE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');

(async()=>{
  const base=process.env.PROOF_GROVE_BASE||'http://127.0.0.1:8899/Spiral/proof-grove/';
  const browser=await chromium.launch({headless:true,executablePath:process.env.PROOF_GROVE_BROWSER||undefined});
  const errors=[],requests=[],checks=[];
  const output=path.resolve('.runtime/hosted-browser');fs.mkdirSync(output,{recursive:true});
  try{
    for(const width of [1440,390]){
      const context=await browser.newContext({viewport:{width,height:width===390?844:1100},reducedMotion:'reduce'});
      const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
      page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
      page.on('request',request=>requests.push(request.url()));
      await page.goto(base,{waitUntil:'networkidle'});
      await page.locator('#case-select option').first().waitFor({state:'attached'});
      assert.equal(await page.locator('#case-select option').count(),8);
      assert.match(await page.locator('#mode-notice').textContent(),/Hosted fixture demo/);
      for(const [id,code] of [['cashu',null],['ark',null],['replay','deposit_script_reused'],['wrong-amount','wrong_amount'],['wrong-script','wrong_payment_script'],['reorg','payment_reorged'],['stale','chain_view_stale'],['operator-report','demo_namespace_required']]){
        await page.selectOption('#case-select',id);await page.click('#run-case');
        if(code)await page.waitForFunction(code=>JSON.parse(document.getElementById('receipt-json').textContent).code===code,code);
        else await page.waitForFunction(()=>document.getElementById('decision-label').textContent==='FIXTURE ACCEPTED');
      }
      await page.selectOption('#case-select','cashu');await page.click('#run-case');
      await page.waitForFunction(()=>document.getElementById('decision-label').textContent==='FIXTURE ACCEPTED');
      await page.click('#inspect-receipt');assert.equal(await page.locator('#receipt-dialog').evaluate(node=>node.open),true);await page.keyboard.press('Escape');
      await page.screenshot({path:path.join(output,`payments-${width}.png`),fullPage:true});
      await page.click('[data-tab="caretaker"]');
      await page.locator('#tip-slider').evaluate(node=>{node.value='1380';node.dispatchEvent(new Event('input',{bubbles:true}));});
      await page.waitForFunction(()=>document.getElementById('height-readout').textContent==='Block 1,380');
      await page.waitForFunction(()=>[...document.querySelectorAll('#vtxo-table tr')].every(row=>row.textContent.includes('20 blocks')||row.textContent.includes('-260 blocks')||row.textContent.includes('-320 blocks')));
      assert.equal(await page.locator('#ark-connection').isVisible(),false);
      assert.equal(await page.locator('#exit-recovery').isVisible(),false);
      await page.screenshot({path:path.join(output,`caretaker-${width}.png`),fullPage:true});
      await page.click('[data-tab="evidence"]');await page.waitForFunction(()=>document.getElementById('cid-field').value.startsWith('bafk'));
      const downloadPromise=page.waitForEvent('download');await page.click('#download-archive');const download=await downloadPromise;
      const saved=await download.path();const raw=fs.readFileSync(saved);const digest=crypto.createHash('sha256').update(raw).digest('hex');
      const data=await page.evaluate(async()=>fetch('./demo-data.json').then(r=>r.json()));
      assert.equal(digest,data.archives.cashu.manifest.sha256);
      assert.equal(await page.locator('#cid-field').inputValue(),data.archives.cashu.manifest.cid);
      const report=await page.evaluate(async()=>fetch('./results/cashu-ark-integration.json').then(r=>r.json()));
      assert.equal(report.status,'passed');assert.equal(report.unilateral_exit_tested,true);
      await page.screenshot({path:path.join(output,`evidence-${width}.png`),fullPage:true});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      checks.push({width,cases:8,planner:true,archive_sha256_verified:true,public_report:true,no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);assert.equal(requests.some(url=>new URL(url).pathname.startsWith('/api/')),false);
    const report={status:'passed',base,checks,javascript_errors:errors,local_api_requests:0};
    fs.writeFileSync(path.resolve('docs/hosted-browser-check.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

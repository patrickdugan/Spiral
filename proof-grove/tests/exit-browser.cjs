const {chromium}=require(process.env.PROOF_GROVE_PLAYWRIGHT||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.PROOF_GROVE_BROWSER||undefined});
  const errors=[],checks=[],output=path.resolve('.runtime/exit-browser');fs.mkdirSync(output,{recursive:true});
  try{
    for(const width of [1440,390]){
      const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}),page=await context.newPage();
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto(process.env.PROOF_GROVE_BASE,{waitUntil:'networkidle'});
      await page.waitForFunction(()=>document.getElementById('mode-badge').textContent.includes('REGTEST'));
      await page.click('[data-tab=caretaker]');
      assert.equal(await page.locator('#ark-connection').isVisible(),false);
      await page.click('#load-exits');
      await page.waitForFunction(()=>!document.getElementById('exit-saved').hidden);
      assert.equal(await page.locator('#exit-id').textContent(),process.env.PROOF_GROVE_EXIT_ID);
      assert.equal(await page.locator('#broadcast-exit').isVisible(),false);
      const downloadPromise=page.waitForEvent('download');await page.click('#download-exit');
      const download=await downloadPromise,file=path.join(output,`private-exit-${width}.json`);await download.saveAs(file);
      const raw=fs.readFileSync(file),body=JSON.parse(raw.toString('utf8'));
      assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),process.env.PROOF_GROVE_EXIT_ID);
      assert.equal(body.schema,'proof-grove/ark-exit/v1');
      assert.equal(body.network,'regtest');
      for(const forbidden of ['mnemonic','private_key','cashu_token','password','Authorization'])assert.equal(raw.includes(Buffer.from('"'+forbidden+'"')),false);
      const checkResponse=page.waitForResponse(response=>response.url().endsWith('/api/ark/exits/advance') && response.request().method()==='POST');
      await page.click('#check-exit');
      assert.equal((await (await checkResponse).json()).state,'target_spent');
      await page.waitForFunction(()=>document.getElementById('exit-state').textContent.includes('exit output is spent'));
      assert.equal(await page.locator('#app-error').isVisible(),false);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:path.join(output,`recovery-${width}.png`),fullPage:true});
      checks.push({width,core_only_dashboard:true,private_download_hash_matches:true,spent_output_rechecked:true,no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);
    const report={status:'passed',checks,javascript_errors:errors};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

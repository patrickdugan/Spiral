/* Uses a supplied Playwright installation; no package installation is needed.
 * Set PROOF_GROVE_PLAYWRIGHT and optionally PROOF_GROVE_BROWSER / PROOF_GROVE_BASE.
 */
const { chromium } = require(process.env.PROOF_GROVE_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.PROOF_GROVE_BROWSER || undefined});
  const errors = [];
  const output = path.resolve('.runtime/browser'); fs.mkdirSync(output, {recursive: true});
  const summary = [];
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({ viewport: {width, height: width === 390 ? 844 : 1100}, reducedMotion: 'reduce' });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if(message.type() === 'error') errors.push(message.text()); });
      await page.goto(process.env.PROOF_GROVE_BASE || 'http://127.0.0.1:8765', {waitUntil:'networkidle'});
      await page.locator('#case-select option').first().waitFor({state:'attached'});
      await page.selectOption('#case-select','cashu');
      await page.click('#run-case');
      await page.waitForFunction(() => document.getElementById('decision-label').textContent === 'FIXTURE ACCEPTED');
      await page.screenshot({path:path.join(output,`payments-${width}.png`), fullPage:true});
      await page.click('#inspect-receipt');
      assert.equal(await page.locator('#receipt-dialog').evaluate(node=>node.open), true);
      assert.match(await page.locator('#receipt-json').textContent(), /"state": "prepared"/);
      await page.keyboard.press('Escape');
      const cases = [['replay','deposit_script_reused'],['wrong-amount','wrong_amount'],['wrong-script','wrong_payment_script'],['reorg','payment_reorged'],['stale','chain_view_stale'],['operator-report','demo_namespace_required']];
      for (const [id, code] of cases) {
        await page.selectOption('#case-select',id);
        const responsePromise = page.waitForResponse(response=>response.url().endsWith('/api/run') && response.request().method()==='POST');
        await page.click('#run-case'); const response = await responsePromise;
        assert.equal((await response.json()).decision.code, code);
        await page.waitForFunction(() => document.getElementById('decision-label').textContent === 'FIXTURE REJECTED');
      }
      await page.selectOption('#case-select','cashu');
      await page.click('#run-case');
      await page.waitForFunction(() => document.getElementById('decision-label').textContent === 'FIXTURE ACCEPTED');
      await page.click('[data-tab=caretaker]');
      assert.equal(await page.locator('#vtxo-table tr').count(),3);
      assert.match(await page.locator('#vtxo-table').textContent(),/delegate exit/);
      await page.locator('#tip-slider').fill('1380');
      await page.waitForFunction(() => document.getElementById('vtxo-table').textContent.includes('urgent'));
      await page.screenshot({path:path.join(output,`caretaker-${width}.png`),fullPage:true});
      await page.click('[data-tab=evidence]');
      await page.waitForFunction(() => document.getElementById('cid-field').value.startsWith('bafkrei'));
      const downloadPromise = page.waitForEvent('download'); await page.click('#download-archive');
      const download = await downloadPromise; const file = path.join(output,`receipts-${width}.json`); await download.saveAs(file);
      const exported = JSON.parse(fs.readFileSync(file,'utf8'));
      assert.equal(exported.schema,'proof-grove/public-receipts/v1');
      assert.equal(exported.receipts.length,1);
      assert.equal(exported.receipts[0].state,'prepared');
      assert.equal('beneficiary' in exported.receipts[0],false);
      await page.click('#read-cashu'); await page.waitForFunction(() => document.getElementById('provider-report').textContent.includes('not-connected'));
      await page.screenshot({path:path.join(output,`evidence-${width}.png`),fullPage:true});
      const overflowing = await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth);
      assert.equal(overflowing,false,'Page overflows viewport');
      assert.equal(await page.locator('.app-error:visible').count(),0);
      summary.push({width,cases:8,dialog:true,planner:true,download:true,no_horizontal_overflow:true});
      await context.close();
    }
    assert.deepEqual(errors,[]);
    const report = {status:'passed', checks:summary, javascript_errors:errors};
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

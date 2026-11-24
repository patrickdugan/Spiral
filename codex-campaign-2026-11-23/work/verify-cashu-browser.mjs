import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const profile = await fs.mkdtemp(path.resolve('work/cashu-browser-'));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--disable-background-networking',
  '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], {windowsHide: true, stdio: 'ignore'});

async function until(read, timeout = 15000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    try {
      const result = await read();
      if (result) return result;
    } catch (error) { last = error; }
    await sleep(120);
  }
  throw new Error('Browser check timed out', {cause: last});
}

let socket;
try {
  const devTools = await until(() => fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8'));
  const endpoint = 'http://127.0.0.1:' + devTools.trim().split('\n')[0].trim();
  const tabs = await (await fetch(endpoint + '/json/list')).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once: true});
    socket.addEventListener('error', reject, {once: true});
  });
  const requests = new Map();
  let id = 0;
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!requests.has(message.id)) return;
    const {resolve, reject} = requests.get(message.id);
    requests.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
  });
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    requests.set(++id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await cdp('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description);
    return result.result.value;
  };
  const verified = [];
  for (const width of [1440, 390]) {
    const downloadPath = path.join(profile, 'downloads-' + width);
    await fs.mkdir(downloadPath);
    await cdp('Page.setDownloadBehavior', {behavior:'allow', downloadPath});
    await cdp('Emulation.setDeviceMetricsOverride', {
      width, height: width === 390 ? 844 : 1000, deviceScaleFactor: 1, mobile: false,
    });
    await cdp('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion', value:'reduce'}]});
    await cdp('Page.navigate', {url: `http://127.0.0.1:8766/?viewport=${width}#zk`});
    try {
      await until(() => evaluate("document.querySelector('#zk-pair')?.hidden === false && !document.querySelector('#zk').hidden"));
    } catch (error) {
      console.log(await evaluate("({url:location.href,title:document.title,status:document.querySelector('#zk-record-status')?.textContent,error:document.querySelector('#app-error')?.textContent})"));
      throw error;
    }
    const evidence = await evaluate("(async () => { const find=id=>document.getElementById(id); find('zk-source').open=true; const r=await fetch(find('zk-source-link').href); const bytes=await r.arrayBuffer(); const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join(''); return {sha, displayed:find('zk-source-hash').textContent, issuance:find('zk-issue').textContent, payout:find('zk-redeem').textContent, overflows:document.documentElement.scrollWidth>innerWidth}; })()");
    assert.match(evidence.issuance, /25,000 sats/);
    assert.match(evidence.payout, /24,750 sats/);
    assert.equal(evidence.sha, evidence.displayed);
    const capture = await cdp('Page.captureScreenshot', {format:'png'});
    await fs.writeFile(path.join(profile, 'cashu-'+width+'.png'), Buffer.from(capture.data,'base64'));
    if (evidence.overflows) console.log(await evaluate("[...document.querySelectorAll('body *')].map(x=>({el:x.tagName,id:x.id,className:typeof x.className==='string'?x.className:'',right:x.getBoundingClientRect().right,width:x.getBoundingClientRect().width})).filter(x=>x.right>innerWidth+1).slice(0,15)"));
    assert.equal(evidence.overflows, false);
    await evaluate("document.getElementById('zk-download').click(); true");
    const saved = await until(() => fs.readFile(path.join(downloadPath, 'proof-grove-paired-regtest-evidence.json'), 'utf8'));
    assert.equal(JSON.parse(saved).source_receipt_sha256, evidence.sha);
    await evaluate("document.getElementById('zk-try-replay').click(); true");
    await until(() => evaluate("JSON.parse(document.getElementById('receipt-json').textContent).code === 'deposit_script_reused'"));
    verified.push({width, receipt_sha256: evidence.sha, replay_rejected: true});
  }
  console.log(JSON.stringify(verified));
  await Promise.race([cdp('Browser.close'), sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}

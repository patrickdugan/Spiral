import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import {setTimeout as sleep} from 'node:timers/promises';

const profile = await fs.mkdtemp(path.resolve('work/cashu-portable-browser-'));
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

  const site = pathToFileURL(path.resolve('outputs/Proof-Grove-Melt-Funded-Reserve.html'));
  const external = [];
  await cdp('Network.enable');
  socket.addEventListener('message', event=>{
    const message=JSON.parse(event.data);
    if(message.method==='Network.requestWillBeSent' && /^https?:/.test(message.params.request.url)) {
      external.push(message.params.request.url);
    }
  });
  await cdp('Network.emulateNetworkConditions', {offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
  const verified=[];
  for (const width of [1440,390]) {
    const destination=path.join(profile,'offline-'+width);
    await fs.mkdir(destination);
    await cdp('Page.setDownloadBehavior',{behavior:'allow',downloadPath:destination});
    await cdp('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:1000,deviceScaleFactor:1,mobile:false});
    site.searchParams.set('viewport',width);
    await cdp('Page.navigate',{url:site.href});
    await until(()=>evaluate("document.querySelector('#zk-pair')?.hidden===false && !document.querySelector('#zk').hidden"));
    const shown=await evaluate("({issue:document.querySelector('#zk-issue').textContent,payout:document.querySelector('#zk-redeem').textContent,hash:document.querySelector('#zk-source-hash').textContent,source:document.querySelector('#zk-source-link').href,download:document.querySelector('#zk-source-link').download})");
    assert.match(shown.issue,/25,000 sats/);
    assert.match(shown.payout,/24,750 sats/);
    assert.match(shown.source,/^blob:/);
    assert.match(shown.download,/^cashu-shinigami-paired-benchmark-20261123[.]json$/);
    await evaluate("document.querySelector('#zk-source').open=true; document.querySelector('#zk-source-link').click(); true");
    const receipt=await until(()=>fs.readFile(path.join(destination,shown.download)));
    assert.equal(createHash('sha256').update(receipt).digest('hex'),shown.hash);
    await evaluate("document.querySelector('#zk-download').click(); true");
    const summary=JSON.parse(await until(()=>fs.readFile(path.join(destination,'proof-grove-paired-regtest-evidence.json'),'utf8')));
    assert.equal(summary.source_receipt_sha256,shown.hash);
    assert.equal(summary.live_verification,false);
    assert.equal(summary.shared_claim_consumption_enforced,false);
    const melt=await evaluate("({shown:!document.querySelector('#zk-melt-reserve').hidden,funding:document.querySelector('#zk-melt-funding').textContent,payout:document.querySelector('#zk-melt-payout').textContent,file:document.querySelector('#zk-melt-source').download})");
    assert.ok(melt.shown);
    assert.match(melt.funding,/24,000 sats.*all 6 source proofs spent/);
    assert.match(melt.payout,/23,750 sats.*6 blocks.*250-sat payout fee/);
    assert.equal(melt.file,'cashu-melt-funded-reserve-regtest.json');
    await evaluate("document.querySelector('#zk-melt-source').click(); true");
    const meltBytes=await until(()=>fs.readFile(path.join(destination,melt.file)));
    assert.equal(createHash('sha256').update(meltBytes).digest('hex'),summary.melt_funded_reserve.source_receipt_sha256);
    assert.equal(await evaluate("document.documentElement.scrollWidth>innerWidth"),false);
    await evaluate("document.querySelector('#zk-try-replay').click(); true");
    await until(()=>evaluate("JSON.parse(document.querySelector('#receipt-json').textContent).code==='deposit_script_reused'"));
    verified.push({width, receiptSha256:shown.hash, replayRejected:true});
  }
  assert.deepEqual(external,[]);
  console.log(JSON.stringify({verified,externalRequests:external.length}));
  await Promise.race([cdp('Browser.close'),sleep(1000)]);
} finally {
  socket?.close();
  if (chrome.exitCode === null) chrome.kill();
}

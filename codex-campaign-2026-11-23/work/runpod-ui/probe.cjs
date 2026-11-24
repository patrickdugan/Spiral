const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {execFile} = require('node:child_process');

const staging = __dirname;
const fixturePath = path.join(staging, 'fixture.html');
const original = fs.readFileSync(path.join(staging, 'index.html'), 'utf8');
const fixture = original.replace('/styles.css', 'styles.css').replace('/app.js', 'app.js').replace('</head>', `<script>
const $ = id => document.getElementById(id);
const wallClock = Date.now.bind(Date);
let offset = 0;
Date.now = () => wallClock() + offset;
const requests = [];
let available = true;
const seeded = location.search === '?saved';
localStorage.clear();
if (seeded) {
  localStorage.setItem('rbzk.compute.target', 'cloud');
  localStorage.setItem('rbzk.compute.provider', 'hyperstack');
}
window.fetch = async (route, options) => {
  requests.push([route, options?.method ?? 'GET']);
  if (route === '/api/live') return {ok: true, json: async () => ({
    sampled_at_unix: Date.now() / 1000,
    gpu: {available, name:'Fixture RTX GPU', util_gpu_pct:0, vram_used_mib:null, vram_total_mib:16384, temp_c:51},
  })};
  if (route === '/api/campaigns') return {ok: true, json: async () => ({campaigns: []})};
  throw Error('Unexpected request: ' + route);
};
const wait = () => new Promise(resolve => setTimeout(resolve, 100));
document.addEventListener('DOMContentLoaded', async () => {
  const details = $('compute-provider-detail');
  const cloud = $('compute-cloud');
  const select = (name, value) => document.querySelector('input[name="' + name + '"][value="' + value + '"]').click();
  const assert = (ok, label) => {if (!ok) throw Error(label);};
  const assertText = (node, text) => assert(node.textContent.includes(text), 'missing ' + text);
  try {
    await wait();
    assert($('compute-panel').hidden, 'Compute panel initially visible');
    $('compute-tab').click();
    assert(!$('compute-panel').hidden && $('eta-panel').hidden, 'Compute tab failed to switch');
    assert($('compute-tab').getAttribute('aria-selected') === 'true', 'selected tab state');
    assertText($('local-gpu-name'), 'Fixture RTX GPU');
    assertText($('local-gpu-metrics'), '0%');
    assertText($('local-gpu-metrics'), '16 GiB');
    assertText($('local-gpu-metrics'), 'Unavailable');
    assertText($('local-gpu-metrics'), '51 °C');
    assertText($('local-gpu-status'), 'OBSERVED');
    if (seeded) {
      assert(!cloud.hidden, 'Cloud selection was not restored');
      assertText(details, 'n3-H100-SXM5x8');
      assert(document.querySelector('input[name="compute-provider"]:checked').value === 'hyperstack', 'saved provider was not checked');
    } else {
      assert(cloud.hidden, 'Local should be the initial target');
      select('compute-target', 'cloud');
      assert(!cloud.hidden && details.hidden, 'cloud initially should prompt for provider');
      assertText(cloud, '$4.39/GPU-hr');
      assertText(cloud, '$3.20/GPU-hr');
      select('compute-provider', 'runpod');
      assertText(details, 'runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404');
      assertText(details, '120 GB network volume');
      assert(details.querySelector('a').hostname === 'console.runpod.io', 'Runpod console URL');
      select('compute-provider', 'hyperstack');
      assertText(details, 'n3-H100-SXM5x8');
      assertText(details, 'eight GPUs');
      assert(details.querySelector('a').hostname === 'console.hyperstack.cloud', 'Hyperstack console URL');
      assert(localStorage.getItem('rbzk.compute.target') === 'cloud', 'target persistence');
      assert(localStorage.getItem('rbzk.compute.provider') === 'hyperstack', 'provider persistence');
      select('compute-target', 'local');
      assert(cloud.hidden, 'switching back to local should collapse choices');
      select('compute-target', 'cloud');
      assert(!details.hidden, 'provider choice should survive local/cloud switch');
    }
    offset = 16000;
    $('compute-tab').click();
    assertText($('local-gpu-status'), 'STALE / UNKNOWN');
    assert(!$('local-gpu-metrics').textContent.includes('16 GiB'), 'stale VRAM was shown');
    $('toggle-poll').click();
    assertText($('local-gpu-status'), 'DISPLAY PAUSED');
    available = false;
    $('toggle-poll').click();
    await wait();
    assertText($('local-gpu-status'), 'UNAVAILABLE');
    assert(requests.every(([route, method]) => ['/api/live','/api/campaigns'].includes(route) && method === 'GET'), 'unexpected fetch on selection');
    document.body.setAttribute('data-probe', 'passed');
  } catch (error) {
    document.body.setAttribute('data-probe', error.message);
  }
});
</script></head>`);
fs.writeFileSync(fixturePath, fixture);

function run(query) {
  return new Promise((resolve,reject)=>{
    const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
    const args = ['--headless=new', '--disable-gpu', '--disable-background-networking', '--no-first-run',
      '--disable-extensions', '--disable-sync', '--virtual-time-budget=800', '--dump-dom',
      '--user-data-dir=' + path.join(staging, 'edge-fixture'), pathToFileURL(fixturePath).href + query];
    execFile(edge, args, {windowsHide: true, timeout: 20000}, (error, output, stderr)=>{
      if (error) return reject(new Error(stderr || error.message));
      const result = output.match(/<body[^>]*data-probe="([^"]+)"/)?.[1];
      if (result !== 'passed') return reject(new Error(result || output.slice(0,1000) || stderr || 'No browser result'));
      console.log(query ? 'Saved target and provider restored' : 'Compute tab, choices, prices, details, live and unavailable telemetry, and read-only polling');
      resolve();
    });
  });
}

run('').then(()=>run('?saved')).catch(error=>{console.error(error);process.exitCode=1;});

const fs = require('node:fs');
const path = require('node:path');
const {execFile} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const root = __dirname;
const source = fs.readFileSync(path.join(root,'web/index.html'), 'utf8');
const variant = source.replace('/styles.css', 'web/styles.css').replace('/app.js', 'web/app.js').replace('</head>', `<script>
const find = id => document.getElementById(id);
let timeSkew = 0;
const realTime = Date.now.bind(Date);
Date.now = () => realTime() + timeSkew;
const now = Math.floor(realTime() / 1000);
const terminal = location.search.includes('terminal');
window.fetch = async route => ({ok:true,json:async () => route === '/api/live' ? {
  sampled_at_unix: now,
  gpu:{available:true,name:'Fixture RTX 5080',util_gpu_pct:0},
  cloud_hyperstack:{vm_id:4321,stage:terminal?'verified':'prove',active:!terminal,a100_confirmed:true,
    sampled_at_unix:now,started_at_unix:now-600,threads:16,logical_cpus:28,rate_usd_per_hour:1.356,
    host_ram_gib:120,host_ram_used_gib:35,prove_seconds:terminal?460:undefined,peak_prove_ram_gib:22}
} : {campaigns:[]}});
const requireText = (id, text) => {
  if (!find(id).textContent.includes(text)) throw Error(id + ' did not contain ' + text);
};
document.addEventListener('DOMContentLoaded', () => setTimeout(() => {
  try {
    find('compute-tab').click();
    requireText('hyperstack-hardware','NVIDIA A100 80 GB PCIe');
    requireText('hyperstack-metrics','16 prover / 28 host');
    requireText('hyperstack-metrics','35 / 120 GiB');
    requireText('hyperstack-stage',terminal?'Issuance verified':'Generating issuance proof');
    requireText('hardware-ribbon',terminal?'Fixture RTX 5080':'HYPERSTACK · CPU PROVING');
    if (terminal) {
      requireText('hyperstack-metrics','00:07:40');
      find('cashu-tab').click();
      requireText('cashu-benchmark','A fresh redemption proof is pending.');
    } else {
      timeSkew = 60000;
      find('compute-tab').click();
      requireText('hyperstack-stage','Telemetry stale');
      requireText('hardware-ribbon','Fixture RTX 5080');
    }
    document.body.dataset.probe = 'passed';
  } catch (error) {
    document.body.dataset.probe = error.message;
  }
}, 100));
</script></head>`);
const fixtureFile=path.join(root,'hyperstack-fixture.html');
fs.writeFileSync(fixtureFile, variant);
const edge='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
function check(query) {
  return new Promise((resolve, reject) => execFile(edge, [
    '--headless=new','--disable-gpu','--disable-background-networking','--no-first-run',
    '--disable-extensions','--disable-sync','--virtual-time-budget=900','--dump-dom',
    '--user-data-dir=' + path.join(root,'edge-fixture'),pathToFileURL(fixtureFile).href + query,
  ], {windowsHide:true, timeout:20000}, (error, output) => {
    if (error) return reject(error);
    const result=output.match(/<body[^>]*data-probe="([^"]+)"/)?.[1];
    if (result !== 'passed') return reject(Error(result || 'No browser result'));
    resolve();
  }));
}
(async() => {
  await check('');
  await check('?terminal');
  console.log('Hyperstack source selection, stale fallback, benchmark metrics and separate redemption milestone passed');
})().catch(error=>{console.error(error.message);process.exitCode=1;});

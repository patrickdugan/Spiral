// An explicitly recorded manual trigger, not an observation of the 2h scheduler.
// No protobuf dependency: upstream TriggerSweep accepts/returns core.Empty.
import http2 from 'node:http2';
import { existsSync, writeFileSync } from 'node:fs';
const label = process.argv[2];
if (!label || !/^[a-z0-9-]+$/.test(label)) throw new Error('A unique evidence label is required');
const output = new URL(`./evidence/trigger-${label}.json`, import.meta.url);
if (existsSync(output)) throw new Error('Trigger already recorded; inspect it before retrying');
const client = http2.connect('http://127.0.0.1:13538');
client.on('error', error => { console.error(error.message); process.exitCode = 1; });
const request = client.request({ ':method': 'POST', ':path': '/bark_server.SweepAdminService/TriggerSweep',
  'content-type': 'application/grpc', 'te': 'trailers' });
let status;
request.on('response', headers => { status = headers['grpc-status']; });
request.on('trailers', headers => { status = headers['grpc-status']; });
request.on('data', () => {});
request.on('error', error => { console.error(error.message); process.exitCode = 1; client.destroy(); });
request.on('end', () => {
  const record = { manual_sweep_trigger: true, grpc_status: status, timestamp: new Date().toISOString() };
  writeFileSync(output, JSON.stringify(record, null, 2) + '\n');
  console.log(JSON.stringify(record));
  if (status !== '0') process.exitCode = 1;
  client.close();
});
request.setTimeout(10000, () => { request.close(); client.destroy(); process.exitCode = 1; });
request.end(Buffer.alloc(5));

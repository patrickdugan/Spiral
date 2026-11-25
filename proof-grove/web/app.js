'use strict';
const $ = id => document.getElementById(id);
let state = { mode: 'demo', current: null, cases: [], vtxos: [], receiptText: '' };
const labels = { payments: 'Payment gate', 'protected-preview': 'Cashu recovery', caretaker: 'Ark caretaker', evidence: 'Evidence & sources' };
const errors = {
  deposit_script_reused: 'This deposit script is already bound to its original intent. A second recipient cannot claim it.',
  payment_already_claimed: 'This payment is already reserved for another intent. No second request was prepared.',
  wrong_amount: 'The deposit amount does not match the fixed intent. No request was prepared.',
  wrong_payment_script: 'The payment went to a different script. This intent cannot claim it.',
  payment_reorged: 'The payment block is no longer on the observed active chain. Authorization is blocked.',
  chain_view_stale: 'The chain observation is too old. Refresh it before accepting the payment.',
  demo_namespace_required: 'An operator report cannot be promoted into verified payment evidence.',
  live_verifier_not_configured: 'Configure the native verifier and local Bitcoin Core before importing live evidence.'
};
function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
async function api(path, body) {
  if (globalThis.ProofGroveHosted) return globalThis.ProofGroveHosted(path, body);
  const response = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Proof-Grove': '1' }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(errors[data.error] || data.error || 'Request failed');
  return data;
}
function error(message) { $('app-error').textContent = message; $('app-error').hidden = false; }
function clearError() { $('app-error').hidden = true; }
function tab(id) {
  if(globalThis.ProofGroveConnection&&!globalThis.ProofGroveConnection.connected)return;
  if (!Object.hasOwn(labels, id)) return;
  document.querySelectorAll('.page').forEach(page => { page.hidden = page.id !== id; });
  document.querySelectorAll('[data-tab]').forEach(button => { button.classList.toggle('active', button.dataset.tab === id); if (button.dataset.tab === id) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
  $('breadcrumb').textContent = labels[id];
  if (id === 'evidence') loadArchive().catch(e => error(e.message));
}
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => tab(button.dataset.tab)));
$('protected-preview-case').addEventListener('change', () => {
  $('protected-preview-export').hidden = true;
  $('protected-preview-details').hidden = true;
  $('protected-preview-result').textContent = '';
});
$('protected-preview-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  const result = $('protected-preview-result');
  const details = $('protected-preview-details');
  const exportEvidence = $('protected-preview-export');
  const caseSelect = $('protected-preview-case');
  const variant = caseSelect.value;
  button.disabled = true;
  caseSelect.disabled = true;
  details.hidden = true;
  exportEvidence.hidden = true;
  result.textContent = 'Checking the recorded evidence…';
  try {
    const check = await api('/api/protected/preview?case=' + encodeURIComponent(variant));
    result.textContent = check.verified
      ? `Verified ${check.payout.payout_sats.toLocaleString('en-US')} sats with a ${check.payout.fee_sats} sat fee after ${check.payout.relative_delay_blocks} blocks.`
      : `Rejected. ${check.detail}`;
    if (check.verified) {
      $('protected-preview-json').textContent = JSON.stringify(check.payout, null, 2);
      details.hidden = false;
      exportEvidence.hidden = variant !== 'original';
    }
  } catch (err) {
    result.textContent = err.message;
  } finally {
    button.disabled = false;
    caseSelect.disabled = false;
  }
});
$('trust-link').addEventListener('click', event => { event.preventDefault(); tab('evidence'); });
function renderRun(run) {
  state.current = run;
  $('inspect-receipt').disabled = false;
  const accepted = run.decision.accepted;
  const panel = document.querySelector('.decision-panel');
  panel.classList.toggle('rejected', !accepted);
  $('decision-symbol').textContent = accepted ? '✓' : '×';
  $('decision-label').textContent = (run.simulation ? 'FIXTURE ' : run.evidence_level==='core-regtest' ? 'CORE REGTEST CHECK ' : 'M16 PROOF ') + (accepted ? 'ACCEPTED' : 'REJECTED');
  $('decision-heading').textContent = accepted ? 'Ready for the next step.' : 'Stopped at the gate.';
  $('decision-detail').textContent = accepted ? 'The payment matches its intent. One settlement request is prepared. Execution is pending.' : (errors[run.decision.code] || run.decision.code);
  $('metric-state').textContent = accepted ? 'Prepared' : 'Blocked';
  $('metric-phase-label').textContent=run.simulation ? 'Settlement status' : 'Payment admission';
  $('metric-phase-detail').textContent=run.simulation ? 'Submission and confirmation remain pending' : 'Provider progress is recorded separately';
  $('decision-settlement').textContent=accepted ? 'Not submitted' : 'Blocked';
  $('metric-amount').textContent = (run.intent?.amount_sats || run.decision.receipt?.amount_sats || 0).toLocaleString('en-US');
  $('metric-caption').textContent = (run.intent?.rail || run.decision.receipt?.rail || 'payment').toUpperCase() + ' · fixed recipient';
  const steps = run.steps || [
    { name: run.evidence_level==='core-regtest' ? 'Check the regtest payment' : 'Verify M16 proof', state: 'verified', detail: run.evidence_level==='core-regtest' ? 'The configured Core node checked an actual regtest transaction. This is not a ZK proof.' : 'Pinned kan-payment-gate verified these exact statement bytes.' },
    { name: 'Recheck the active chain', state: 'checked', detail: 'Local Bitcoin Core checked the payment block and proof tip.' },
    { name: 'Bind intent & reserve once', state: 'prepared', detail: 'The immutable recipient and payment match. A durable request is prepared.' },
    { name: run.decision.receipt?.rail==='ark' ? 'Ark execution' : 'Claim through the Cashu wallet', state: 'pending', detail: run.decision.receipt?.rail==='ark' ? 'Ark execution is not connected. This admission does not sign or broadcast a transaction.' : 'The wallet can request admitted blind signatures, then unblind and verify them. Ark execution is separate.' }
  ];
  $('steps').replaceChildren(...steps.map((step, index) => {
    const li = element('li'); li.append(element('span', 'step-number', String(index + 1).padStart(2, '0')));
    const copy = element('div', 'step-copy'); copy.append(element('h3', '', step.name), element('p', '', step.detail));
    li.append(copy, element('span', 'step-state ' + step.state, step.state.toUpperCase())); return li;
  }));
  $('raw-evidence').textContent = JSON.stringify(run.evidence || run.decision.receipt, null, 2);
  state.receiptText = JSON.stringify(run.decision.receipt || { rejected: true, code: run.decision.code, evidence_level: run.evidence_level, settlement: 'not executed' }, null, 2);
  $('receipt-json').textContent = state.receiptText;
  if(!run.simulation && accepted){
    $('metric-state').textContent='Admitted';$('decision-heading').textContent='Payment admitted.';
    $('decision-detail').textContent='The payment matches its intent. Inspect the provider stage separately from this admission receipt.';
    api('/api/cashu/operations').then(result=>{
      if(state.current!==run)return;
      const operation=result.operations.find(op=>op.intent_id===run.decision.receipt.intent_id);
      if(operation?.state==='signatures_received'){
        $('metric-phase-label').textContent='Cashu provider stage';$('metric-state').textContent='Signatures returned';
        $('metric-phase-detail').textContent='Wallet verification stays in its encrypted vault';
        $('decision-settlement').textContent='Signatures returned';
        $('decision-detail').textContent='The mint response is saved. Inspect the wallet for its verified bearer proofs.';
        const last=$('steps').lastElementChild;
        last.querySelector('h3').textContent='Blind signatures returned';
        last.querySelector('p').textContent='The desk saved the mint response. The wallet unblinds and verifies its own proofs.';
        last.querySelector('.step-state').textContent='RECEIVED';
      }
    }).catch(()=>{if(state.current===run)$('metric-phase-detail').textContent='Provider stage could not be read';});
  }
}
function describeCase() { $('case-description').textContent = state.cases.find(c => c.id === $('case-select').value)?.description || ''; }
$('case-select').addEventListener('change', describeCase);
$('run-case').addEventListener('click', async () => {
  clearError(); $('run-case').disabled = true;
  try { renderRun(await api('/api/run', { case: $('case-select').value })); } catch (e) { error(e.message); }
  finally { $('run-case').disabled = false; }
});
$('inspect-receipt').addEventListener('click', () => $('receipt-dialog').showModal());
$('close-dialog').addEventListener('click', () => $('receipt-dialog').close());
$('copy-receipt').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(state.receiptText); $('copy-receipt').textContent = 'Copied'; } catch { error('Select the receipt text to copy it from this browser.'); }
});
function renderPlans(plans) {
  $('vtxo-table').replaceChildren(...plans.map(plan => {
    const tr = element('tr'); tr.title = plan.reason;
    tr.append(element('td', '', plan.id), element('td', '', plan.value_sats.toLocaleString('en-US') + ' sats'), element('td', '', plan.remaining_blocks + ' blocks'));
    const action = element('td'); action.append(element('span', 'action-pill ' + plan.action, plan.action.replaceAll('_', ' ')));
    tr.append(action, element('td', '', 'Not executed')); return tr;
  }));
}
function renderArkOperation(operation) {
  state.arkOperation = operation.id;
  $('ark-operation-details').hidden = false;
  $('ark-operation-summary').textContent = 'Refresh ' + operation.state.replaceAll('_', ' ') + (operation.result?.actual_fee_sats !== undefined ? ' · fee ' + operation.result.actual_fee_sats.toLocaleString('en-US') + ' sats' : '');
  $('ark-operation').textContent = JSON.stringify(operation, null, 2);
  $('ark-reconcile').hidden = false;
}
$('load-ark').addEventListener('click', async () => {
  clearError(); $('load-ark').disabled = true;
  try {
    const wallet = await api('/api/ark/wallet');
    if (wallet.evidence_level === 'not-connected') throw new Error('Configure a local Bark wallet and Core node first.');
    $('ark-vtxo-panel').hidden=false;
    $('ark-notice').textContent = wallet.meaning;
    $('ark-wallet-status').textContent = wallet.network + ' · Core block ' + wallet.tip_height.toLocaleString('en-US') + ' · ' + wallet.vtxos.length + ' VTXOs. ' + wallet.fee_limit + '.';
    $('tip-slider').disabled = true;
    $('ark-demo-clock').hidden = true;
    const headings = document.querySelectorAll('#caretaker table th'); headings[3].textContent = 'Chain anchor'; headings[4].textContent = 'Wallet state';
    $('height-readout').textContent = 'Core block ' + wallet.tip_height.toLocaleString('en-US');
    $('vtxo-table').replaceChildren(...wallet.vtxos.map(v => {
      const row = element('tr'); const id = element('td', '', v.id.slice(0, 12) + '…:' + v.id.split(':')[1]); id.title = v.id;
      row.append(id, element('td', '', v.amount_sat.toLocaleString('en-US') + ' sats'), element('td', '', v.remaining_blocks + ' blocks'), element('td', '', v.anchor_error || 'Anchor confirmed'), element('td', '', v.state.type)); return row;
    }));
    const spendable = wallet.vtxos.filter(v => v.state.type === 'spendable' && !v.anchor_error);
    $('ark-refresh-form').hidden = !wallet.regtest_execution || !spendable.length || state.hostedMutations===false;
    $('ark-input').replaceChildren(...spendable.map(v => {const option = element('option', '', v.id.slice(0, 12) + '… · ' + v.amount_sat.toLocaleString('en-US') + ' sats'); option.value = v.id; return option;}));
    $('ark-height').value = wallet.tip_height + 1;
    $('exit-prepare-form').hidden = !wallet.regtest_execution || !spendable.length || state.hostedMutations===false;
    $('exit-input').replaceChildren(...spendable.map(v => {const option = element('option', '', v.id.slice(0, 12) + '… · ' + v.amount_sat.toLocaleString('en-US') + ' sats'); option.value = v.id; return option;}));
    const operations = await api('/api/ark/operations');
    if (operations.operations.length) renderArkOperation(operations.operations.at(-1));
  } catch (e) { error(e.message); }
  finally { $('load-ark').disabled = false; }
});
function renderExit(record, fresh=false) {
  state.exitId = record.id;state.exitState=record.state;
  const saved=state.exits?.find(item=>item.id===record.id);
  if(saved){saved.state=record.state;saved.observation=record.observation||{...record};}
  const option=Array.from($('exit-record').options).find(item=>item.value===record.id);
  if(option)option.textContent=record.id.slice(0,12)+'… · '+record.state.replaceAll('_',' ');
  $('exit-saved').hidden = false;
  const descriptions = {
    prepared:'Saved locally. Transaction structure and CPFP fees checked.',
    requires_package_validation:'Saved package needs Core validation during combined package submission.',
    ready:'Core dry-run passed for the next wave.',
    awaiting_confirmations:'Waiting for this wave to confirm before advancing.',
    exit_confirmed:'Exit transactions confirmed. Waiting for the owner claim timelock.',
    claim_ready:'Exit output is ready for its owner to sign the final claim.',
    submission_uncertain:'Submission reply was lost. Check the saved transaction IDs before retrying.',
    inputs_unavailable:'A saved input is unavailable. Review competing spends or a reorg.',
    package_rejected:'Core did not accept the full package. Review its rejection and saved transaction IDs.',
    target_spent:'The exit output is spent. Verify the owner claim separately.',
    expiry_reached:'Expiry reached. Review recovery and competing spends manually.'
  };
  $('exit-state').textContent = (fresh?'':'Saved observation. ') + (descriptions[record.state] || record.state.replaceAll('_',' ')) + (fresh?'':' Check recovery for current chain state.');
  $('exit-id').textContent = record.id;
  $('exit-observation').textContent = JSON.stringify(record.observation || record, null, 2);
}
async function loadExits(selected) {
  const result = await api('/api/ark/exits'); state.exits = result.exits;
  $('exit-saved').hidden = !result.exits.length;
  $('broadcast-exit').hidden = !result.broadcast_enabled;
  $('exit-record').replaceChildren(...result.exits.map(record => {const option = element('option','',record.id.slice(0,12)+'… · '+record.state.replaceAll('_',' '));option.value=record.id;return option;}));
  if(result.exits.length){$('exit-record').value=selected || result.exits.at(-1).id;renderExit(result.exits.find(record=>record.id===$('exit-record').value));}
  else $('exit-help').textContent='No saved recovery packages in this desk. Connect a regtest Bark wallet to prepare one, or import an owner-authenticated bundle through the CLI.';
}
$('load-exits').addEventListener('click',async()=>{try{await loadExits();}catch(e){error(e.message);}});
$('exit-record').addEventListener('change',()=>renderExit(state.exits.find(record=>record.id===$('exit-record').value)));
$('exit-prepare-form').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;
  try{const record=await api('/api/ark/exits/prepare',{vtxos:[$('exit-input').value],fee_rate:Number($('exit-rate').value),max_fee_sats:Number($('exit-fee').value)});await loadExits(record.id);}
  catch(e){error(e.message);}finally{button.disabled=false;}
});
for(const [id,broadcast] of [['check-exit',false],['broadcast-exit',true]]){
  $(id).addEventListener('click',async()=>{$(id).disabled=true;clearError();try{renderExit(await api('/api/ark/exits/advance',{id:state.exitId,broadcast}),true);}catch(e){error(e.message);}finally{$(id).disabled=false;}});
}
$('download-exit').addEventListener('click',async()=>{
  try{const response=await fetch('/api/ark/exits/bundle?id='+encodeURIComponent(state.exitId));if(!response.ok)throw new Error('Recovery export failed');const blob=await response.blob();const url=URL.createObjectURL(blob);const link=element('a');link.href=url;link.download='proof-grove-private-exit-'+state.exitId.slice(0,12)+'.json';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  catch(e){error(e.message);}
});
$('ark-refresh-form').addEventListener('submit', async event => {
  event.preventDefault(); clearError(); const button = event.target.querySelector('button'); button.disabled = true;
  try {renderArkOperation(await api('/api/ark/refresh', {vtxos:[$('ark-input').value], height:Number($('ark-height').value), max_fee_sats:Number($('ark-fee').value)}));}
  catch (e) {error(e.message);}
  finally {button.disabled = false;}
});
$('ark-reconcile').addEventListener('click', async () => {
  $('ark-reconcile').disabled = true;
  try {renderArkOperation(await api('/api/ark/reconcile', {id:state.arkOperation}));}
  catch (e) {error(e.message);}
  finally {$('ark-reconcile').disabled = false;}
});
$('tip-slider').addEventListener('input', async event => {
  const tip = Number(event.target.value); $('height-readout').textContent = 'Block ' + tip.toLocaleString('en-US');
  const request = ++state.planRequest;
  try { const results = await Promise.all(state.vtxos.map(vtxo => api('/api/plan', { vtxo, tip_height: tip }))); if (request === state.planRequest) renderPlans(results.map(r => r.plan)); }
  catch (e) { error(e.message); }
});
async function loadArchive() { const manifest = await api('/api/archive/manifest'); $('cid-field').value = manifest.cid; }
$('download-archive').addEventListener('click', async () => {
  try {
    let blob;
    if(globalThis.ProofGroveHosted)blob=await globalThis.ProofGroveHosted.archive();
    else{const response=await fetch('/api/archive');if(!response.ok)throw new Error('Archive export failed');blob=await response.blob();}
    const url = URL.createObjectURL(blob);
    const link = element('a'); link.href = url; link.download = 'proof-grove-public-receipts.json'; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { error(e.message); }
});
async function bytesBase64(file) { const bytes = new Uint8Array(await file.arrayBuffer()); let text = ''; for (let i = 0; i < bytes.length; i += 8192) text += String.fromCharCode(...bytes.subarray(i, i + 8192)); return btoa(text); }
function renderProofCheck(result){
  state.current=null;state.receiptText=JSON.stringify(result,null,2);
  $('inspect-receipt').disabled=false;$('receipt-json').textContent=state.receiptText;
  $('raw-evidence').textContent=state.receiptText;
  $('decision-symbol').textContent='✓';$('decision-label').textContent='NATIVE M16 PROOF VERIFIED';
  $('decision-heading').textContent='Proof checked without a claim.';
  $('decision-detail').textContent=result.chain_observation?'Core also checked the payment block and proof tip. This check does not admit a payment or issue ecash.':'Current chain context is unavailable: '+result.chain_error+'. No payment was admitted.';
  $('metric-amount').textContent=result.evidence.value_sats.toLocaleString('en-US');
  $('metric-state').textContent='Verified only';$('decision-settlement').textContent='Not requested';
  $('metric-phase-label').textContent='Proof verification';$('metric-phase-detail').textContent='No payment reserved or signatures requested';
  $('steps').replaceChildren();
}
$('check-recorded-proof').addEventListener('click',async()=>{
  const button=$('check-recorded-proof');button.disabled=true;clearError();
  try{renderProofCheck(await api('/api/proofs/recorded/check',{}));}
  catch(problem){error(problem.message);}
  finally{button.disabled=false;}
});
$('live-controls').addEventListener('submit', async event => {
  event.preventDefault(); clearError(); const button = event.target.querySelector('button'); button.disabled = true;
  try {
    if(state.mode==='regtest'){
      renderRun(await api('/api/verify',{intent_id:$('intent-select').value,txid:$('regtest-txid').value,vout:Number($('regtest-vout').value)}));return;
    }
    const statement = $('statement-file').files[0], proof = $('proof-file').files[0];
    if (!statement || statement.size !== 1292 || !proof || proof.size > 4 * 1024 * 1024 || proof.size === 0) throw new Error('Choose a 1,292 byte statement and a final proof of at most 4 MiB.');
    const payload={intent_id:$('intent-select').value,statement_base64:await bytesBase64(statement),proof_base64:await bytesBase64(proof)};
    if(!$('intent-select').value){renderProofCheck(await api('/api/proofs/check',payload));return;}
    const result = await api('/api/verify', payload);
    renderRun(result);
  } catch (e) { renderRun({ simulation: false, decision: { accepted: false, code: e.message }, evidence_level: 'rejected', steps: [{ name: 'Payment verification', state: 'rejected', detail: e.message }, { name: 'Settlement', state: 'blocked', detail: 'No new request prepared by this attempt. Existing reservations are retained.' }] }); error(e.message); }
  finally { button.disabled = false; }
});
for (const [button, path] of [['read-cashu', '/api/cashu/info'], ['read-bark', '/api/bark/history'],['read-issuance','/api/cashu/operations']]) {
  $(button).addEventListener('click', async () => { $(button).disabled = true; try { $('provider-report').textContent = JSON.stringify(await api(path), null, 2); } catch (e) { error(e.message); } finally { $(button).disabled = false; } });
}
async function loadChainstate(){
  if(state.mode==='demo')return;
  $('chainstate-panel').hidden=false;
  try{
    const value=await api('/api/chainstate');$('chainstate-json').textContent=JSON.stringify(value,null,2);
    $('network-label').textContent=value.network+' · Core block '+value.blocks.toLocaleString('en-US');
    $('chainstate-status').textContent=value.network+' · block '+value.blocks.toLocaleString('en-US')+' · observed '+new Date(value.observed_at*1000).toLocaleTimeString()+(value.initialblockdownload?' · node still syncing':' · configured Core observation');
  }catch(error){$('chainstate-status').textContent='Chain observer unavailable: '+error.message;$('chainstate-json').textContent='';}
}
$('refresh-chainstate').addEventListener('click',loadChainstate);
async function initialize() {
  const [status, cases, vtxos, sources] = await Promise.all(['/api/status', '/api/cases', '/api/vtxos', '/api/sources'].map(path => api(path)));
  state.mode = status.mode; state.cases = cases.cases; state.vtxos = vtxos.vtxos; state.planRequest = 0;
  $('protected-preview-tab').hidden = !status.protected_preview_configured;
  state.hostedMutations=!status.hosted_access?.enabled||status.hosted_access.mutations;
  $('proof-files').hidden=status.mode==='regtest';
  $('statement-file').required=status.mode==='live';$('proof-file').required=status.mode==='live';
  $('regtest-fields').hidden=status.mode!=='regtest';$('regtest-txid').required=status.mode==='regtest';
  $('check-recorded-proof').hidden=true;$('recorded-proof-status').hidden=true;
  $('ark-connection').hidden=!status.ark_wallet_configured;$('ark-vtxo-panel').hidden=true;
  $('mode-badge').textContent = status.mode === 'demo' ? 'DEMO · NO FUNDS' : status.mode==='regtest' ? 'REGTEST · TEST COINS' : 'CONNECTED · PROOF GATE';
  if (status.mode !== 'demo') {
    $('ark-demo-clock').hidden = true;
    $('ark-notice').textContent = 'Read the configured Bark wallet for its VTXOs, or inspect saved recovery packages through Core alone.';
    if (!status.ark_wallet_configured) {$('ark-connection').hidden = true;$('ark-vtxo-panel').hidden = true;}
    $('demo-controls').hidden = true; $('live-controls').hidden = false;
    $('mode-notice').querySelector('p').textContent = status.mode==='regtest' ? 'Isolated regtest mode checks real Core transactions and can gate Cashu test issuance. It does not verify a ZK proof or use real bitcoin.' : 'Connected mode verifies native M16 proof bytes and active-chain context. The configured Cashu wallet can claim admitted issuance. Ark execution remains separate.';
    if(status.mode==='regtest'){
      $('proof-files').hidden=true;$('statement-file').required=false;$('proof-file').required=false;
      $('regtest-fields').hidden=false;$('regtest-txid').required=true;
      $('verification-help').textContent='Uses the configured isolated regtest Core node. No fixture or browser-supplied verification flag is accepted.';
    }else $('verification-help').textContent='Checks native proof bytes and active testnet4 chain context. Historical verification creates no new payment credit.';
    $('network-label').textContent = status.intents[0]?.network || 'No intents configured';
    $('intent-select').replaceChildren(...status.intents.map(intent => { const option = element('option', '', intent.id + ' · ' + intent.amount_sats.toLocaleString('en-US') + ' sats'); option.value = intent.id; return option; }));
    if(status.mode==='live'){
      const option=element('option','','Verify native proof only — no payment claim');option.value='';$('intent-select').prepend(option);
      if(!status.intents.length)$('intent-select').value='';
      $('intent-select').required=false;
      if(!state.hostedMutations){$('intent-select').value='';[...$('intent-select').options].filter(option=>option.value).forEach(option=>option.disabled=true);}
    }
    $('tip-slider').disabled = true; $('metric-state').textContent = 'Awaiting proof'; $('metric-amount').textContent = '—';
    $('decision-symbol').textContent = '○'; $('decision-label').textContent = status.mode==='regtest' ? 'AWAITING REGTEST PAYMENT' : 'AWAITING NATIVE PROOF'; $('decision-heading').textContent = 'Choose an intent.'; $('decision-detail').textContent = status.mode==='regtest' ? 'Enter a confirmed regtest transaction and output index for a configured intent.' : 'Import a statement and its final proof to check a configured payment.';
    $('inspect-receipt').disabled = true;
  } else {
    $('case-select').replaceChildren(...state.cases.map(item => { const option = element('option', '', item.name + ' · ' + item.group); option.value = item.id; return option; })); describeCase(); renderRun(cases.current);
  }
  renderPlans(vtxos.plans);
  $('integrations').replaceChildren(...sources.integrations.map(item => {
    const row = element('div', 'integration'); row.append(element('span', 'integration-icon', item.symbol)); const copy = element('div'); copy.append(element('h3', '', item.name), element('p', '', item.description), element('small', '', item.status)); row.append(copy); return row;
  }));
  $('source-list').replaceChildren(...sources.sources.map(item => {
    const row = element('div', 'source'); const left = element('div'); const link = element('a', '', item.name + ' ↗');
    const url = new URL(item.url); if (url.protocol === 'https:') { link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
    left.append(link); if (item.pin) left.append(element('small', '', item.pin)); row.append(left, element('p', '', item.use)); return row;
  }));
  if(globalThis.ProofGroveConnection)tab('payments');
  else if (location.hash === '#evidence') tab('evidence');
  if(status.mode!=='demo'){
    await loadChainstate();
    if(status.mode==='live'){
      try{
        const record=await api('/api/proofs/recorded');$('check-recorded-proof').hidden=false;
        $('recorded-proof-status').hidden=false;$('recorded-proof-status').textContent=record.name+' · checking this record does not claim its historical payment.';
      }catch{$('check-recorded-proof').hidden=true;}
    }
  }
}
if(globalThis.ProofGroveConnection){
  globalThis.ProofGroveConnection.onConnect=initialize;
  globalThis.ProofGroveConnection.onDisconnect=()=>{
    state.current=null;state.receiptText='';state.vtxos=[];state.cases=[];state.mode='disconnected';
    for(const id of ['receipt-json','raw-evidence','provider-report','ark-operation','exit-observation','chainstate-json'])$(id).textContent='';
    $('receipt-dialog').close();$('inspect-receipt').disabled=true;$('app-error').hidden=true;
  };
}else initialize().catch(e => error('Workspace could not load: ' + e.message));

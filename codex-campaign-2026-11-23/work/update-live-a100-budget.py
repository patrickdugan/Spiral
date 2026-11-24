from pathlib import Path


repo = Path(r"C:\Users\patri\OneDrive\Documents\GitHub\rbzk-prover-ui")


def edit(name, changes):
    path = repo / name
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    text = original.decode("utf-8").replace("\r\n", "\n")
    for old, new in changes:
        if text.count(old) != 1:
            raise ValueError(f"unexpected contents of {name}")
        text = text.replace(old, new, 1)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


edit("prover-ui/web/app.js", [
    ('''  function a100Budget({saved,target,rate,credit}) {
    if(!finite(rate)||rate<=0)return null;
    const coresPerHour=10.38*60;''', '''  function observedBudgetPace(history) {
    const last=history.at(-1);
    if(!last)return null;
    const first=history.find(point=>point.replayed===last.replayed && last.t-point.t<=300);
    const seconds=last.t-first.t, cores=last.core-first.core;
    return seconds>=240 && cores>0 ? {perMinute:cores*60/seconds,seconds} : null;
  }
  function a100Budget({saved,target,rate,credit,coresPerMinute=10.38}) {
    if(!finite(rate)||rate<=0||!finite(coresPerMinute)||coresPerMinute<=0)return null;
    const coresPerHour=coresPerMinute*60;'''),
    ('''checkpointMosaic,a100Budget,arkWorkerLabel''', '''checkpointMosaic,a100Budget,observedBudgetPace,arkWorkerLabel'''),
    ('''    const rate=value('budget-rate');
    const estimate=ProofEta.a100Budget({saved,target,rate,credit:value('budget-credit')});
    const catchUp=usingPublished&&target===null&&localSaved>saved?
      ProofEta.a100Budget({saved,target:localSaved,rate}):null;''', '''    const enteredRate=value('budget-rate');
    const cloud=arkCloudSignal();
    const leaseRate=cloud?.active&&Number.isFinite(cloud.sample.rate_usd_per_hour)?cloud.sample.rate_usd_per_hour:null;
    const pace=cloud?.active&&cloud.sample.ark_running?ProofEta.observedBudgetPace(checkpointHistory):null;
    const rate=enteredRate ?? leaseRate ?? 1.35672043;
    const coresPerMinute=pace?.perMinute;
    const estimate=ProofEta.a100Budget({saved,target,rate,credit:value('budget-credit'),coresPerMinute});
    const catchUp=usingPublished&&target===null&&localSaved>saved?
      ProofEta.a100Budget({saved,target:localSaved,rate,coresPerMinute}):null;
    const priceBasis=enteredRate!==null?'Entered price':leaseRate!==null?'Live lease price':'Earlier on-demand quote';
    const paceBasis=pace?`${n(coresPerMinute,1)} fresh cores/min over ${formatDuration(pace.seconds)}`:
      'Earlier A100 pilot · 10.38 fresh cores/min';
    $('budget-basis').textContent=`${priceBasis} · $${n(rate,4)}/h · ${paceBasis}`;'''),
    ('''core shards costs about $${estimate.perThousand.toFixed(2)} at the measured pace.''', '''core shards costs about $${estimate.perThousand.toFixed(2)} at this pace.'''),
])

edit("prover-ui/web/index.html", [
    ('''The pilot measured 10.38 new core shards per minute. Use a scenario total to price core work from a saved copy. Replay, recursion after core, compression, verification, and storage have separate costs.''',
     '''Use a scenario total to price fresh core work from a saved copy. Replay, recursion after core, compression, verification, and storage have separate costs.'''),
    ('''value="1.35672"''', '''placeholder="Use the observed or earlier rate"'''),
    ('''            <p id="budget-result" class="panel-sub"></p>''', '''            <p id="budget-basis" class="panel-sub"></p>
            <p id="budget-result" class="panel-sub"></p>'''),
])

edit("prover-ui/src/server.rs", [
    ('''    sample["spot"] = raw["spot"].clone();''', '''    sample["spot"] = raw["spot"].clone();
    if let Some(rate) = raw["rate_usd_per_hour"].as_f64().filter(|rate| *rate > 0.0 && *rate <= 100.0) {
        sample["rate_usd_per_hour"] = json!(rate);
    }'''),
    ('''            "storage_key_id": 8,
        });''', '''            "storage_key_id": 8,
            "rate_usd_per_hour": 1.08672043,
        });'''),
    ('''        assert_eq!(live["ark_running"], true);''', '''        assert_eq!(live["ark_running"], true);
        assert_eq!(live["rate_usd_per_hour"], 1.08672043);'''),
])

edit("prover-ui/tests/ongoing_jobs.cjs", [
    ('''checkpointMosaic, a100Budget, arkWorkerLabel''', '''checkpointMosaic, a100Budget, observedBudgetPace, arkWorkerLabel'''),
    ('''test('private seed staging is visible without counting a GPU as running', () => {''', '''test('live budget uses a full fresh-core window and ignores the earlier core replay', () => {
  const history=[{t:670,core:2,replayed:2000},{t:700,core:4,replayed:4378},{t:1000,core:29,replayed:4378}];
  const pace=observedBudgetPace(history);
  assert.deepEqual(pace,{perMinute:5,seconds:300});
  const cost=a100Budget({saved:4421,target:5421,rate:1.08672043,coresPerMinute:pace.perMinute});
  assert.equal(cost.cost.toFixed(2),'3.62');
  assert.equal(observedBudgetPace([...history,{t:1010,core:30,replayed:4380}]),null);
  assert.equal(observedBudgetPace([{t:700,core:4,replayed:4378},{t:1000,core:4,replayed:4378}]),null);
});

test('private seed staging is visible without counting a GPU as running', () => {'''),
])

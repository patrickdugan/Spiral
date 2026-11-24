import sys
from pathlib import Path


repo = Path(sys.argv[1])
updates = {}


def edit(name, changes):
    path = repo / name
    original = path.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    source = original.decode("utf-8").replace("\r\n", "\n")
    for before, after in changes:
        if source.count(before) != 1:
            raise ValueError(f"{name} no longer has the expected source")
        source = source.replace(before, after, 1)
    updates[path] = source.replace("\n", newline).encode("utf-8")


edit("prover-ui/web/app.js", [
    ('''    if(!finite(rate)||rate<=0||!finite(coresPerMinute)||coresPerMinute<=0)return null;
    const coresPerHour=coresPerMinute*60;''',
     '''    if(!finite(rate)||rate<=0)return null;
    if(coresPerMinute!==null&&(!finite(coresPerMinute)||coresPerMinute<=0))return null;
    const coresPerHour=coresPerMinute===null?null:coresPerMinute*60;'''),
    ('''    const hours=hasTarget?(target-saved)/coresPerHour:null;''',
     '''    const hours=hasTarget&&coresPerHour!==null?(target-saved)/coresPerHour:null;'''),
    ('''    return {hours,cost,perThousand:1000/coresPerHour*rate,runway,
      runwayCores:runway===null?null:Math.floor(runway*coresPerHour),''',
     '''    return {hours,cost,perThousand:coresPerHour===null?null:1000/coresPerHour*rate,runway,
      runwayCores:runway===null||coresPerHour===null?null:Math.floor(runway*coresPerHour),'''),
    ('''    const saved=usingPublished?1727:localSaved;''',
     '''    const saved=usingPublished?3646:localSaved;'''),
    ('''    const leaseRate=cloud?.active&&Number.isFinite(cloud.sample.rate_usd_per_hour)?cloud.sample.rate_usd_per_hour:null;
    const pace=cloud?.active&&cloud.sample.ark_running?ProofEta.observedBudgetPace(checkpointHistory):null;
    const rate=enteredRate ?? leaseRate ?? 1.35672043;
    const coresPerMinute=pace?.perMinute;''',
     '''    const lease=cloud?.sample.active&&!cloud.sample.local_verification&&Number.isSafeInteger(cloud.sample.vm_id);
    const leaseRate=lease&&Number.isFinite(cloud.sample.rate_usd_per_hour)?cloud.sample.rate_usd_per_hour:null;
    const pace=cloud?.active&&cloud.sample.ark_running?ProofEta.observedBudgetPace(checkpointHistory):null;
    const rate=enteredRate ?? leaseRate ?? 1.35672043;
    const coresPerMinute=lease?(pace?.perMinute ?? null):undefined;'''),
    ('''    const priceBasis=enteredRate!==null?'Entered price':leaseRate!==null?'Live lease price':'Earlier on-demand quote';
    const paceBasis=pace?\x60${n(coresPerMinute,1)} fresh cores/min over ${formatDuration(pace.seconds)}\x60:
      'Earlier A100 pilot · 10.38 fresh cores/min';''',
     '''    const priceBasis=enteredRate!==null?'Entered price':leaseRate!==null?'Lease price':'Earlier on-demand quote';
    const paceBasis=lease?
      (pace?\x60${n(coresPerMinute,1)} fresh cores/min over ${formatDuration(pace.seconds)}\x60:
        cloud.fresh?'Waiting for a recent fresh-core rate':'Waiting for a fresh server heartbeat'):
      'Earlier A100 pilot · 10.38 fresh cores/min';'''),
    ('''      catchUp?\x60Matching the laptop’s''',
     '''      estimate.perThousand===null?'Core cost and ETA are on hold until the live run records a recent fresh-core rate.':
      catchUp?\x60Matching the laptop’s'''),
    ('''      \x60Credit covers ${n(estimate.runway,2)} A100 hours, or up to ${n(estimate.runwayCores)} new cores before overhead.\x60+''',
     '''      \x60Credit covers ${n(estimate.runway,2)} A100 hours before overhead.\x60+
      (estimate.runwayCores===null?'':\x60 At this pace, up to ${n(estimate.runwayCores)} new cores.\x60)+'''),
])

edit("prover-ui/web/index.html", [
    ('Published copy · 1,727 cores', 'Published base + delta · 3,646 cores'),
])

edit("prover-ui/tests/ongoing_jobs.cjs", [
    ('''test('live budget uses a full fresh-core window and ignores the earlier core replay', () => {''',
     '''test('the active lease keeps dollar runway when checkpoint throughput is unknown', () => {
  const budget=a100Budget({saved:3646,target:4646,rate:1.08672043,credit:10,coresPerMinute:null});
  assert.equal(budget.hours,null);
  assert.equal(budget.cost,null);
  assert.equal(budget.perThousand,null);
  assert.equal(budget.runwayCores,null);
  assert.equal(budget.runway.toFixed(2),'9.20');
});

test('live budget uses a full fresh-core window and ignores the earlier core replay', () => {'''),
])

for path, data in updates.items():
    path.write_bytes(data)

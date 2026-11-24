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
    ('''    const live=state.live||{},wsl=live.wsl_prover||{},progress=wsl.progress||{};
    const source=\x60${wsl.progress_source||progress.path||'unknown'}:${live.wsl_prover?.prover_binary_sha256||''}\x60;''',
     '''    const wsl=state.live?.wsl_prover||{};
    const localConnected=freshRuntime(), localActive=localConnected&&!!arkProcess();
    const cloud=arkCloudSignal();
    const remote=cloud?.sample.active&&cloud.sample.ark_running&&
      Number.isSafeInteger(cloud.sample.vm_id)&&(cloud.fresh||!localActive)?cloud:null;
    const progress=remote?(ProofEta.checkpointTrend(checkpointHistory)?.progress || {}):(wsl.progress || {});
    const connected=remote?remote.fresh:localConnected;
    const active=remote?remote.active:localActive;
    const source=remote?\x60hyperstack:${remote.sample.vm_id}:${remote.sample.started_at_unix}\x60:
      \x60${wsl.progress_source||progress.path||'unknown'}:${wsl.prover_binary_sha256||''}\x60;'''),
    ('''    const active=freshRuntime() && !!arkProcess();
    const model=ProofEta.estimate(progress,{now:Date.now()/1000,target,active,connected:freshRuntime(),paused:!state.polling,startedAt:wsl.phase_started_unix});
    model.source=\x60${source}:${wsl.active_phase_dir||''}\x60;''',
     '''    const model=ProofEta.estimate(progress,{now:Date.now()/1000,target,active,connected,
      paused:!state.polling,startedAt:remote?.sample.started_at_unix ?? wsl.phase_started_unix});
    model.source=remote?source:\x60${source}:${wsl.active_phase_dir||''}\x60;
    model.remote=!!remote;'''),
    ('''    document.documentElement.dataset.stream=active&&freshRuntime()?'live':'quiet';
    $('eta-scope')''',
     '''    document.documentElement.dataset.stream=active&&connected?'live':'quiet';
    $('eta-heading').textContent=remote?'Live core checkpoint forecast · Hyperstack':'Live core checkpoint forecast · laptop';
    $('eta-scope')'''),
    ('''    $('eta-rate').textContent=model.rate?\x60${n(model.rate,2)} cores / min\x60:'Learning the current pace';''',
     '''    $('eta-rate').textContent=model.status==='tracking'?\x60${n(model.rate,2)} cores / min\x60:'Waiting for a current core rate';'''),
    ('''    $('eta-run-age').textContent=typeof wsl.latest_resource?.elapsed_s==='number'?\x60Phase elapsed ${formatDuration(wsl.latest_resource.elapsed_s)}\x60:'Phase elapsed unavailable';''',
     '''    $('eta-run-age').textContent=remote?
      \x60Lease elapsed ${formatDuration(remote.sample.sampled_at_unix-remote.sample.started_at_unix)}\x60:
      typeof wsl.latest_resource?.elapsed_s==='number'?\x60Phase elapsed ${formatDuration(wsl.latest_resource.elapsed_s)}\x60:'Phase elapsed unavailable';'''),
    ('''    $('eta-last-proof').textContent=latest?\x60Last ${latest.kind==='shard'?'core':'recursion'} proof · ${time(latest.t)}\x60:'Waiting for a new proof event';''',
     '''    $('eta-last-proof').textContent=remote?.sample.last_checkpoint_at_unix?
      \x60Last server checkpoint · ${time(remote.sample.last_checkpoint_at_unix)}\x60:
      latest?\x60Last ${latest.kind==='shard'?'core':'recursion'} proof · ${time(latest.t)}\x60:'Waiting for a new proof event';'''),
    ('''    if(!state.polling || !freshRuntime()) {
      $('eta-clock').textContent=state.polling?'Signal stale':'Display paused';$('eta-finish').textContent='Estimate held';return;
    }''',
     '''    const connected=model.remote?arkCloudSignal()?.fresh:freshRuntime();
    if(!state.polling || !connected) {
      document.documentElement.dataset.stream='quiet';
      $('eta-clock').textContent=state.polling?'Signal stale':'Display paused';$('eta-finish').textContent='Estimate held';return;
    }'''),
])

edit("prover-ui/web/index.html", [
    ('<h3 class="core-eta-heading">Live core checkpoint forecast</h3>',
     '<h3 class="core-eta-heading" id="eta-heading">Live core checkpoint forecast</h3>'),
])

for path, data in updates.items():
    path.write_bytes(data)

from pathlib import Path
import sys


checkout = Path(sys.argv[1]) / "prover-ui"
updates = {}


def edit(name, replacements):
    path = checkout / name
    data = path.read_bytes()
    newline = "\r\n" if b"\r\n" in data else "\n"
    source = data.decode().replace("\r\n", "\n")
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError(f"unexpected source in {name}")
        source = source.replace(before, after, 1)
    updates[path] = source.replace("\n", newline).encode()


edit("src/live_probe.py", [
    ('''MAX_JSON = 2 * 1024 * 1024''',
     '''MAX_JSON = 2 * 1024 * 1024
NOVA_PHASES = {
    b"mnr04-regtest": "Checking settlement in Bitcoin Core",
    b"mnr04-key-hash": "Deriving the Nova verification key",
    b"mnr04-prove": "Proving the clearing transaction",
    b"mnr04-verify": "Independently verifying the clearing proof",
    b"mnr04-route-key-hash": "Deriving the routed Nova verification key",
    b"mnr04-route-prove": "Proving the routed settlement",
    b"mnr04-route-verify": "Independently verifying the routed proof",
}'''),
    ('''def scan_provers():
    # Process names alone do not establish GPU use; report the observed executable.
    names = {"ark-prove-gpu-cached-gkr", "ark-prove-gpu", "nb3-prove-gpu", "nb3-prove"}
    processes = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            exe = os.readlink(proc / "exe").removesuffix(" (deleted)")
            if Path(exe).name not in names:
                continue
            stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            if stat[0] != "Z":
                processes.append({"pid": int(proc.name), "executable": exe,
                                  "start_ticks": int(stat[19]), "state": stat[0]})
        except (OSError, ValueError, IndexError):
            pass
    return processes[:16]''',
     '''def scan_provers(root=Path("/proc"), tracked_units=()):
    # Process names alone do not establish GPU use; report the observed executable.
    ark_names = {"ark-prove-gpu-cached-gkr", "ark-prove-gpu", "nb3-prove-gpu", "nb3-prove"}
    ark, nova = [], []
    for proc in root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            exe = os.readlink(proc / "exe").removesuffix(" (deleted)")
            name = Path(exe).name
            if name not in ark_names and name != "shz":
                continue
            stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            if stat[0] in {"Z", "X", "x"}:
                continue
            process = {"pid": int(proc.name), "executable": exe,
                       "start_ticks": int(stat[19]), "state": stat[0]}
            if name in ark_names:
                ark.append(process)
                continue
            with (proc / "cmdline").open("rb") as source:
                args = source.read(4096).split(b"\\0", 2)
            phase = NOVA_PHASES.get(args[1]) if len(args) == 3 else None
            if phase is None:
                continue
            groups = (proc / "cgroup").read_text().splitlines()
            unit = next((Path(group[3:]).name for group in groups if group.startswith("0::")), "")
            if unit in tracked_units:
                continue
            # A process may have exited or been replaced while sampling its command.
            after = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            if after[19] != stat[19] or after[0] in {"Z", "X", "x"}:
                continue
            cpu_seconds = (int(after[11]) + int(after[12])) / os.sysconf("SC_CLK_TCK")
            nova.append({
                "id": f"mnr04:{process['pid']}:{process['start_ticks']}",
                "kind": "mnr04", "title": "MNR-04 clearing proof", "network": "SatsHedgeZero",
                "backend": "Nova / CPU", "phase": phase, "status": "running", "running": True,
                "process": process, "cpu_seconds": cpu_seconds,
                "ram_bytes": max(0, int(after[21])) * os.sysconf("SC_PAGE_SIZE"),
                "unit": unit if unit.endswith(".service") else "Observed process",
            })
        except (OSError, ValueError, IndexError):
            pass
    return ark[:16], nova[:16]'''),
    ('''    return {"sampled_at_unix": time.time(), "reachable": True, "jobs": jobs,
            "ark_progress_path": str(ark_progress.resolve()) if ark_progress.is_file() else None,
            "ark_processes": scan_provers(), "source": "systemd + /proc + cgroup v2 + local audit files"}''',
     '''    ark, nova = scan_provers(tracked_units={job["unit"] for job in jobs if job["running"]})
    return {"sampled_at_unix": time.time(), "reachable": True, "jobs": jobs + nova,
            "ark_progress_path": str(ark_progress.resolve()) if ark_progress.is_file() else None,
            "ark_processes": ark, "source": "systemd + /proc + cgroup v2 + local audit files"}'''),
])

edit("web/app.js", [
    ('''        phase:job.phase,status:observedState(localFresh,activity),heardAt:localSample,
        details:'#runtime-panel',detailsLabel:'Process details'});''',
     '''        phase:job.phase,status:observedState(localFresh,activity),heardAt:localSample,
        metrics:job.kind==='mnr04'&&localFresh&&!paused?[
          ['CPU seconds',Number.isFinite(job.cpu_seconds)?Math.floor(job.cpu_seconds):null],
          ['Process RAM MiB',Number.isFinite(job.ram_bytes)?Math.floor(job.ram_bytes/2**20):null],
        ]:[],
        details:'#runtime-panel',detailsLabel:'Process details'});'''),
    ('''previous:new Map(), seen:new Set()''',
     '''previous:new Map(), workerAdvances:new Set(), seen:new Set()'''),
    ('''    let cpu=0, measured=false;
    for(const job of rt.jobs||[]){''',
     '''    let cpu=0, measured=false;
    const observed=new Map(), advances=new Set();
    for(const job of rt.jobs||[]){'''),
    ('''      if(prev && t>prev.t && job.cpu_seconds>=prev.cpu){cpu+=(job.cpu_seconds-prev.cpu)/(t-prev.t)*50;measured=true;}
      state.previous.set(key,{t,cpu:job.cpu_seconds});
    }
    state.history.push''',
     '''      if(prev && t>prev.t && job.cpu_seconds>=prev.cpu){
        cpu+=(job.cpu_seconds-prev.cpu)/(t-prev.t)*50;
        measured=true;
        if(Math.floor(job.cpu_seconds)>Math.floor(prev.cpu))advances.add(job.id);
      }
      observed.set(key,{t,cpu:job.cpu_seconds});
    }
    state.previous=observed;state.workerAdvances=advances;
    state.history.push'''),
    ('''<dd>${n(value)}</dd>''',
     '''<dd${label==='CPU seconds'&&job.status==='Running'&&state.workerAdvances.has(job.id)?' class="worker-increment"':''}>${n(value)}</dd>'''),
])

edit("web/styles.css", [
    ('''.checkpoint-new { animation:checkpoint-arrive .65s ease-out 1; }''',
     '''.checkpoint-new, .worker-increment { animation:checkpoint-arrive .65s ease-out 1; }'''),
])

edit("README.md", [
    ('''Default jobs are the current testnet4 tapleaf and legacy-payment units. To observe another proof run, configure its real unit, executable and output/audit paths:''',
     '''Default jobs are the current testnet4 tapleaf and legacy-payment units. The process probe also discovers supported local SatsHedgeZero MNR-04 commands, including the routed Nova profile. Its live-workers row reports the observed command stage, CPU time and process RAM. To observe another proof run, configure its real unit, executable and output/audit paths:'''),
])

edit("tests/test_live_probe.py", [
    ('''    def test_output_presence_does_not_verify_and_mutation_revokes_receipt(self):''',
     '''    def test_recognizes_only_live_nova_commands_and_deduplicates_configured_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            programs = {}

            def process(pid, exe, command, state="R"):
                proc = root / str(pid)
                proc.mkdir()
                programs[str(pid)] = "/var/tmp/bin/" + exe
                fields = ["0"] * 22
                fields[0], fields[11], fields[12], fields[19], fields[21] = state, "230", "70", "1234", "7"
                (proc / "stat").write_text(f"{pid} ({exe}) " + " ".join(fields))
                (proc / "cgroup").write_text("0::/system.slice/fixture.service\\n")
                (proc / "cmdline").write_bytes(b"\\0".join([exe.encode(), command, b"private-path", b""]))

            process(17, "shz", b"mnr04-route-prove")
            process(18, "shz", b"mnr04-route-prove", "Z")
            process(19, "shz", b"mnr04-oracle-external")
            process(20, "unrelated", b"mnr04-route-prove")
            process(21, "ark-prove-gpu", b"prove")
            with (
                patch.object(probe.os, "readlink", side_effect=lambda path: programs[path.parent.name]),
                patch.object(probe.os, "sysconf", side_effect={"SC_CLK_TCK": 100, "SC_PAGE_SIZE": 4096}.__getitem__, create=True),
            ):
                ark, nova = probe.scan_provers(root)
                self.assertEqual([entry["pid"] for entry in ark], [21])
                self.assertEqual([job["id"] for job in nova], ["mnr04:17:1234"])
                self.assertEqual(nova[0]["phase"], "Proving the routed settlement")
                self.assertEqual(nova[0]["cpu_seconds"], 3)
                self.assertEqual(nova[0]["ram_bytes"], 28672)
                self.assertNotIn("private-path", json.dumps(nova))
                self.assertEqual(probe.scan_provers(root, {"fixture.service"})[1], [])

    def test_output_presence_does_not_verify_and_mutation_revokes_receipt(self):'''),
])

edit("tests/ongoing_jobs.cjs", [
    ('''function sample(t, core, recursion, replayed) {''',
     '''test('observes a local Nova process alongside the A100 with independent CPU and RAM samples', () => {
  const job = {id: 'mnr04:17:1234', kind: 'mnr04', title: 'MNR-04 clearing proof',
    running: true, process: {pid: 17, start_ticks: 1234}, backend: 'Nova / CPU',
    phase: 'Proving the routed settlement', cpu_seconds: 8.8, ram_bytes: 423 * 2**20};
  const input = setup({local: [job]});
  input.ark.sample.nova_running = false;
  const [ark, nova] = ongoingJobs(input);
  assert.equal(ark.status, 'Running');
  assert.equal(nova.where, 'Local machine · Nova / CPU');
  assert.deepEqual(nova.metrics, [['CPU seconds', 8], ['Process RAM MiB', 423]]);
  const [, stale] = ongoingJobs({...input, localFresh: false});
  assert.equal(stale.status, 'Stale');
  assert.deepEqual(stale.metrics, []);
});

function sample(t, core, recursion, replayed) {'''),
])

for path, data in updates.items():
    path.write_bytes(data)

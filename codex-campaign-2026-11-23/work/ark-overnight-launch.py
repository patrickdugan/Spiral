"""Gate one eight-hour Spot launch on staged bytes, a settled top-up, and durable export."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tarfile
import time

WORK = Path(__file__).resolve().parent
ARK = WORK.parents[2] / "2026-11-15/new-chat/outputs/zk-rusto-no-bitcoino-ark/Ark"
SECONDS = 8 * 3600
BUFFER = 0.75
TTL = SECONDS + 1800
MIN_SETTLED = 10.30


def run_local_check(pilot, stage, command, log, timeout=None):
    pilot.note(stage=stage)
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(subprocess.run, command, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=timeout, check=False)
        while not result.done():
            try:
                return result.result(timeout=10)
            except TimeoutError:
                try:
                    pilot.note(stage=stage)
                except OSError:
                    pass
        return result.result()


def retrieve_completed_proof(pilot, archive_path):
    with tarfile.open(archive_path, "r:gz") as archive:
        record = next((item for item in archive if item.name.removeprefix("./") == "compressed.sha256"), None)
        if record is None:
            return
        if not record.isfile() or record.size > 200:
            raise ValueError("invalid compressed proof digest record")
        expected = archive.extractfile(record).read().decode("ascii").split()[0]
    if len(expected)!=64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("invalid compressed proof digest")
    length = pilot.store.head_object(Bucket=pilot.name, Key="compressed.bin")["ContentLength"]
    if not 0 < length <= 512 * 1024**2:
        raise RuntimeError("compressed proof exceeded the local retrieval budget")
    proof_dir = Path(r"D:\Codex-offload") / ("ark-overnight-proof-" + pilot.name[-10:])
    if proof_dir.resolve() != proof_dir or not proof_dir.parent.is_dir():
        raise ValueError("unexpected proof staging location")
    proof_dir.mkdir(exist_ok=True)
    target = proof_dir / "compressed.bin"
    partial = target.with_suffix(".part")
    digest = hashlib.sha256()
    step = 2 * 1024**2
    with partial.open("xb") as file:
        for offset in range(0,length,step):
            end = min(offset+step,length)-1
            for attempt in range(4):
                try:
                    obj = pilot.store.get_object(Bucket=pilot.name, Key="compressed.bin", Range=f"bytes={offset}-{end}")
                    with obj["Body"] as response:
                        data = response.read()
                    if len(data)==end-offset+1:
                        break
                except Exception:
                    pass
                time.sleep(attempt+1)
            else:
                raise RuntimeError("compressed proof range download failed")
            digest.update(data)
            file.write(data)
    if digest.hexdigest()!=expected:
        raise RuntimeError("compressed proof differs from the GPU worker's digest")
    partial.rename(target)
    local_root="/mnt/c/Users/patri/Documents/Codex/2026-11-23/the-goal-is-paused-at-the/work"
    proof_wsl = "/mnt/d/Codex-offload/" + proof_dir.name
    with (pilot.run_dir/"downstream-verification.log").open("wb") as log:
        command=["wsl.exe","-u","root","--","systemd-run",
                 "--unit=ark-overnight-sdk-m13-"+pilot.name[-10:],"--wait","--pipe",
                 "-p","CPUQuota=100%","-p","MemoryMax=2G","-p","MemorySwapMax=4G",
                 "/bin/bash",local_root+"/ark-overnight-verify.sh",proof_wsl]
        check = run_local_check(pilot, "overnight_sdk_m13_verification", command, log, timeout=14400)
    pilot.note(sdk_m13_independent_exit=check.returncode,compressed_sha256=expected)
    if check.returncode or not (proof_dir / "independent-sdk-m13-passed").is_file():
        pilot.note(stage="overnight_verification_failed")
        raise RuntimeError("Independent SDK/M13 verification did not pass")

    with (pilot.run_dir / "m14-evaluation.log").open("wb") as log:
        command = ["wsl.exe", "-u", "root", "--", "systemd-run",
                   "--unit=ark-overnight-m14-" + pilot.name[-10:], "--wait", "--pipe",
                   "-p", "CPUQuota=100%", "-p", "MemoryHigh=1G", "-p", "MemoryMax=2G", "-p", "MemorySwapMax=4G",
                   "/bin/bash", local_root + "/ark-overnight-m14.sh", proof_wsl]
        checked = run_local_check(pilot, "overnight_m14_evaluation", command, log)
    pilot.note(m14_independent_exit=checked.returncode)
    if checked.returncode or not (proof_dir / "independent-m14-passed").is_file():
        pilot.note(stage="overnight_verification_failed")
        raise RuntimeError("Independent M14 evaluation did not pass")
    pilot.note(stage="overnight_offchain_proof_verified")
    publisher = runpy.run_path(str(WORK / "publish-ark-verified-proof.py"))
    publisher["publish_verified"](pilot, proof_dir, expected)

def launch_overnight(pilot, index):
    pilot.flavor = "n3-A100x1-spot"
    pilot.price_sku = "A100-80G-PCIe-spot"
    pilot.hourly_ceiling = 1.10

    def url(key, method="get_object"):
        return pilot.store.generate_presigned_url(method, Params={"Bucket": pilot.name, "Key": key},
                                                 ExpiresIn=TTL)

    def send(key, data):
        pilot.store.put_object(Bucket=pilot.name, Key=key, Body=data)
        return hashlib.sha256(data).hexdigest()

    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w:gz") as tar:
        for source in (WORK / "ark-overnight-worker.py", WORK / "ark-overnight-trial.sh",
                       WORK / "ark-a100-heartbeat.py", ARK / "scripts/prover_cgroup_sample.py"):
            data = source.read_bytes().replace(b"\r\n", b"\n")
            entry = tarfile.TarInfo(source.name)
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
    runner_sha = send("runner.tar.gz", bundle.getvalue())

    # Generate URLs only after the top-up is recognized so all upload slots
    # remain valid until the last checkpoint export.
    money_cutoff = time.monotonic() + 1800
    while True:
        credit = float(pilot.api("GET", "billing/user-credit/credit")["data"]["credit"])
        rates = {record["name"]: float(record["value"]) for record in pilot.api("GET", "pricebook")}
        hourly = rates[pilot.price_sku] + rates["PublicIP"]
        if not 0 < hourly <= pilot.hourly_ceiling:
            raise RuntimeError("spot account rate rose above the approved estimate")
        if credit >= max(MIN_SETTLED, hourly * 8 + BUFFER):
            break
        if time.monotonic() >= money_cutoff:
            raise TimeoutError("the authorized top-up has not cleared")
        time.sleep(30)

    stock_cutoff = time.monotonic() + 7200
    while True:
        groups = pilot.api("GET", "core/stocks")["stocks"]
        models = (m for group in groups if group["region"] == "CANADA-1" for m in group["models"])
        if any(m["model"] == pilot.price_sku and int(m["configurations"]["1x"]) > 0 for m in models):
            break
        pilot.note(stage="overnight_waiting_stock")
        if time.monotonic() >= stock_cutoff:
            raise TimeoutError("no single Canada spot A100 became available")
        time.sleep(90)
    if pilot.inventory():
        raise RuntimeError("existing VM found before overnight allocation")
    config = {
        "kit": {"url":url("kit.tar.gz"), "bytes":pilot.artifact.stat().st_size, "sha256":pilot.kit_sha},
        "seed": {**index, "parts":[{**row, "url":url(row["key"])} for row in index["parts"]]},
        "output_urls": [url(f"out/{i:06}.part","put_object") for i in range(2048)],
        "index_url": url("out/index.json","put_object"),
    }
    transport_sha = send("transport.json", json.dumps(config, separators=(",",":")).encode())
    ready = pilot.run_dir / "watchdog.ready"
    state = pilot.run_dir / "state.json"
    credential_path = str(Path(sys.argv[1]).resolve(strict=True))
    with (pilot.run_dir / "watchdog.log").open("wb") as log:
        guard = subprocess.Popen(
            [sys.executable, str(WORK / "ark-overnight-watchdog.py"), str(state),
             credential_path, str(ready), pilot.name, str(SECONDS)], stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )
    for _ in range(20):
        if ready.exists():
            break
        if guard.poll() is not None:
            raise RuntimeError("billing watchdog exited before provisioning")
        time.sleep(0.5)
    else:
        raise RuntimeError("billing watchdog was not confirmed")
    deadline = int(time.time()) + SECONDS - 130
    pilot.cutoff = time.monotonic() + SECONDS - 115
    pilot.note(stage="overnight_requested", lease_ends_at_unix=deadline, max_billed_seconds=SECONDS,
               spot=True, rate_usd_per_hour=hourly)
    values = {
        "transport_url":url("transport.json"), "transport_sha":transport_sha,
        "runner_url":url("runner.tar.gz"), "runner_sha":runner_sha,
        "status_url":url("status.json","put_object"), "result_url":url("results.tar.gz","put_object"),
        "compressed_url":url("compressed.bin","put_object"),
        "release_sha":hashlib.sha256(pilot.release.read_bytes()).hexdigest(),
        "deadline":str(deadline),
    }
    user_data = "#!/usr/bin/env bash\n" + "\n".join(f"{k}={shlex.quote(v)}" for k,v in values.items())
    user_data += "\n" + (WORK / "ark-overnight-bootstrap.sh").read_text(encoding="utf-8")
    pilot.launch(user_data)
    # Status updates feed the app. The checkpoint index is a separate object and
    # remains recoverable even if the spot process disappears mid-export.
    latest = None
    check_at = 0
    boot_deadline = time.monotonic() + 1800
    result = None
    try:
        while time.monotonic() < pilot.cutoff - 35:
            try:
                if time.monotonic() >= check_at:
                    check_at = time.monotonic() + 60
                    vm = pilot.vm(missing_ok=True)
                    if not vm or vm["status"] in {"DELETED","FAILED","ERROR","HIBERNATED","SHUTOFF"}:
                        break
                    if any(rule.get("direction","").lower()=="ingress" for rule in vm.get("security_rules",[])):
                        raise ValueError("unexpected ingress rule")
                status = pilot.status()
            except (OSError, RuntimeError):
                time.sleep(12)
                continue
            if status:
                stage = status["stage"]
                prepare_phase = status.get("prepare_phase") if stage == "preparing_inputs" else None
                phase_key = (stage, prepare_phase)
                if phase_key != latest:
                    pilot.note(stage=stage, prepare_phase=prepare_phase, ark_cgroup=status.get("ark_cgroup"))
                    if not stage.startswith("ark_heartbeat|"):
                        print(json.dumps({"stage": stage, "prepare_phase": prepare_phase, "vm_id": pilot.vm_id}), flush=True)
                    latest = phase_key
                if stage == "finished":
                    result = status
                    break
                if stage == "failed":
                    print(json.dumps({"stage": stage, "phase": status.get("phase")}), flush=True)
                    break
            elif latest is None and time.monotonic() > boot_deadline:
                break
            time.sleep(8)
    finally:
        pilot.cleanup()
        # Fetch the evidence after deletion. The whole recovery snapshot remains
        # in the private bucket for the next resume.
        try:
            pilot.store.download_file(pilot.name, "out/index.json", str(pilot.run_dir / "durable-memo-index.json"))
        except Exception:
            pass
        if result:
            path = pilot.run_dir / "results.tar.gz"
            size = int(result["artifact_bytes"])
            if not 0 < size <= 4 * 1024**2:
                raise RuntimeError("overnight evidence exceeds the bounded result size")
            pilot.store.download_file(pilot.name, "results.tar.gz", str(path))
            if path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != result["artifact_sha256"]:
                raise RuntimeError("retrieved overnight evidence hash mismatch")
            pilot.note(stage="results_retrieved", result_sha256=result["artifact_sha256"],
                       checkpoint_export_finished=result["checkpoint_export_finished"])
        pilot.store.delete_object(Bucket=pilot.name, Key="transport.json")
        try:
            if result:
                retrieve_completed_proof(pilot, path)
        finally:
            try:
                release = runpy.run_path(str(WORK / "publish-ark-spot-delta.py"))
                release["publish_spot"](pilot, index["sha256"])
            except Exception as error:
                pilot.note(spot_release_error=type(error).__name__)
                print(json.dumps({"stage": "spot_release_pending", "error": type(error).__name__}), flush=True)

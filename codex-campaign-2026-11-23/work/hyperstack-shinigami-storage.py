"""Retry the approved Hyperstack proof pilot using outbound HTTPS only."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK / "hyperstack-python"))
import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.exceptions import ClientError

common = runpy.run_path(str(WORK / "hyperstack-shinigami-pilot.py"))
Pilot = common["Pilot"]
emit = common["emit"]
file_digest = common["file_digest"]
windows_case_path = common["windows_case_path"]
iteration_until = common["iteration_until"]
KEYS = ("kit.tar.gz", "shinigami-case.json", "shinigami-case.args.json", "status.json",
        "benchmark.json", "verifier-input.json")
FLAVOR = "n3-A100x1"
KIT_SHA256 = "ada77fb81e9f18d619ba2ffdb188b20497b0d73d6f7957f6222728636337a9b4"
TELEMETRY = WORK / "hyperstack-benchmark.json"


class StoragePilot(Pilot):
    object_keys = KEYS
    flavor = FLAVOR
    price_sku = "A100-80G-PCIe"
    hourly_ceiling = 1.50

    def __init__(self, credential, artifact, results):
        super().__init__(credential, artifact, results)
        self.cutoff = time.monotonic() + 3200
        self.storage_id = None
        self.store = None
        self.owns_bucket = False
        self.storage_requested = False
        self.metrics = {}
        self.rate = None
        self.started_at = None

    def telemetry(self, stage, *, active):
        if self.vm_id is None:
            return
        snapshot = {
            "schema": "rbzk/hyperstack-benchmark/v1", "vm_id": self.vm_id,
            "stage": stage, "active": active, "sampled_at_unix": int(time.time()),
            "started_at_unix": self.started_at, "rate_usd_per_hour": self.rate,
            **self.metrics,
        }
        temporary = TELEMETRY.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
        for attempt in range(3):
            try:
                temporary.replace(TELEMETRY)
                break
            except PermissionError:
                if attempt == 2:
                    return
                time.sleep(0.05)

    def storage_keys(self):
        return [key for key in self.api("GET", "object-storage/access-keys")["access_keys"]
                if key["description"] == self.name and key["region"] == "CANADA-1"]

    def initialize_storage(self):
        url = "object-storage/access-keys"
        self.storage_requested = True
        reply = self.api("POST", url, {"region": "CANADA-1", "description": self.name})
        key, = self.storage_keys()
        self.storage_id = key["id"]
        data = next((entry for entry in (reply, reply.get("data"), reply.get("access_key"))
                     if isinstance(entry, dict) and "secret_key" in entry), None)
        if data is None or data["access_key"] != key["access_key"]:
            raise RuntimeError("Ephemeral storage key could not be reconciled")
        self.store = boto3.client(
            "s3", endpoint_url="https://ca1.obj.nexgencloud.io", region_name="us-east-1",
            aws_access_key_id=data["access_key"], aws_secret_access_key=data["secret_key"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          request_checksum_calculation="when_required", response_checksum_validation="when_required",
                          connect_timeout=8, read_timeout=25, retries={"max_attempts": 2}),
        )
        self.store.create_bucket(Bucket=self.name)
        self.owns_bucket = True
        self.note(stage="private_transport_ready", storage_key_id=self.storage_id)

    def stage_initial_inputs(self):
        part_size = 5 * 1024**2
        self.store.upload_file(str(self.artifact), self.name, "kit.tar.gz", Config=TransferConfig(
            multipart_threshold=part_size, multipart_chunksize=part_size, max_concurrency=2,
        ))
        if self.store.head_object(Bucket=self.name, Key="kit.tar.gz")["ContentLength"] != self.artifact.stat().st_size:
            raise RuntimeError("Stored archive size differs from the pinned archive")
        emit(stage="pinned_kit_staged")
        self.begin_fixture()
        event = self.fixture_ready()
        for field in ("case_file", "arguments_file"):
            path = windows_case_path(event[field])
            self.store.put_object(Bucket=self.name, Key=path.name, Body=path.read_bytes())
        return event

    def prepare_storage(self):
        self.initialize_storage()
        return self.stage_initial_inputs()

    def cloud_init(self, limit):
        urls = {}
        for name in KEYS:
            operation = "get_object" if name in KEYS[:3] else "put_object"
            urls[name] = self.store.generate_presigned_url(
                operation, Params={"Bucket": self.name, "Key": name}, ExpiresIn=3300)
        q = shlex.quote
        sha = file_digest(self.artifact)
        return f"""#!/bin/bash
set -Eeuo pipefail
umask 077
dir=$(mktemp -d /var/tmp/cashu-shinigami.XXXXXXXX)
cd "$dir"
status() {{
    python3 - "$1" "$2" "$dir" > "$dir/status.json" <<'PY'
import json, os, pathlib, sys, time
stage, code, directory = sys.argv[1:]
root = pathlib.Path(directory)
data = {{"stage": stage, "exit_code": int(code), "sampled_at_unix": int(time.time())}}
gpu = root / "gpu.txt"
if gpu.exists():
    data["a100_confirmed"] = "A100" in gpu.read_text()
report = root / "run/report.json"
if report.exists():
    benchmark = json.loads(report.read_text())
    data.update(phase=benchmark["status"], threads=benchmark["rayon_threads"])
mem = {{line.split(":", 1)[0]: int(line.split()[1]) for line in pathlib.Path("/proc/meminfo").read_text().splitlines() if line.startswith(("MemTotal:", "MemAvailable:"))}}
data.update(logical_cpus=len(os.sched_getaffinity(0)), host_ram_gib=round(mem["MemTotal"]/1048576, 2), host_ram_used_gib=round((mem["MemTotal"]-mem["MemAvailable"])/1048576, 2))
print(json.dumps(data))
PY
    curl -fsS --retry 1 --connect-timeout 5 --max-time 12 -T "$dir/status.json" {q(urls["status.json"])}
}}
finish() {{
    code=$?
    trap - EXIT
    if test -n "${{sampler:-}}"; then kill "$sampler" 2>/dev/null || true; wait "$sampler" || true; fi
    if test -s run/verifier-input.json; then
        curl -fsS --retry 2 --connect-timeout 10 --max-time 45 -T run/verifier-input.json {q(urls["verifier-input.json"])} || code=1
    fi
    if test -s run/report.json; then
        curl -fsS --retry 2 --connect-timeout 10 --max-time 25 -T run/report.json {q(urls["benchmark.json"])} || code=1
    fi
    status finished "$code" || true
    exit "$code"
}}
trap finish EXIT
status booted 0
if ! test -x /usr/bin/time; then
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get update -qq
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get install -y -qq time
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader > gpu.txt
grep -q A100 gpu.txt
curl -fsS --retry 2 --connect-timeout 10 --max-time 150 -o kit.tar.gz {q(urls["kit.tar.gz"])}
printf '%s  %s\\n' {q(sha)} kit.tar.gz | sha256sum -c
tar -xzf kit.tar.gz
curl -fsS --retry 2 --connect-timeout 10 --max-time 25 -o shinigami-case.json {q(urls["shinigami-case.json"])}
curl -fsS --retry 2 --connect-timeout 10 --max-time 25 -o shinigami-case.args.json {q(urls["shinigami-case.args.json"])}
status benchmark_started 0
sampler=''
(trap - EXIT; while true; do status benchmark_running 0 || true; sleep 8; done) &
sampler=$!
cd shinigami-cpu-pilot
threads=$(nproc)
if (( threads > 16 )); then threads=16; fi
python3 -B benchmarks/shinigami/run.py ../run --regtest-case ../shinigami-case.json --threads "$threads" --max-seconds {limit}
cd "$dir"
""".replace('test -s run/', 'test -s "$dir"/run/').replace('-T run/', '-T "$dir"/run/')

    def launch(self, user_data):
        rates = {row["name"]: float(row["value"]) for row in self.api("GET", "pricebook")}
        hourly = rates[self.price_sku] + rates["PublicIP"]
        if not 0 < hourly <= self.hourly_ceiling:
            raise RuntimeError("The A100 rate exceeds the approved pilot budget")
        if any(row["name"].startswith("cashu-shinigami-pilot-") for row in self.inventory()):
            raise RuntimeError("A previous trial still exists")
        subprocess.run(["ssh-keygen.exe", "-q", "-t", "ed25519", "-f", str(self.ssh_key),
                        "-N", "", "-C", self.name], check=True, timeout=12)
        self.api("POST", "core/keypairs", {
            "name": self.name, "environment_name": "default-CANADA-1",
            "public_key": self.ssh_key.with_suffix(".pub").read_text().strip(),
        })
        key, = (k for k in self.api("GET", "core/keypairs")["keypairs"]
                if k["name"] == self.name and k["environment"]["name"] == "default-CANADA-1")
        self.key_id = key["id"]
        self.rate = hourly
        self.started_at = int(time.time())
        self.note(stage="storage_vm_requested", rate_usd_per_hour=hourly, requested_at=self.started_at,
                  flavor=self.flavor)
        self.submitted = True
        reply = self.api("POST", "core/virtual-machines", {
            "environment_name": "default-CANADA-1", "name": self.name, "count": 1,
            "image_name": common["IMAGE"], "flavor_name": self.flavor,
            "key_name": self.name, "assign_floating_ip": True, "security_rules": [],
            "user_data": user_data,
        })
        instance, = reply["instances"]
        if instance["name"] != self.name:
            raise RuntimeError("Unexpected instance identity")
        self.vm_id = int(instance["id"])
        self.note(stage="storage_vm_provisioned")
        self.telemetry("provisioning", active=True)
        emit(stage="provisioned", vm_id=self.vm_id, route="outbound_https_only", rate_usd_per_hour=hourly,
             flavor=self.flavor, proving_backend="CPU")

    def status(self):
        try:
            with self.store.get_object(Bucket=self.name, Key="status.json")["Body"] as body:
                return json.loads(body.read(8192))
        except ClientError as error:
            if error.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
                return None
            raise

    def run(self):
        if file_digest(self.artifact) != KIT_SHA256:
            raise RuntimeError("Pilot archive differs from the approved pinned archive")
        if any(row["name"].startswith("cashu-shinigami-pilot-") for row in self.inventory()):
            raise RuntimeError("A previous trial still exists")
        event = self.prepare_storage()
        limit = min(event["wait_seconds"] - 430, int(self.cutoff - time.monotonic() - 450))
        if limit < 600:
            raise TimeoutError("Too little time for the approved retry")
        self.launch(self.cloud_init(limit))
        last = None
        started = time.monotonic()
        next_check = started
        for _ in iteration_until(self.cutoff - 75):
            if time.monotonic() >= next_check:
                vm = self.vm(missing_ok=True)
                if vm is None or vm["status"] in ("DELETED", "ERROR", "FAILED"):
                    raise RuntimeError("Hyperstack trial stopped before the proof was retrieved")
                if any(rule.get("direction", "").lower() == "ingress" for rule in vm.get("security_rules", [])):
                    raise RuntimeError("Unexpected inbound rule on the outbound-only VM")
                if last is None:
                    self.telemetry("provisioning", active=True)
                next_check = time.monotonic() + 30
            stage = self.status()
            if stage is None:
                if time.monotonic() - started > 380:
                    raise TimeoutError("Cloud-init did not reach private object storage")
                continue
            for field in ("a100_confirmed", "logical_cpus", "threads", "host_ram_gib", "host_ram_used_gib"):
                if field in stage:
                    self.metrics[field] = stage[field]
            phase = stage.get("phase") or stage["stage"]
            remote_time = stage.get("sampled_at_unix", 0)
            if abs(time.time() - remote_time) <= 35:
                self.telemetry(phase if stage["stage"] != "finished" else "retrieving", active=True)
            if phase != last:
                last = phase
                self.note(stage=last)
                emit(stage=last, vm_id=self.vm_id, route="outbound_https_only")
            if stage["stage"] == "finished":
                break
        else:
            raise TimeoutError("Proof did not finish within the remaining budget")
        report_path = self.run_dir / "benchmark.json"
        self.store.download_file(self.name, "benchmark.json", str(report_path))
        report = json.loads(report_path.read_text())
        if stage["exit_code"] != 0 or report["status"] != "fresh_proof_independently_verified":
            raise RuntimeError(f"Cloud benchmark ended at {report['status']}; see benchmark.json")
        proof = report["phases"]["prove"]
        self.metrics.update(prove_seconds=proof["elapsed_seconds"], peak_prove_ram_gib=round(proof["peak_rss_kib"]/1048576, 2))
        target = windows_case_path(event["proof_target"])
        pending = target.with_suffix(".partial")
        self.store.download_file(self.name, "verifier-input.json", str(pending))
        if file_digest(pending) != report["verifier_input_sha256"]:
            raise RuntimeError("Transferred proof hash differs from the verified cloud proof")
        pending.replace(target)
        self.telemetry("local_verification", active=True)
        emit(stage="cloud_proof_verified", proof_sha256=report["verifier_input_sha256"], phases=report["phases"])
        self.fixture.wait(timeout=max(30, min(120, int(self.cutoff - time.monotonic()))))
        if self.fixture.returncode:
            raise RuntimeError("Local proof admission or offline reserve payout failed; see fixture.log")
        self.note(stage="local_issuance_and_reserve_verified")
        emit(stage="local_issuance_and_reserve_verified")

    def clean_storage(self):
        if self.owns_bucket:
            for name in self.object_keys:
                self.store.delete_object(Bucket=self.name, Key=name)
            self.store.delete_bucket(Bucket=self.name)
            emit(stage="temporary_bucket_deleted")
        if self.storage_requested:
            for key in self.storage_keys():
                self.api("DELETE", f"object-storage/access-keys/{int(key['id'])}", missing_ok=True)
            if self.storage_keys():
                raise RuntimeError("Temporary storage credential deletion is unconfirmed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    pilot = StoragePilot(args.key_file.read_text(encoding="utf-8-sig").strip(),
                         args.kit.resolve(), args.results.resolve())
    emit(stage="pilot_preflight", result_dir=str(pilot.run_dir))
    final = "failed"
    try:
        pilot.run()
        final = "verified"
    finally:
        try:
            try:
                pilot.cleanup()
            finally:
                try:
                    pilot.stop_fixture()
                finally:
                    pilot.clean_storage()
        except Exception:
            final = "cleanup_unconfirmed"
            raise
        finally:
            pilot.telemetry(final, active=False)


if __name__ == "__main__":
    main()

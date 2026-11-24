"""Finish both Shinigami proofs against a single isolated regtest fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import runpy
import shlex
import subprocess
import time


WORK = Path(__file__).resolve().parent
storage = runpy.run_path(str(WORK / "hyperstack-shinigami-storage.py"))
StoragePilot = storage["StoragePilot"]
WSL = storage["common"]["WSL"]
file_digest = storage["file_digest"]
emit = storage["emit"]
iteration_until = storage["iteration_until"]
windows_case_path = storage["windows_case_path"]
PROOF_LIMIT = 64 * 1024**2
REDEMPTION_KEYS = ("redemption-args.json", "redemption-statement.json", "redemption-ready",
                   "redemption-benchmark.json", "redemption-verifier-input.json")


class PairedPilot(StoragePilot):
    object_keys = StoragePilot.object_keys + REDEMPTION_KEYS + ("issuance-ready",)

    def begin_fixture(self):
        super().begin_fixture(("--shinigami-redemption-bundle", self.local_bundle,
                               "--shinigami-redemption-external", "3100"), self.local_bundle)

    def telemetry(self, stage, *, active):
        self.note(stage=stage, active=active)

    def cloud_init(self, limit):
        inputs = (*self.object_keys[:3], *REDEMPTION_KEYS[:3], "issuance-ready")
        urls = {}
        for key in self.object_keys:
            action = "get_object" if key in inputs else "put_object"
            urls[key] = shlex.quote(self.store.generate_presigned_url(
                action, Params={"Bucket": self.name, "Key": key}, ExpiresIn=3300))
        digest = file_digest(self.artifact)
        return f'''#!/bin/bash
set -Eeuo pipefail
umask 077
dir=$(mktemp -d /var/tmp/cashu-paired.XXXXXXXX)
cd "$dir"
download() {{ curl -fsS --retry 1 --connect-timeout 7 --max-time "$1" -o "$2" "$3"; }}
upload() {{ curl -fsS --retry 1 --connect-timeout 7 --max-time 75 -T "$1" "$2"; }}
status() {{
    printf '{{"stage":"%s","exit_code":%s,"sampled_at_unix":%s}}\\n' "$1" "$2" "$(date +%s)" > "$dir/status.json"
    upload "$dir/status.json" {urls['status.json']}
}}
trap 'code=$?; if ((code)); then status failed "$code" || true; fi' EXIT
budget() {{
    local remaining=$(({limit} - SECONDS))
    if (( remaining < 30 )); then return 1; fi
    printf '%s\\n' "$remaining"
}}
run_case() {{
    local name=$1; shift
    local seconds
    seconds=$(budget)
    status "${{name}}_started" 0
    python3 -B "$dir/shinigami-cpu-pilot/benchmarks/shinigami/run.py" "$dir/$name" \\
        "$@" --threads "$threads" --max-seconds "$seconds"
}}
await_input() {{
    until download 16 "$1" "$2" 2>/dev/null; do
        budget >/dev/null
        sleep 5
    done
}}
status booted 0
if ! test -x /usr/bin/time; then
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get update -qq
    DEBIAN_FRONTEND=noninteractive timeout 120 apt-get install -y -qq time
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader > gpu.txt
grep -q A100 gpu.txt
threads=$(nproc)
if (( threads > 16 )); then threads=16; fi
await_input issuance-ready {urls['issuance-ready']}
download 150 kit.tar.gz {urls['kit.tar.gz']}
printf '%s  %s\\n' {digest} kit.tar.gz | sha256sum -c
tar -xzf kit.tar.gz
download 30 shinigami-case.json {urls['shinigami-case.json']}
download 30 shinigami-case.args.json {urls['shinigami-case.args.json']}
run_case issuance --regtest-case "$dir/shinigami-case.json"
upload issuance/report.json {urls['benchmark.json']}
upload issuance/verifier-input.json {urls['verifier-input.json']}
status issuance_proof_ready 0
await_input redemption-ready {urls['redemption-ready']}
mkdir redemption-case
download 30 redemption-case/honest.args.json {urls['redemption-args.json']}
download 30 redemption-case/statement.json {urls['redemption-statement.json']}
sha256sum -c redemption-ready
run_case redemption --redemption-case "$dir/redemption-case"
upload redemption/report.json {urls['redemption-benchmark.json']}
upload redemption/verifier-input.json {urls['redemption-verifier-input.json']}
status redemption_proof_ready 0
'''

    def wait_for_worker(self, desired, deadline):
        last = None
        next_vm_check = 0
        boot_deadline = time.monotonic() + 420
        for _ in iteration_until(deadline):
            if time.monotonic() >= next_vm_check:
                vm = self.vm(missing_ok=True)
                if vm is None or vm["status"] in ("DELETED", "ERROR", "FAILED"):
                    raise RuntimeError("The paired worker stopped")
                if any(rule["direction"].lower() == "ingress" for rule in (vm.get("security_rules") or [])):
                    raise RuntimeError("Unexpected VM ingress rule")
                next_vm_check = time.monotonic() + 30
            status = self.status()
            if not status:
                if last is None and time.monotonic() >= boot_deadline:
                    raise TimeoutError("The worker did not report its boot status")
                continue
            stage = status["stage"]
            if stage != last:
                last = stage
                self.telemetry(stage, active=True)
                emit(stage=stage, vm_id=self.vm_id)
            if stage == "failed":
                raise RuntimeError(f"Worker failed before {desired}")
            if stage == desired:
                return
        raise TimeoutError(f"No worker result for {desired} within the pilot budget")

    def fixture_event(self, status):
        deadline = min(self.cutoff - 180, time.monotonic() + 180)
        while time.monotonic() < deadline and self.fixture.poll() is None:
            try:
                event = self.fixture_output.get(timeout=2)
            except queue.Empty:
                continue
            if event.get("status") == status:
                return event
        raise RuntimeError(f"The live Core/CDK fixture did not reach {status}")

    def stage_redemption(self, event):
        root = self.redemption_path(event["case_dir"])
        checksum_lines = []
        for key, basename in zip(REDEMPTION_KEYS, ("honest.args.json", "statement.json")):
            path = root / basename
            if path.stat().st_size > 16384:
                raise ValueError("Unexpected redemption proof input size")
            data = path.read_bytes()
            self.store.put_object(Bucket=self.name, Key=key, Body=data)
            checksum_lines.append(f"{hashlib.sha256(data).hexdigest()}  redemption-case/{basename}\n")
        self.store.put_object(Bucket=self.name, Key="redemption-ready", Body="".join(checksum_lines).encode())

    @staticmethod
    def redemption_path(path):
        root = Path(storage["common"]["LINUX_BASE"].replace("/mnt/c/", "C:/", 1))
        runtime = (root / "outputs/ark-cashu-proofdesk/.runtime").resolve()
        if not path.startswith("/mnt/c/"):
            raise ValueError("Expected the isolated Core/CDK runtime")
        absolute = Path(path.replace("/mnt/c/", "C:/", 1)).resolve()
        relative = absolute.relative_to(runtime)
        if len(relative.parts) != 2 or not relative.parts[0].startswith("regtest-stack-"):
            raise ValueError("Redemption path is outside the isolated Core/CDK fixture")
        return absolute

    def return_proof(self, report_key, proof_key, target, case):
        report_path = self.run_dir / report_key
        self.store.download_file(self.name, report_key, str(report_path))
        report = json.loads(report_path.read_text())
        required = {"execute": 0, "prove": 0, "verify": 0,
                    "reject_changed_anchor_amount": 1, "reject_changed_commitment": 1}
        if (report["status"] != "fresh_proof_independently_verified" or report["case"] != case
                or any(report["phases"][name]["exit_code"] != code for name, code in required.items())):
            raise RuntimeError(f"The cloud worker did not verify the {case} proof")
        length = self.store.head_object(Bucket=self.name, Key=proof_key)["ContentLength"]
        if not 0 < length <= PROOF_LIMIT:
            raise ValueError("Returned proof exceeds the approved size")
        pending = target.with_suffix(".partial")
        self.store.download_file(self.name, proof_key, str(pending))
        if file_digest(pending) != report["verifier_input_sha256"]:
            raise ValueError("Returned proof does not match the verified remote artifact")
        pending.replace(target)
        return report

    def run(self):
        if file_digest(self.artifact) != storage["KIT_SHA256"]:
            raise ValueError("The proof kit does not match its pinned archive")
        if any(vm["name"].startswith("cashu-shinigami-pilot-") for vm in self.inventory()):
            raise RuntimeError("Reconcile the previous pilot before launching another worker")
        if not any(model["model"] == self.price_sku and model["configurations"]["1x"] > 0
                   for region in self.api("GET", "core/stocks")["stocks"] if region["region"] == "CANADA-1"
                   for model in region["models"]):
            raise RuntimeError(f"Canada has no single-card {self.price_sku} capacity")
        self.initialize_storage()
        limit = int(self.cutoff - time.monotonic() - 250)
        if limit < 900:
            raise TimeoutError("Insufficient time within the one-hour limit")
        self.launch(self.cloud_init(limit))
        first = self.stage_initial_inputs()
        self.store.put_object(Bucket=self.name, Key="issuance-ready", Body=b"ready\n")
        self.wait_for_worker("issuance_proof_ready", self.cutoff - 600)
        issuance = self.return_proof("benchmark.json", "verifier-input.json",
                                     windows_case_path(first["proof_target"]), "fresh_cashu_regtest")
        receipt = self.fixture_event("waiting_for_redemption_proof")
        self.stage_redemption(receipt)
        self.wait_for_worker("redemption_proof_ready", self.cutoff - 120)
        redemption = self.return_proof("redemption-benchmark.json", "redemption-verifier-input.json",
                                       self.redemption_path(receipt["proof_target"]), "fresh_cashu_redemption")
        try:
            self.fixture.wait(timeout=max(10, min(90, int(self.cutoff - time.monotonic()))))
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("The local redemption audit did not finish in time") from error
        if self.fixture.returncode:
            raise RuntimeError("Local verification or chain binding failed; see fixture.log")
        log = (self.run_dir / "fixture.log").read_text(encoding="utf-8")
        for line in log.splitlines():
            if line.startswith('{"status": "redemption_proof_independently_verified_on_regtest"'):
                verified = json.loads(line)
                if verified["proof_sha256"] == redemption["verifier_input_sha256"]:
                    self.note(stage="paired_issuance_and_redemption_verified", active=False,
                              issuance_seconds=issuance["phases"]["prove"]["elapsed_seconds"],
                              redemption_seconds=redemption["phases"]["prove"]["elapsed_seconds"])
                    emit(stage="paired_issuance_and_redemption_verified", vm_id=self.vm_id)
                    return
        raise RuntimeError("The local verifier did not report the exact returned payout proof")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--local-bundle", required=True, help="Redemption-enabled pinned bundle in WSL")
    parser.add_argument("--spot", action="store_true", help="Use an explicitly approved preemptible A100")
    args = parser.parse_args()
    pilot = PairedPilot(args.key_file.read_text(encoding="utf-8-sig").strip(),
                        args.kit.resolve(), args.results.resolve())
    subprocess.run(WSL + ["test", "-f", args.local_bundle + "/benchmarks/shinigami/redemption/Runtime.toml"],
                   check=True, timeout=12)
    pilot.local_bundle = args.local_bundle
    if args.spot:
        pilot.flavor = "n3-A100x1-spot"
        pilot.price_sku = "A100-80G-PCIe-spot"
        pilot.hourly_ceiling = 1.10
    emit(stage="paired_pilot_preflight", result_dir=str(pilot.run_dir))
    try:
        pilot.run()
    finally:
        try:
            pilot.cleanup()
        finally:
            try:
                pilot.stop_fixture()
            finally:
                pilot.clean_storage()


if __name__ == "__main__":
    main()

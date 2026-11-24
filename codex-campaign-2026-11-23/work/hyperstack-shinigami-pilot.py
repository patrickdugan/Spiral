import argparse
import hashlib
import ipaddress
import json
from pathlib import Path, PureWindowsPath
import queue
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request

API = "https://infrahub-api.nexgencloud.com/v1"
REGION = "CANADA-1"
ENVIRONMENT = "default-CANADA-1"
FLAVOR = "n3-H100x1-spot"
IMAGE = "Ubuntu Server 24.04 LTS R570 CUDA 12.8 with Docker"
LINUX_BASE = "/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat"
LOCAL_BUNDLE = "/tmp/proofdesk-shinigami-pilot-26maqmjn/shinigami-cpu-pilot"
WSL = ["wsl.exe", "-d", "Ubuntu-24.04", "-u", "root", "--"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def emit(**entry):
    print(json.dumps(entry, ensure_ascii=True), flush=True)


def iteration_until(deadline):
    while time.monotonic() < deadline:
        yield
        time.sleep(4)


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def windows_case_path(path):
    if not path.startswith("/mnt/c/Users/patri/Documents/Codex/2026-11-15/new-chat/outputs/ark-cashu-proofdesk/.runtime/cdk-e2e-"):
        raise ValueError("fixture path is outside the isolated workspace")
    candidate = Path(PureWindowsPath("C:/" + path[len("/mnt/c/"):])).resolve()
    root = Path("C:/Users/patri/Documents/Codex/2026-11-15/new-chat/outputs/ark-cashu-proofdesk/.runtime").resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("fixture path escaped the runtime directory")
    return candidate


class Pilot:
    def __init__(self, credential, artifact, results):
        self.credential = credential
        self.artifact = artifact
        self.results = results
        self.name = "cashu-shinigami-pilot-" + secrets.token_hex(5)
        self.run_dir = results / self.name
        self.run_dir.mkdir()
        self.http = urllib.request.build_opener(NoRedirect())
        self.vm_id = self.key_id = self.fixture = None
        self.fixture_output = queue.Queue()
        self.submitted = False
        self.cutoff = time.monotonic() + 3500
        self.ssh_key = self.run_dir / "identity"
        self.unit = self.name + "-local"

    def api(self, method, suffix, body=None, missing_ok=False):
        headers = {"api_key": self.credential, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        request = urllib.request.Request(f"{API}/{suffix}", data, headers, method=method)
        try:
            with self.http.open(request, timeout=18) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            try:
                reply = json.loads(error.read(8192))
                detail = str(reply.get("message") or reply.get("detail") or reply.get("errors") or "")
            except (ValueError, AttributeError):
                detail = ""
            detail = detail.replace(self.credential, "[redacted]")
            detail = re.sub(r"https://ca1\.obj\.nexgencloud\.io/[^\s\"']+", "[private object URL]", detail)[:360]
            raise RuntimeError(f"Hyperstack {method} {suffix} returned HTTP {error.code} {detail}") from None

    def note(self, **fields):
        target = self.run_dir / "state.json"
        record = json.loads(target.read_text()) if target.is_file() else {}
        record.update(name=self.name, vm_id=self.vm_id, **fields)
        temporary = self.run_dir / "state.tmp"
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        temporary.replace(target)

    def inventory(self):
        return self.api("GET", "core/virtual-machines")["instances"]

    def vm(self, missing_ok=False):
        request = self.api("GET", f"core/virtual-machines/{self.vm_id}", missing_ok=missing_ok)
        if request is None:
            return None
        result = request["instance"]
        if result["name"] != self.name or int(result["id"]) != self.vm_id:
            raise RuntimeError("Hyperstack VM identity verification failed")
        return result

    def provision(self):
        prices = {line["name"]: float(line["value"]) for line in self.api("GET", "pricebook")}
        rate = prices["H100-80G-PCIe-spot"] + prices["PublicIP"]
        if not 0 < rate <= 2.55:
            raise RuntimeError(f"Unexpected hourly rate for the approved offer ({rate:.3f})")
        if any(row["name"].startswith("cashu-shinigami-pilot-") for row in self.inventory()):
            raise RuntimeError("A previous isolated Shinigami trial must be reconciled first")
        with self.http.open("https://api.ipify.org", timeout=8) as response:
            source = ipaddress.IPv4Address(response.read(64).decode().strip())
        if not source.is_global:
            raise RuntimeError("No public IPv4 available for an SSH /32 rule")
        cidr = str(ipaddress.IPv4Network(f"{source}/32"))
        subprocess.run(["ssh-keygen.exe", "-q", "-t", "ed25519", "-f",
                        str(self.ssh_key), "-N", "", "-C", self.name],
                       stdin=subprocess.DEVNULL, check=True, timeout=12)
        response = self.api("POST", "core/keypairs", {
            "name": self.name, "environment_name": ENVIRONMENT,
            "public_key": self.ssh_key.with_suffix(".pub").read_text().strip(),
        })
        if response.get("status") is False:
            raise RuntimeError("API refused the ephemeral SSH public key")
        keys = self.api("GET", "core/keypairs")["keypairs"]
        key, = (key for key in keys if key["name"] == self.name and key["environment"]["name"] == ENVIRONMENT)
        self.key_id = key["id"]
        self.note(stage="provisioning", rate_usd_per_hour=rate, requested_at=int(time.time()))
        self.submitted = True
        result = self.api("POST", "core/virtual-machines", {
            "name": self.name, "environment_name": ENVIRONMENT, "image_name": IMAGE,
            "flavor_name": FLAVOR, "key_name": self.name, "count": 1,
            "assign_floating_ip": True,
            "security_rules": [{
                "direction": "ingress", "protocol": "tcp", "port_range_min": 22,
                "port_range_max": 22, "ethertype": "IPv4", "remote_ip_prefix": cidr,
            }],
        })
        instance, = result["instances"]
        if instance["name"] != self.name:
            raise RuntimeError("Hyperstack returned an unexpected instance name")
        self.vm_id = int(instance["id"])
        self.note(stage="provisioned")
        emit(stage="provisioned", vm_id=self.vm_id, rate_usd_per_hour=rate,
             provider="Hyperstack", flavor=FLAVOR, region=REGION)
        for _ in iteration_until(min(self.cutoff - 1800, time.monotonic() + 350)):
            current = self.vm()
            if current["status"] in ("ERROR", "DELETED", "FAILED"):
                raise RuntimeError(f"Hyperstack VM reported {current['status']}")
            if current["status"] == "ACTIVE" and current.get("floating_ip"):
                rules = [rule for rule in current["security_rules"] if rule["direction"].lower() == "ingress"]
                ports = [(rule.get("remote_ip_prefix"), rule.get("protocol"),
                          rule.get("port_range_min"), rule.get("port_range_max")) for rule in rules]
                if ports != [(cidr, "tcp", 22, 22)]:
                    raise RuntimeError("VM ingress does not match the approved SSH /32 rule")
                self.target = f"ubuntu@{ipaddress.IPv4Address(current['floating_ip'])}"
                self.ssh_options = ["-i", str(self.ssh_key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                                    "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=15",
                                    "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=accept-new",
                                    "-o", f"UserKnownHostsFile={self.run_dir / 'known_hosts'}"]
                return
        raise TimeoutError("VM did not become active within the provisioning window")

    def ssh(self, command, timeout=20, check=True):
        return subprocess.run(["ssh.exe", *self.ssh_options, self.target, command],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=timeout, check=check)

    def upload(self, files, remote, timeout=90):
        subprocess.run(["scp.exe", *self.ssh_options, *map(str, files),
                        f"{self.target}:{remote}"], stdin=subprocess.DEVNULL, check=True, timeout=timeout)

    def pull(self, remote, local, timeout=45):
        subprocess.run(["scp.exe", *self.ssh_options, f"{self.target}:{remote}", str(local)],
                       stdin=subprocess.DEVNULL, check=True, timeout=timeout)

    def log_fixture(self):
        with (self.run_dir / "fixture.log").open("w", encoding="utf-8") as log:
            for line in self.fixture.stdout:
                log.write(line)
                log.flush()
                if line.startswith("{"):
                    try:
                        self.fixture_output.put(json.loads(line))
                    except ValueError:
                        pass

    def begin_fixture(self, extra_args=(), local_bundle=LOCAL_BUNDLE):
        seconds = min(3150, int(self.cutoff - time.monotonic() - 110))
        if seconds < 900:
            raise TimeoutError("Too little time remains for a fresh proving benchmark")
        repo = LINUX_BASE + "/outputs/ark-cashu-proofdesk"
        command = WSL + ["systemd-run", "--quiet", "--wait", "--collect", "--pipe", f"--unit={self.unit}",
                         "-p", "CPUQuota=100%", "-p", "MemoryMax=2G", "-p", "MemorySwapMax=1G",
                         "/usr/bin/nice", "-n", "15", "python3", "-B", repo + "/tests/run-regtest-stack.py",
                         "--cdk", LINUX_BASE + "/work/integration-bin/cdk-mintd-0.18.3-x86_64",
                         "--node", "/opt/node/bin/node", "--shinigami-bundle", local_bundle,
                         "--shinigami-external", str(seconds), "--test-funded-refusal", *extra_args]
        self.fixture = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self.log_fixture, daemon=True).start()

    def fixture_ready(self):
        deadline = time.monotonic() + 160
        while time.monotonic() < deadline and self.fixture.poll() is None:
            try:
                event = self.fixture_output.get(timeout=2)
            except queue.Empty:
                continue
            if event.get("status") == "waiting_for_shinigami_proof":
                return event
        raise RuntimeError("Local Core/CDK fixture did not produce a live quote; see fixture.log")

    def benchmark(self):
        for _ in iteration_until(min(self.cutoff - 1700, time.monotonic() + 130)):
            probe = self.ssh("umask 077; mkdir -p cashu-pilot; command -v python3; test -x /usr/bin/time; nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", check=False)
            if probe.returncode == 0 and "H100" in probe.stdout:
                emit(stage="connected", hardware=probe.stdout.splitlines()[-1], proving_backend="CPU")
                break
        else:
            raise RuntimeError("Restricted SSH endpoint or GPU health check failed")
        self.begin_fixture()
        self.upload([self.artifact], "cashu-pilot/shinigami-cpu-pilot.tar.gz")
        sha256 = file_digest(self.artifact)
        self.ssh(f"cd cashu-pilot && printf '%s  %s\\n' {sha256} shinigami-cpu-pilot.tar.gz | sha256sum -c && tar -xzf shinigami-cpu-pilot.tar.gz", timeout=60)
        event = self.fixture_ready()
        local_case = windows_case_path(event["case_file"])
        local_arguments = windows_case_path(event["arguments_file"])
        proof_target = windows_case_path(event["proof_target"])
        self.upload([local_case, local_arguments], "cashu-pilot/")
        limit = min(event["wait_seconds"] - 90, int(self.cutoff - time.monotonic() - 95))
        if limit < 600:
            raise TimeoutError("Insufficient time left in the pilot window")
        shell = ("cd cashu-pilot/shinigami-cpu-pilot && python3 -B benchmarks/shinigami/run.py ../run "
                 f"--regtest-case ../shinigami-case.json --threads 16 --max-seconds {limit}")
        self.note(stage="benchmark_live", proof_target=str(proof_target), threads=16)
        emit(stage="remote_benchmark_started", backend="CPU", rayon_threads=16, time_limit_seconds=limit)
        with (self.run_dir / "benchmark.log").open("w", encoding="utf-8") as log:
            trial = subprocess.run(["ssh.exe", *self.ssh_options, self.target, shell],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=limit + 25)
        local_report = self.run_dir / "benchmark.json"
        self.pull("cashu-pilot/run/report.json", local_report)
        report = json.loads(local_report.read_text())
        if trial.returncode != 0 or report["status"] != "fresh_proof_independently_verified":
            raise RuntimeError("The cloud proof did not independently verify; see benchmark.json")
        proof_pending = proof_target.with_suffix(".partial")
        self.pull("cashu-pilot/run/verifier-input.json", proof_pending)
        if file_digest(proof_pending) != report["verifier_input_sha256"]:
            raise RuntimeError("Downloaded proof differs from the cloud verifier input")
        proof_pending.replace(proof_target)
        emit(stage="cloud_proof_verified", proof_sha256=report["verifier_input_sha256"], phases=report["phases"])
        self.fixture.wait(timeout=max(30, min(90, int(self.cutoff - time.monotonic()))))
        if self.fixture.returncode:
            raise RuntimeError("Local proof admission or funded payout failed; see fixture.log")
        self.note(stage="local_issuance_and_reserve_verified")
        emit(stage="local_issuance_and_reserve_verified")

    def cleanup(self):
        if self.submitted and self.vm_id is None:
            owned = [row for row in self.inventory() if row["name"] == self.name]
            if len(owned) > 1:
                raise RuntimeError("Duplicate identities need removal from the console")
            if owned:
                self.vm_id = int(owned[0]["id"])
        if self.vm_id is not None:
            if self.vm(missing_ok=True) is not None:
                self.api("DELETE", f"core/virtual-machines/{self.vm_id}", missing_ok=True)
            for _ in iteration_until(time.monotonic() + 120):
                current = self.vm(missing_ok=True)
                if current is None or current["status"] == "DELETED":
                    emit(stage="vm_deleted", vm_id=self.vm_id)
                    self.note(cleanup="vm_deleted")
                    break
            else:
                raise RuntimeError(f"Deletion unconfirmed for VM {self.vm_id}; inspect Hyperstack immediately")
        if self.key_id is not None:
            self.api("DELETE", f"core/keypair/{int(self.key_id)}", missing_ok=True)

    def stop_fixture(self):
        if self.fixture and self.fixture.poll() is None:
            subprocess.run(WSL + ["systemctl", "kill", "--kill-whom=main", "--signal=SIGINT", self.unit],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=12, check=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    key = args.key_file.read_text(encoding="utf-8-sig").strip()
    if not args.kit.is_file() or not args.results.is_dir() or not key:
        raise ValueError("Pilot inputs are missing")
    pilot = Pilot(key, args.kit.resolve(), args.results.resolve())
    emit(stage="pilot_preflight", result_dir=str(pilot.run_dir))
    try:
        pilot.provision()
        pilot.benchmark()
    finally:
        try:
            pilot.cleanup()
        finally:
            pilot.stop_fixture()


if __name__ == "__main__":
    main()

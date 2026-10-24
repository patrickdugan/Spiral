"""Phase 9's model runs, in turn, under one GPU lease (start it with ``vramorama run``).

1. A base Bonsai-8B server (no adapter: BitAgent's A4 recipe) and controller
   qualification on the collected turns.
2. The same port, restarted with the actor's adapter applied: Bonsai-8B + the
   v3 DAG adapter. Per-request adapter switching on one server was tried and
   is unusable here (one switched request took about 100 s).
3. The actor stage through the runtime arms (BitAgent's
   ``eval/run-runtime-phase9.ts --stage=actor --resume``), controller ``none``
   then ``model``; the model controller is the base weights on a CPU server,
   whose decisions were checked against the GPU base server's.

Every step resumes: finished qualification is kept, finished runs are kept.
A heartbeat file says what the driver is doing. It waits while the PC runs on
battery, where the GPU throttles to almost nothing.

Usage: vramorama run --vram 2450M --owner phase9 --detach --out <log> --wait <s> --
           python -u scripts/phase9_driver.py [--experiment phase9-actor-v1] [--arms R1,R2,R0]
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "results" / "phase9-logs"
GYM = Path("C:/Users/patri/Documents/Codex/BitAgent-gym")
SERVER = GYM / "llama-prism" / "bin" / "llama-server.exe"
BASE = GYM / "prime-artifacts" / "Bonsai-8B-Q1_0.gguf"
ADAPTER = GYM / "prime-artifacts" / "bitagent-bonsai8b-dagv2-lora-v3-f16.gguf"
BASE_SHA256 = "284a335aa3fb2ced3b1b01fcb40b08aa783e3b70832767f0dd2e3fdfa134bd54"
ADAPTER_SHA256 = "9a11fe2cecf795f53dbea490b9897b28f3d3346a9f69a71ce28bbb195f7de704"
ALIAS = "Bonsai-8B-Q1_0"
KERNEL = Path("C:/Users/patri/OneDrive/Documents/GitHub/BitAgent/apps/bitagent-launch-kernel")
NODE = Path("C:/Users/patri/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
GOOSE_BIN = "C:/Users/patri/Documents/GitHub/goose-builds/goose-control-gate.exe"


def say(message: str, stage: str | None = None) -> None:
    line = f"[phase9-driver] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    if stage is not None:
        (LOGS / "driver-heartbeat.json").write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "pid": os.getpid(), "stage": stage, "note": message}), encoding="utf-8")


def on_mains() -> bool:
    class Status(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte), ("BatteryLifePercent", ctypes.c_byte),
                    ("SystemStatusFlag", ctypes.c_byte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    status = Status()
    return not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) or status.ACLineStatus != 0


def wait_for_mains(stage: str) -> None:
    while not on_mains():
        say("on battery: waiting for mains power", stage)
        time.sleep(120)


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/health", timeout=5) as response:
            return b"ok" in response.read()
    except OSError:
        return False


def start_server(port: int, *, adapter: bool | Path | None, cpu: bool = False, log_name: str, model: Path = BASE, alias: str = ALIAS) -> subprocess.Popen:
    """A llama-server on loopback; ``adapter`` True means the v3 adapter, a path another adapter."""
    args = [str(SERVER), "-m", str(model), "-c", "6144", "-np", "1", "--no-webui", "--alias", alias, "--reasoning", "off", "--host", "127.0.0.1", "--port", str(port)]
    args += ["--device", "none", "--no-op-offload", "-ngl", "0", "-t", "6"] if cpu else ["-ngl", "99"]
    if adapter:
        args += ["--lora", str(ADAPTER if adapter is True else adapter)]
    log = open(LOGS / log_name, "a", encoding="utf-8")
    process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) if cpu else 0)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        if healthy(url):
            return process
        if process.poll() is not None:
            raise RuntimeError(f"server on {port} exited with {process.returncode}; see {log_name}")
        time.sleep(2)
    process.kill()
    raise RuntimeError(f"server on {port} never became healthy")


def stop(process: subprocess.Popen | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()


def adapters(port: int) -> list:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/lora-adapters", timeout=10) as response:
        return json.loads(response.read())


def qualify(port: int) -> None:
    out = LOGS / "qualification-bonsai8b.json"
    if out.exists() and "verdict" in json.loads(out.read_text(encoding="utf-8")):
        say("qualification already done; kept", "qualify")
        return
    wait_for_mains("qualify")
    server = start_server(port, adapter=False, log_name=f"server-{port}-base.log")
    try:
        if adapters(port):
            raise RuntimeError("the controller server must load no adapter")
        say("qualifying the base controller on the collected turns", "qualify")
        subprocess.run([sys.executable, "-u", str(ROOT / "scripts" / "qualify_controller.py"), "--runs", str(ROOT / "results" / "runs" / "phase9-collect-v2" / "null"),
                        "--controller-url", f"http://127.0.0.1:{port}/v1", "--controller-model", ALIAS, "--model-hash", BASE_SHA256, "--out", str(out)], check=True)
        say("qualification finished", "qualify")
    finally:
        stop(server)


def actor_stage(args: argparse.Namespace) -> int:
    # The model controller's endpoint comes from <runs>/<experiment>/controller.json. A CPU server is
    # started only on request (--cpu-controller); a separate GPU base server with --controller-port.
    port, adapter = args.port, (None if args.actor_adapter == "none" else Path(args.actor_adapter))
    start_actor = lambda: start_server(port, adapter=adapter, log_name=f"server-{port}-actor.log", model=Path(args.actor_model), alias=args.actor_alias)  # noqa: E731
    cpu = start_server(args.cpu_port, adapter=False, cpu=True, log_name=f"controller-cpu-{args.cpu_port}.log") if args.cpu_controller and not healthy(f"http://127.0.0.1:{args.cpu_port}") else None
    controller = start_server(args.controller_port, adapter=False, log_name=f"server-{args.controller_port}-controller.log") if args.controller_port else None
    server = start_actor()
    try:
        if controller is not None and adapters(args.controller_port):
            raise RuntimeError("the controller server must load no adapter")
        loaded = adapters(port)
        if (adapter is None and loaded) or (adapter is not None and (len(loaded) != 1 or float(loaded[0]["scale"]) != 1.0)):
            raise RuntimeError(f"the actor server's adapters are not as asked ({args.actor_adapter}): {loaded}")
        env = dict(os.environ) | {"GOOSE_FORK_BIN": GOOSE_BIN}
        command = [str(NODE), "node_modules/tsx/dist/cli.mjs", "eval/run-runtime-phase9.ts", "--stage=actor", f"--experiment={args.experiment}", f"--arms={args.arms}",
                   f"--model-url=http://127.0.0.1:{port}", f"--model-id={args.model_id}", f"--controllers={args.controllers}",
                   f"--controller-url=http://127.0.0.1:{args.cpu_port}/v1", f"--controller-model={ALIAS}", "--resume"]
        if args.only:
            command.append(f"--only={args.only}")
        for attempt in range(1, 4):
            wait_for_mains("actor")
            say(f"actor stage, attempt {attempt}", "actor")
            code = subprocess.run(command, cwd=KERNEL, env=env).returncode
            if code == 0:
                say("actor stage finished", "done")
                return 0
            say(f"actor stage exited {code}; resuming", "actor")
            if not healthy(f"http://127.0.0.1:{port}"):
                stop(server)
                server = start_actor()
        say("actor stage failed three times", "failed")
        return 1
    finally:
        stop(server)
        stop(controller)
        stop(cpu)


def live_stage(args: argparse.Namespace) -> int:
    """The model controller live, deciding reference policies' calls: only the controller's server runs."""
    port = args.controller_port or args.port
    controller = start_server(port, adapter=False, log_name=f"server-{port}-controller.log")
    try:
        if adapters(port):
            raise RuntimeError("the controller server must load no adapter")
        env = dict(os.environ) | {"GOOSE_FORK_BIN": GOOSE_BIN}
        command = [str(NODE), "node_modules/tsx/dist/cli.mjs", "eval/run-runtime-phase9.ts", "--stage=live", f"--experiment={args.experiment}", f"--arms={args.arms}",
                   f"--random-seeds={args.random_seeds}", f"--controller-url=http://127.0.0.1:{port}/v1", f"--controller-model={ALIAS}", "--resume"]
        if args.only:
            command.append(f"--only={args.only}")
        command += args.runner_arg or []
        for attempt in range(1, args.attempts + 1):
            wait_for_mains("live")
            say(f"live stage, attempt {attempt}", "live")
            code = subprocess.run(command, cwd=KERNEL, env=env).returncode
            if code == 0:
                say("live stage finished", "done")
                return 0
            say(f"live stage exited {code}; resuming", "live")
            if not healthy(f"http://127.0.0.1:{port}"):
                stop(controller)
                controller = start_server(port, adapter=False, log_name=f"server-{port}-controller.log")
        say(f"live stage failed {args.attempts} times", "failed")
        return 1
    finally:
        stop(controller)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", default="phase9-actor-v1")
    parser.add_argument("--arms", default="R1,R2,R0")
    parser.add_argument("--port", type=int, default=8103)
    parser.add_argument("--cpu-port", type=int, default=8105)
    parser.add_argument("--skip-qualification", action="store_true")
    parser.add_argument("--cpu-controller", action="store_true", help="start the CPU controller server if it is not up")
    parser.add_argument("--controller-port", type=int, help="also start the base controller (no adapter) on this GPU port")
    parser.add_argument("--actor-model", default=str(BASE))
    parser.add_argument("--actor-adapter", default=str(ADAPTER), help="the actor's adapter, or none")
    parser.add_argument("--actor-alias", default=ALIAS)
    parser.add_argument("--model-id", default="bonsai8b-dagv2-lora-v3")
    parser.add_argument("--controllers", default="none,model")
    parser.add_argument("--only", default="")
    parser.add_argument("--stage", choices=("actor", "live"), default="actor")
    parser.add_argument("--random-seeds", type=int, default=2)
    parser.add_argument("--attempts", type=int, default=3, help="live stage: how many times to restart the runner (and a dead controller server) before giving up")
    parser.add_argument("--runner-arg", action="append", help="passed to eval/run-runtime-phase9.ts as is, e.g. --runner-arg=--set=open-gate")
    args = parser.parse_args(argv)
    LOGS.mkdir(parents=True, exist_ok=True)
    say(f"started; lease {os.environ.get('VRAMORAMA_LEASE', '?')}; experiment {args.experiment}", "start")
    try:
        if not args.skip_qualification:
            qualify(args.port)
        return live_stage(args) if args.stage == "live" else actor_stage(args)
    except Exception as exc:  # noqa: BLE001 - recorded in the heartbeat, then raised
        say(f"stopped: {type(exc).__name__}: {exc}", "failed")
        raise


if __name__ == "__main__":
    sys.exit(main())

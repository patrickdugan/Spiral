from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from . import demo
from .adapters import CoreClient
from .domain import Intent, Ledger, Refused, plan_vtxo
from .server import Desk, make_server
from .verifier import M16Gate, PROOF_LIMIT, STATEMENT_SIZE, read_bounded
from .shinigami import ShinigamiGate
from . import recovery_cli


def load_config(path: str) -> dict:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise Refused("invalid_config")
    return config


def gate_from(config: dict) -> M16Gate:
    gate = config["gate"]
    return M16Gate(gate["argv"], gate["binary_sha256"], config["policy"])


def main():
    parser = argparse.ArgumentParser(description="Proof Grove — local Ark / Cashu proof desk")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--config", help="Use live mode with a server-owned configuration")
    check = commands.add_parser("verify", help="Verify M16 proof bytes; does not authorize or settle a payment")
    check.add_argument("--config", required=True)
    check.add_argument("--statement", required=True)
    check.add_argument("--proof", required=True)
    case = commands.add_parser("demo")
    case.add_argument("--case", choices=[c["id"] for c in demo.CASES], default="cashu")
    plan = commands.add_parser("plan", help="Plan VTXO refresh/exit; never signs or broadcasts")
    plan.add_argument("--vtxo", required=True)
    plan.add_argument("--tip", type=int, required=True)
    recovery_cli.configure(commands)
    args = parser.parse_args()
    try:
        if args.command.startswith("exit-"):
            print(json.dumps(recovery_cli.run(args), indent=2))
        elif args.command == "demo":
            print(json.dumps(demo.run_case(args.case), indent=2))
        elif args.command == "plan":
            print(json.dumps(plan_vtxo(load_config(args.vtxo), args.tip), indent=2))
        elif args.command == "verify":
            evidence = gate_from(load_config(args.config)).verify(read_bounded(args.statement, STATEMENT_SIZE), read_bounded(args.proof, PROOF_LIMIT))
            print(json.dumps({"status": "proof-verified", "settlement": "not executed", "evidence": asdict(evidence)}, indent=2))
        elif args.command == "serve":
            ledger = None
            if args.config:
                config_path = Path(args.config).resolve()
                config = load_config(args.config)
                mode = config.get("mode","live")
                if mode not in ("live","regtest"):
                    raise Refused("invalid_mode")
                db_path = config_path.parent / config.get("database", f".runtime/{mode}.sqlite")
                db_path.parent.mkdir(parents=True, exist_ok=True)
                ledger = Ledger(db_path, mode)
                for item in config.get("intents", []):
                    ledger.add_intent(Intent(**item))
                core_config = config["core"]
                password = os.environ[core_config["password_env"]]
                core = CoreClient(core_config["url"], core_config["username"], password)
                public_config = {k: config[k] for k in ("cashu_url", "bark_url", "ark_regtest_execution", "ark_regtest_exit_broadcast", "max_tip_lag", "max_view_age_seconds","min_confirmations") if k in config}
                if config.get("bark_bearer_env"):
                    public_config["bark_bearer"] = os.environ[config["bark_bearer_env"]]
                shinigami = None
                if "shinigami" in config:
                    setup = config["shinigami"]
                    shinigami = ShinigamiGate(
                        Path(setup["verifier"]), config_path.parent / setup["proof_dir"],
                        setup["verifier_sha256"], setup["bootloader_sha256"],
                        config_path.parent / setup["manifest_dir"] if "manifest_dir" in setup else None,
                    )
                desk = Desk(mode, ledger, gate_from(config) if mode == "live" else None, core, public_config, shinigami)
            else:
                desk = Desk()
            server = make_server(desk, args.port)
            print(f"Proof Grove ({desk.mode}) http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
                if ledger:
                    ledger.close()
    except KeyboardInterrupt:
        return 130
    except (Refused, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"error": exc.code if isinstance(exc, Refused) else "configuration_or_file_error"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
from .verifier import M16Gate, NativeFinalGate, PROOF_LIMIT, STATEMENT_SIZE, read_bounded
from . import protected_cli, recovery_cli
from .access import HostedAccess


def load_config(path: str) -> dict:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise Refused("invalid_config")
    return config


def gate_from(config: dict) -> M16Gate:
    gate = config["gate"]
    formats={'payment-gate':M16Gate,'m13-final':NativeFinalGate}
    kind=gate.get('format','payment-gate')
    if kind not in formats:raise Refused('unsupported_gate_format')
    return formats[kind](gate["argv"], gate["binary_sha256"], config["policy"])


def main():
    parser = argparse.ArgumentParser(description="Proof Grove — local Ark / Cashu proof desk")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--config", help="Use live mode with a server-owned configuration")
    serve.add_argument("--protected-preview", type=Path, help="Load a pinned archived V3 regtest payout for the local demo")
    serve.add_argument("--protected-funded-preview", type=Path,
                       help="Watch a pinned, independently verified joint payout publication in the local demo")
    serve.add_argument('--hosted',action='store_true',help='Require bearer authentication and exact configured HTTPS origins behind a TLS proxy')
    serve.add_argument('--bind',default='127.0.0.1',choices=['127.0.0.1','0.0.0.0'])
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
    protected_cli.configure(commands)
    args = parser.parse_args()
    try:
        if args.command.startswith("exit-"):
            print(json.dumps(recovery_cli.run(args), indent=2))
        elif args.command.startswith("protected-"):
            print(json.dumps(protected_cli.run(args), indent=2))
        elif args.command == "demo":
            print(json.dumps(demo.run_case(args.case), indent=2))
        elif args.command == "plan":
            print(json.dumps(plan_vtxo(load_config(args.vtxo), args.tip), indent=2))
        elif args.command == "verify":
            evidence = gate_from(load_config(args.config)).verify(read_bounded(args.statement, STATEMENT_SIZE), read_bounded(args.proof, PROOF_LIMIT))
            print(json.dumps({"status": "proof-verified", "settlement": "not executed", "evidence": asdict(evidence)}, indent=2))
        elif args.command == "serve":
            ledger = None
            access=None
            if args.protected_preview and (args.config or args.hosted or args.bind != '127.0.0.1'):
                raise Refused('protected_preview_requires_local_demo')
            if args.protected_funded_preview and not args.protected_preview:
                raise Refused('funded_preview_requires_protected_preview')
            if args.hosted and not args.config:raise Refused('hosted_configuration_required')
            if args.config:
                config_path = Path(args.config).resolve()
                config = load_config(args.config)
                if args.hosted:access=HostedAccess.from_config(config.get('hosted_api'))
                mode = config.get("mode","live")
                if mode not in ("live","regtest"):
                    raise Refused("invalid_mode")
                db_path = config_path.parent / config.get("database", f".runtime/{mode}.sqlite")
                db_path.parent.mkdir(parents=True, exist_ok=True)
                ledger = Ledger(db_path, mode)
                for item in config.get("intents", []):
                    ledger.add_intent(Intent(**item))
                core_config = config["core"]
                core = CoreClient.from_config(core_config)
                public_config = {k: config[k] for k in ("cashu_url", "bark_url", "ark_regtest_execution", "ark_regtest_exit_broadcast", "max_tip_lag", "max_view_age_seconds","min_confirmations","recorded_proof", "protected_melt_wallet") if k in config}
                if config.get("bark_bearer_env"):
                    public_config["bark_bearer"] = os.environ[config["bark_bearer_env"]]
                desk = Desk(mode, ledger, gate_from(config) if mode == "live" else None, core, public_config)
            else:
                preview = {"protected_preview": args.protected_preview.resolve()} if args.protected_preview else {}
                if args.protected_funded_preview:
                    preview["protected_funded_preview"] = args.protected_funded_preview.resolve()
                desk = Desk(config=preview)
            server = make_server(desk, args.port,access=access,bind=args.bind)
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

"""Lease-based collaborative proving coordinator for Cashu SP1 group reductions.

Responsibilities:
  1. Assign one-group work orders (`000000`..`000291`, default backward from highest
     group so contributors stay ahead of a live local reducer scanning forward).
  2. Track heartbeats and automatically reclaim & reassign any group stuck on a dead
     worker once `heartbeat_timeout_s` or `lease_ttl_s` elapses.
  3. Enforce the untrusted-contributor boundary on every submission:
       - Gate 1: `cuda_reduction_verified` receipt + exact group/VK/manifest/SHA-256 match
       - Gate 2: coordinator-local pinned `replay-reduction-cpu ... --check-inputs`
       - Gate 3: atomic merge into `<compose_dir>/groups/NNNNNN/` for `compose_core_bounded.py`
  4. Record append-only `events.jsonl` and per-contributor throughput + rejected-root stats.
  5. Never handle, require, or distribute Bitcoin wallets or signing keys.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import uuid

from .schema import (
    GROUP_SIZE,
    TELEMETRY_SCHEMA,
    CollabError,
    assert_no_key_material_in_obj,
    groups_from_shard_index,
    load_shard_index,
    require_hex64,
    sha256_file,
    verify_pinned_file,
)
from .verifier import verify_and_merge_submission


@dataclass
class WorkerStats:
    worker_id: str
    groups_assigned: int = 0
    groups_verified: int = 0
    shards_verified: int = 0
    roots_rejected: int = 0
    leases_expired: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    total_group_seconds: float = 0.0
    total_cpu_verify_seconds: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0

    def to_dict(self) -> dict:
        avg_group = (self.total_group_seconds / self.groups_verified) if self.groups_verified else None
        avg_cpu = (self.total_cpu_verify_seconds / self.groups_verified) if self.groups_verified else None
        active_span = max(self.last_seen - self.first_seen, 1e-6) if self.first_seen else 0.0
        g_per_hr = (self.groups_verified / active_span * 3600.0) if (self.groups_verified and active_span > 0) else 0.0
        s_per_sec = (self.shards_verified / self.total_group_seconds) if self.total_group_seconds > 0 else 0.0
        return {
            "worker_id": self.worker_id,
            "groups_assigned": self.groups_assigned,
            "groups_verified": self.groups_verified,
            "shards_verified": self.shards_verified,
            "roots_rejected": self.roots_rejected,
            "leases_expired": self.leases_expired,
            "rejection_reasons": dict(sorted(self.rejection_reasons.items())),
            "avg_group_seconds": round(avg_group, 4) if avg_group is not None else None,
            "avg_cpu_verify_seconds": round(avg_cpu, 4) if avg_cpu is not None else None,
            "throughput_groups_per_hour": round(g_per_hr, 2),
            "throughput_shards_per_sec": round(s_per_sec, 2),
        }


class CoordinatorEngine:
    """Thread-safe lease scheduler, dead-worker reaper, verifier, and telemetry recorder."""

    def __init__(
        self,
        *,
        work_orders: list[dict],
        compose_dir: Path,
        state_dir: Path,
        cpu_checker_path: Path,
        cpu_checker_sha256: str,
        run_json_path: Path,
        program_key_path: Path,
        archive_path: Path | None = None,
        direction: str = "backward",
        lease_ttl_s: float = 1800.0,
        heartbeat_timeout_s: float = 120.0,
        heartbeat_interval_s: float = 30.0,
        cpu_timeout_s: int = 180,
        clock=time.monotonic,
    ):
        if direction not in ("backward", "forward"):
            raise CollabError("direction must be 'backward' or 'forward'")
        if not work_orders:
            raise CollabError("work_orders must be non-empty")
        verify_pinned_file(cpu_checker_path, cpu_checker_sha256, "replay-reduction-cpu")
        verify_pinned_file(run_json_path, work_orders[0]["run_manifest_sha256"], "run.json")

        self.orders: dict[str, dict] = {o["group_id"]: o for o in work_orders}
        self.order_sequence: list[str] = (
            [o["group_id"] for o in reversed(work_orders)]
            if direction == "backward"
            else [o["group_id"] for o in work_orders]
        )
        self.compose_dir = Path(compose_dir).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.compose_dir / "groups").mkdir(parents=True, exist_ok=True)

        self.cpu_checker_path = Path(cpu_checker_path).resolve()
        self.cpu_checker_sha256 = cpu_checker_sha256
        self.run_json_path = Path(run_json_path).resolve()
        self.program_key_path = Path(program_key_path).resolve()
        self.archive_path = Path(archive_path).resolve() if archive_path else None

        self.direction = direction
        self.lease_ttl_s = float(lease_ttl_s)
        self.heartbeat_timeout_s = float(heartbeat_timeout_s)
        self.heartbeat_interval_s = float(heartbeat_interval_s)
        self.cpu_timeout_s = int(cpu_timeout_s)
        self._clock = clock
        self._lock = threading.Lock()
        self._started_at = self._clock()
        self._completed_at: float | None = None

        self.events_path = self.state_dir / "events.jsonl"
        self.summary_path = self.state_dir / "summary.json"

        # Group state: status in ("pending", "leased", "verified")
        self.groups: dict[str, dict] = {}
        for gid in self.order_sequence:
            self.groups[gid] = {
                "group_id": gid,
                "status": "pending",
                "attempts": 0,
                "reassignments": 0,
                "lease_id": None,
                "worker_id": None,
                "leased_at": None,
                "last_heartbeat": None,
                "expires_at": None,
                "verified_by": None,
                "reduction_sha256": None,
                "group_seconds": None,
                "cpu_verify_seconds": None,
            }

        self.workers: dict[str, WorkerStats] = {}
        self.total_reassignments = 0
        self.total_rejected_roots = 0
        self.wasted_dead_worker_seconds = 0.0
        self.rejected_log: list[dict] = []

        # Detect any already-verified group slots present in compose_dir/groups before startup.
        self._scan_existing_verified_slots()

    def _scan_existing_verified_slots(self) -> None:
        groups_root = self.compose_dir / "groups"
        for gid, g in self.groups.items():
            slot = groups_root / gid
            if (slot / "reduction.bin").is_file() and (slot / "cpu-verify.json").is_file():
                try:
                    cpu = json.loads((slot / "cpu-verify.json").read_text(encoding="utf-8"))
                    if cpu.get("status") == "cpu_reduction_inputs_verified":
                        g["status"] = "verified"
                        g["verified_by"] = "preexisting"
                        g["reduction_sha256"] = sha256_file(slot / "reduction.bin")
                except (OSError, json.JSONDecodeError):
                    pass

    def _worker(self, worker_id: str, now: float) -> WorkerStats:
        if worker_id not in self.workers:
            self.workers[worker_id] = WorkerStats(worker_id=worker_id, first_seen=now, last_seen=now)
        w = self.workers[worker_id]
        w.last_seen = now
        return w

    def _emit_event(self, event: str, **fields) -> None:
        rec = {"event": event, "t_rel": round(self._clock() - self._started_at, 4), **fields}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def reap_expired_leases(self) -> list[dict]:
        """Reclaim any leased group whose worker stopped heartbeating or exceeded lease TTL."""
        with self._lock:
            return self._reap_locked(self._clock())

    def _reap_locked(self, now: float) -> list[dict]:
        reclaimed = []
        for g in self.groups.values():
            if g["status"] != "leased":
                continue
            hb_expired = (now - g["last_heartbeat"]) > self.heartbeat_timeout_s
            ttl_expired = now > g["expires_at"]
            if hb_expired or ttl_expired:
                dead_worker = g["worker_id"]
                old_lease = g["lease_id"]
                wasted = max(0.0, now - g["leased_at"])
                reason = "heartbeat_timeout" if hb_expired else "lease_ttl_expired"
                self.wasted_dead_worker_seconds += wasted
                self.total_reassignments += 1
                if dead_worker in self.workers:
                    self.workers[dead_worker].leases_expired += 1
                g["status"] = "pending"
                g["reassignments"] += 1
                g["lease_id"] = None
                g["worker_id"] = None
                g["leased_at"] = None
                g["last_heartbeat"] = None
                g["expires_at"] = None
                info = {
                    "group_id": g["group_id"],
                    "dead_worker_id": dead_worker,
                    "expired_lease_id": old_lease,
                    "reason": reason,
                    "wasted_seconds": round(wasted, 4),
                    "reassignments": g["reassignments"],
                }
                reclaimed.append(info)
                self._emit_event("dead_worker_reassigned", **info)
        return reclaimed

    def assign_lease(self, worker_id: str) -> dict | None:
        """Assign the next pending group work order to `worker_id` (reaping dead leases first)."""
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise CollabError("worker_id must be a non-empty string")
        with self._lock:
            now = self._clock()
            self._reap_locked(now)
            w = self._worker(worker_id, now)

            # Pick the next pending group in configured order (preferring reassigned groups first
            # so previously stuck groups are recovered immediately!).
            chosen = None
            for gid in self.order_sequence:
                g = self.groups[gid]
                if g["status"] == "pending" and g["reassignments"] > 0:
                    chosen = g
                    break
            if chosen is None:
                for gid in self.order_sequence:
                    g = self.groups[gid]
                    if g["status"] == "pending":
                        chosen = g
                        break
            if chosen is None:
                return None

            lease_id = uuid.uuid4().hex
            chosen["status"] = "leased"
            chosen["attempts"] += 1
            chosen["lease_id"] = lease_id
            chosen["worker_id"] = worker_id
            chosen["leased_at"] = now
            chosen["last_heartbeat"] = now
            chosen["expires_at"] = now + self.lease_ttl_s
            w.groups_assigned += 1

            order = self.orders[chosen["group_id"]]
            self._emit_event(
                "lease_assigned",
                group_id=chosen["group_id"],
                worker_id=worker_id,
                lease_id=lease_id,
                attempt=chosen["attempts"],
                reassignment=chosen["reassignments"] > 0,
            )
            payload = {
                "lease_id": lease_id,
                "worker_id": worker_id,
                "attempt": chosen["attempts"],
                "lease_ttl_s": self.lease_ttl_s,
                "heartbeat_interval_s": self.heartbeat_interval_s,
                "work_order": order,
            }
            assert_no_key_material_in_obj(payload)
            return payload

    def heartbeat(self, worker_id: str, lease_id: str, progress_shards: int = 0) -> dict:
        with self._lock:
            now = self._clock()
            self._reap_locked(now)
            for g in self.groups.values():
                if g["status"] == "leased" and g["lease_id"] == lease_id and g["worker_id"] == worker_id:
                    g["last_heartbeat"] = now
                    self._worker(worker_id, now)
                    self._emit_event(
                        "heartbeat",
                        group_id=g["group_id"],
                        worker_id=worker_id,
                        lease_id=lease_id,
                        progress_shards=int(progress_shards),
                    )
                    return {"ok": True, "group_id": g["group_id"]}
            return {"ok": False, "reason": "unknown_or_expired_lease"}

    def submit_root(
        self,
        *,
        worker_id: str,
        lease_id: str,
        group_id: str,
        reduction_bytes: bytes,
        cuda_receipt: dict,
        reported_group_seconds: float | None = None,
    ) -> dict:
        """Verify an untrusted contributor's root on the coordinator and merge if valid."""
        with self._lock:
            now = self._clock()
            self._reap_locked(now)
            w = self._worker(worker_id, now)
            g = self.groups.get(group_id)
            if g is None:
                return self._record_rejection_locked(w, group_id, lease_id, "unknown_group", "")
            if g["status"] == "verified":
                return self._record_rejection_locked(w, group_id, lease_id, "already_verified", "")
            if g["status"] != "leased" or g["lease_id"] != lease_id or g["worker_id"] != worker_id:
                return self._record_rejection_locked(w, group_id, lease_id, "stale_or_expired_lease", "")
            # Transition to `verifying` so the dead-worker reaper never reclaims a lease
            # while the coordinator itself is running `replay-reduction-cpu --check-inputs`.
            g["status"] = "verifying"
            order = self.orders[group_id]
            leased_at = g["leased_at"]

        # Run Gate 1 + Gate 2 + Gate 3 outside the scheduler lock so other workers can lease/heartbeat!
        res = verify_and_merge_submission(
            work_order=order,
            reduction_bytes=reduction_bytes,
            cuda_receipt=cuda_receipt,
            cpu_checker_path=self.cpu_checker_path,
            cpu_checker_sha256=self.cpu_checker_sha256,
            run_json_path=self.run_json_path,
            program_key_path=self.program_key_path,
            compose_dir=self.compose_dir,
            timeout_seconds=self.cpu_timeout_s,
        )

        with self._lock:
            now_done = self._clock()
            w = self._worker(worker_id, now_done)
            g = self.groups[group_id]
            if not res.accepted:
                # Release the lease immediately so a healthy worker can pick up the group without waiting for TTL!
                if g["status"] == "verifying" and g["lease_id"] == lease_id:
                    g["status"] = "pending"
                    g["reassignments"] += 1
                    g["lease_id"] = None
                    g["worker_id"] = None
                    g["leased_at"] = None
                    g["last_heartbeat"] = None
                    g["expires_at"] = None
                    self.total_reassignments += 1
                return self._record_rejection_locked(w, group_id, lease_id, res.reason, res.reduction_sha256)

            if g["status"] == "verified":
                return self._record_rejection_locked(w, group_id, lease_id, "already_verified", res.reduction_sha256)

            elapsed_group = (
                float(reported_group_seconds)
                if reported_group_seconds is not None and reported_group_seconds > 0
                else max(0.0, now_done - leased_at)
            )
            g["status"] = "verified"
            g["verified_by"] = worker_id
            g["reduction_sha256"] = res.reduction_sha256
            g["group_seconds"] = round(elapsed_group, 4)
            g["cpu_verify_seconds"] = round(res.cpu_verify_seconds, 4)
            g["lease_id"] = None
            g["worker_id"] = None
            g["leased_at"] = None
            g["last_heartbeat"] = None
            g["expires_at"] = None

            w.groups_verified += 1
            w.shards_verified += order["group_shards"]
            w.total_group_seconds += elapsed_group
            w.total_cpu_verify_seconds += res.cpu_verify_seconds

            if all(item["status"] == "verified" for item in self.groups.values()):
                self._completed_at = now_done

            self._emit_event(
                "root_verified",
                group_id=group_id,
                worker_id=worker_id,
                lease_id=lease_id,
                reduction_sha256=res.reduction_sha256,
                group_shards=order["group_shards"],
                group_seconds=round(elapsed_group, 4),
                cpu_verify_seconds=round(res.cpu_verify_seconds, 4),
            )
            return {
                "accepted": True,
                "reason": res.reason,
                "group_id": group_id,
                "reduction_sha256": res.reduction_sha256,
                "cpu_verify_seconds": round(res.cpu_verify_seconds, 4),
            }

    def _record_rejection_locked(
        self,
        w: WorkerStats,
        group_id: str,
        lease_id: str,
        reason: str,
        reduction_sha256: str,
    ) -> dict:
        w.roots_rejected += 1
        w.rejection_reasons[reason] = w.rejection_reasons.get(reason, 0) + 1
        self.total_rejected_roots += 1
        entry = {
            "group_id": group_id,
            "worker_id": w.worker_id,
            "lease_id": lease_id,
            "reason": reason,
            "reduction_sha256": reduction_sha256,
        }
        self.rejected_log.append(entry)
        self._emit_event("root_rejected", **entry)
        return {"accepted": False, "reason": reason, "group_id": group_id}

    def all_verified(self) -> bool:
        with self._lock:
            return all(g["status"] == "verified" for g in self.groups.values())

    def stats(self) -> dict:
        with self._lock:
            now = self._clock()
            self._reap_locked(now)
            verified = sum(1 for g in self.groups.values() if g["status"] == "verified")
            verifying = sum(1 for g in self.groups.values() if g["status"] == "verifying")
            leased = sum(1 for g in self.groups.values() if g["status"] == "leased")
            pending = sum(1 for g in self.groups.values() if g["status"] == "pending")
            wall = (self._completed_at or now) - self._started_at
            total_shards = sum(self.orders[gid]["group_shards"] for gid in self.order_sequence)
            verified_shards = sum(
                self.orders[gid]["group_shards"]
                for gid, g in self.groups.items()
                if g["status"] == "verified"
            )
            eff_g_hr = (verified / max(wall, 1e-6)) * 3600.0 if verified else 0.0
            return {
                "schema": TELEMETRY_SCHEMA,
                "direction": self.direction,
                "total_groups": len(self.groups),
                "verified_groups": verified,
                "verifying_groups": verifying,
                "leased_groups": leased,
                "pending_groups": pending,
                "total_shards": total_shards,
                "verified_shards": verified_shards,
                "reassignments_total": self.total_reassignments,
                "rejected_roots_total": self.total_rejected_roots,
                "wasted_dead_worker_seconds": round(self.wasted_dead_worker_seconds, 4),
                "wall_seconds": round(wall, 4),
                "effective_groups_per_hour": round(eff_g_hr, 2),
                "contributors": {wid: ws.to_dict() for wid, ws in sorted(self.workers.items())},
                "rejected_roots": list(self.rejected_log),
            }

    def write_summary(self) -> dict:
        s = self.stats()
        self.summary_path.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return s


def make_http_server(engine: CoordinatorEngine, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create a multi-threaded HTTP server wrapping `CoordinatorEngine`."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            return

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32 * 1024 * 1024:
                raise CollabError(f"invalid request content length: {length}")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _send_json(self, code: int, payload: dict) -> None:
            raw = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802
            if self.path == "/v1/stats":
                self._send_json(HTTPStatus.OK, engine.stats())
                return
            if self.path == "/v1/health":
                self._send_json(HTTPStatus.OK, {"ok": True, "all_verified": engine.all_verified()})
                return
            if self.path.startswith("/v1/shards/") and engine.archive_path is not None:
                gid = self.path.removeprefix("/v1/shards/")
                order = engine.orders.get(gid)
                if order is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown group"})
                    return
                with engine.archive_path.open("rb") as fh:
                    fh.seek(int(order["archive_byte_start"]))
                    data = fh.read(int(order["slice_bytes"]))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            try:
                body = self._read_json()
                if self.path == "/v1/lease":
                    lease = engine.assign_lease(body["worker_id"])
                    if lease is None:
                        self._send_json(HTTPStatus.OK, {"done": True, "lease": None})
                    else:
                        self._send_json(HTTPStatus.OK, {"done": False, "lease": lease})
                    return
                if self.path == "/v1/heartbeat":
                    res = engine.heartbeat(
                        body["worker_id"],
                        body["lease_id"],
                        int(body.get("progress_shards", 0)),
                    )
                    self._send_json(HTTPStatus.OK, res)
                    return
                if self.path == "/v1/submit":
                    raw_bytes = base64.b64decode(body["reduction_b64"].encode("ascii"))
                    res = engine.submit_root(
                        worker_id=body["worker_id"],
                        lease_id=body["lease_id"],
                        group_id=body["group_id"],
                        reduction_bytes=raw_bytes,
                        cuda_receipt=body["cuda_receipt"],
                        reported_group_seconds=body.get("group_seconds"),
                    )
                    status = HTTPStatus.OK if res["accepted"] else HTTPStatus.UNPROCESSABLE_ENTITY
                    self._send_json(status, res)
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except (KeyError, ValueError, CollabError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the Cashu collaborative proving HTTP coordinator.")
    parser.add_argument("--shard-index", type=Path, required=True)
    parser.add_argument("--shard-index-sha256", help="Optional expected sha256 of shard-index.json.")
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--program-key", type=Path, required=True)
    parser.add_argument("--cpu-checker", type=Path, required=True, help="Pinned replay-reduction-cpu binary.")
    parser.add_argument("--cpu-checker-sha256", required=True)
    parser.add_argument("--compose-dir", type=Path, required=True, help="Live reducer compose dir (groups/NNNNNN).")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Optional Core proof.bin to serve slices over HTTP.")
    parser.add_argument("--network", default="regtest")
    parser.add_argument("--group-size", type=int, default=GROUP_SIZE)
    parser.add_argument("--direction", choices=("backward", "forward"), default="backward")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--lease-ttl", type=float, default=1800.0)
    parser.add_argument("--heartbeat-timeout", type=float, default=120.0)
    parser.add_argument("--heartbeat-interval", type=float, default=30.0)
    args = parser.parse_args(argv)

    index_data, index_sha = load_shard_index(args.shard_index, args.shard_index_sha256)
    run_sha = sha256_file(args.run_json)
    orders = groups_from_shard_index(
        index_data,
        index_sha,
        run_manifest_sha256=run_sha,
        network=args.network,
        group_size=args.group_size,
    )
    engine = CoordinatorEngine(
        work_orders=orders,
        compose_dir=args.compose_dir,
        state_dir=args.state_dir,
        cpu_checker_path=args.cpu_checker,
        cpu_checker_sha256=require_hex64(args.cpu_checker_sha256, "cpu_checker_sha256"),
        run_json_path=args.run_json,
        program_key_path=args.program_key,
        archive_path=args.archive,
        direction=args.direction,
        lease_ttl_s=args.lease_ttl,
        heartbeat_timeout_s=args.heartbeat_timeout,
        heartbeat_interval_s=args.heartbeat_interval,
    )
    server = make_http_server(engine, args.host, args.port)
    addr, bound_port = server.server_address
    print(json.dumps({"listening": f"http://{addr}:{bound_port}", "groups": len(orders), "direction": args.direction}), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.write_summary()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

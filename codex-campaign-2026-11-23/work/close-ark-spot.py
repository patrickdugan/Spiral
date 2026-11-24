"""Verify the named Spot checkpoint index, then end only its compute lease."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
import time


WORK = Path(__file__).resolve().parent
NAME = "ark-mnr04-a100-a6e283d956"
VM = 1178271
ACCESS = "object-storage/access-keys"
MARK = NAME + "-closeout-read"


def main(credential_path):
    state = json.loads((WORK / "hyperstack-ark-state.json").read_bytes())
    if state["name"] != NAME or state["vm_id"] != VM or state["spot"] is not True:
        raise ValueError("unexpected lease identity")
    tools = runpy.run_path(str(WORK / "hyperstack-shinigami-storage.py"))
    pilot = tools["Pilot"].__new__(tools["Pilot"])
    pilot.name, pilot.vm_id = NAME, VM
    pilot.credential = credential_path.read_text(encoding="utf-8-sig").strip()
    helper = tools["common"]
    pilot.http = helper["urllib"].request.build_opener(helper["NoRedirect"]())
    machine = pilot.vm(missing_ok=True)
    if machine is None or machine["status"] == "DELETED":
        print(json.dumps({"stage": "vm_deleted", "vm_id": VM}), flush=True)
        return

    def matching_keys():
        return [
            row for row in pilot.api("GET", ACCESS)["access_keys"]
            if row["region"] == "CANADA-1" and row["description"] == MARK
        ]

    if matching_keys():
        raise RuntimeError("closeout credential already exists")
    try:
        response = pilot.api("POST", ACCESS, {"description": MARK, "region": "CANADA-1"})
        entry = next(item for item in (response, response.get("data"), response.get("access_key"))
                     if isinstance(item, dict) and item.get("secret_key"))
        key, = matching_keys()
        if key["access_key"] != entry["access_key"]:
            raise ValueError("closeout access key identity mismatch")
        store = tools["boto3"].client(
            "s3", endpoint_url="https://ca1.obj.nexgencloud.io", region_name="us-east-1",
            aws_access_key_id=entry["access_key"], aws_secret_access_key=entry["secret_key"],
            config=tools["Config"](signature_version="s3v4", s3={"addressing_style": "path"},
                                   connect_timeout=8, read_timeout=20),
        )
        result = store.get_object(Bucket=NAME, Key="out/index.json")
        with result["Body"] as stream:
            raw = stream.read(4 * 1024**2 + 1)
        index = json.loads(raw)
        count = index["entries"]
        batches = index["batches"]
        if (len(raw) > 4 * 1024**2 or index["schema"] != "ark/spot-memo-export/v1"
                or index["seed_sha256"] != state["seed_sha256"]
                or not 0 < count == sum(batch["entries"] for batch in batches)):
            raise ValueError("unexpected checkpoint index")
        parts = [part for batch in batches for part in batch["parts"]]
        if not parts or parts[-1]["key"] != f"out/{len(parts) - 1:06}.part":
            raise ValueError("unexpected checkpoint part inventory")
        latest = store.head_object(Bucket=NAME, Key=parts[-1]["key"])
        if latest["ContentLength"] != parts[-1]["bytes"]:
            raise ValueError("latest durable checkpoint part differs from its index")
        proof_objects = {}
        for name in ("compressed.bin", "results.tar.gz"):
            try:
                proof_objects[name] = store.head_object(Bucket=NAME, Key=name)["ContentLength"]
            except tools["ClientError"] as error:
                if error.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                    raise
        if proof_objects:
            raise RuntimeError("proof output exists; retain worker for coordinator retrieval")
        with tempfile.NamedTemporaryFile(dir=WORK, delete=False) as saved:
            saved.write(raw)
        Path(saved.name).replace(WORK / "ark-spot-closeout-durable-index.json")
        print(json.dumps({"stage": "durable_index_retrieved", "entries": count, "parts": len(parts),
                          "index_sha256": hashlib.sha256(raw).hexdigest()}), flush=True)
        # The running controller sees this exact VM disappear. It retains the
        # private bucket and performs the audited GitHub release from this index.
        pilot.api("DELETE", f"core/virtual-machines/{VM}", missing_ok=True)
    finally:
        for key in matching_keys():
            pilot.api("DELETE", f"{ACCESS}/{int(key['id'])}", missing_ok=True)
    end = time.monotonic() + 120
    while time.monotonic() < end:
        machine = pilot.vm(missing_ok=True)
        if machine is None or machine["status"] == "DELETED":
            print(json.dumps({"stage": "vm_deleted", "vm_id": VM}), flush=True)
            return
        time.sleep(3)
    raise RuntimeError("deletion has not yet been confirmed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

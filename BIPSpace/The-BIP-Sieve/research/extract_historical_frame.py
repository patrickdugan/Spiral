#!/usr/bin/env python3
"""Extract a retrospective metadata frame from a pinned bitcoin/bips checkout.

Usage:
  python research/extract_historical_frame.py --bips-root /path/to/bips \
      --output historical-frame.json --verify-against historical-frame.json

The optional verification argument checks each source file against the recorded
Git blob hash. A commit label by itself cannot verify a modified working tree.
Only metadata is emitted. Network deployment outcomes require separate coding.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

PIN = "b34d9f751791d4feb22feff4f2ed00bcac83961b"
START = "2011-01-01"
END = "2017-12-31"
DATE = "2026-11-13"


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def index_rows(text):
    result = []
    for block in re.split(r"\n\|-", text):
        fields = [
            re.sub(r"^\|\s?", "", line).strip()
            for line in block.splitlines()
            if re.match(r"^\|(?![}-])", line)
        ]
        match = re.fullmatch(
            r"\[\[(bip-(\d+)\.(?:md|mediawiki))\|\d+\]\]",
            fields[0] if fields else "",
        )
        if not match:
            continue
        if len(fields) < 6:
            raise ValueError("Incomplete index row: " + match[1])
        if not fields[1].startswith("Consensus"):
            continue
        result.append({
            "number": int(match[2]),
            "path": match[1],
            "layer": fields[1],
            "title": fields[2],
            "index_authors": fields[3],
            "type": fields[4],
            "official_status": fields[5],
        })
    if not result or len({r["number"] for r in result}) != len(result):
        raise ValueError("Index is empty or contains duplicate consensus rows")
    return result


def header(text):
    match = re.search(r"<pre>(.*?)</pre>|\x60{3}[^\n]*\n(.*?)\x60{3}", text, re.S)
    if not match:
        raise ValueError("Missing metadata block")
    block = next(g for g in match.groups() if g is not None)
    fields = dict(re.findall(
        r"^\s*(BIP|Layer|Title|Status|Type|Assigned|Created):\s*(.*?)\s*$",
        block,
        re.M,
    ))
    assigned = fields.get("Assigned", fields.get("Created"))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", assigned or ""):
        raise ValueError("Missing or malformed assignment date")
    fields["assigned"] = assigned
    return fields


def build(root, expected=None):
    index_data = (root / "README.mediawiki").read_bytes()
    index_hash = git_blob(index_data)
    if expected and index_hash != expected["index_blob_sha"]:
        raise ValueError("The index differs from the recorded source snapshot")
    expected_rows = {r["path"]: r for r in expected["records"]} if expected else {}
    rows = []
    for row in index_rows(index_data.decode()):
        data = (root / row["path"]).read_bytes()
        sha = git_blob(data)
        if expected and sha != expected_rows[row["path"]]["blob_sha"]:
            raise ValueError("Source blob differs: " + row["path"])
        meta = header(data.decode())
        for source_field, index_field in (
            ("BIP", "number"),
            ("Layer", "layer"),
            ("Title", "title"),
            ("Status", "official_status"),
            ("Type", "type"),
        ):
            if str(meta.get(source_field)) != str(row[index_field]):
                raise ValueError("Index/header disagreement: " + row["path"] + " " + source_field)
        assigned = meta["assigned"]
        included = START <= assigned <= END
        row.update({
            "assigned": assigned,
            "included": included,
            "exclusion_reason": None if included else "Assigned date outside 2011–2017",
            "blob_sha": sha,
            "source_url": f"https://github.com/bitcoin/bips/blob/{PIN}/{row['path']}",
            "network_outcome_independently_coded_here": False,
        })
        rows.append(row)
    included_rows = [r for r in rows if r["included"]]
    counts = Counter((r["layer"], r["official_status"]) for r in included_rows)
    return {
        "schema_version": "0.2",
        "title": "Retrospective frame of consensus-labelled BIP documents assigned in 2011–2017",
        "observed_on": DATE,
        "repository": "bitcoin/bips",
        "source_commit": PIN,
        "index_path": "README.mediawiki",
        "index_blob_sha": index_hash,
        "selection_rule": {
            "index_layer_starts_with": "Consensus",
            "assigned_date_start_inclusive": START,
            "assigned_date_end_inclusive": END,
            "applied_to": "Every consensus-labelled row in the pinned current index.",
            "rule_timing": "Retrospective coverage audit after the purposive version 0.1 cohort.",
        },
        "interpretation_limits": [
            "Current metadata and present semantics can postdate the assignment year.",
            "Document counts include components and activation rules from shared episodes.",
            "Closed merges several earlier labels; the reason for closure needs separate evidence.",
            "Complete and Deployed are archive metadata; this extraction does not establish chain outcomes.",
            "Unnumbered ideas and documents outside the declared layer/date frame are excluded.",
            "The resulting counts describe this archive frame and supply no causal adoption estimate.",
        ],
        "counts": {
            "all_consensus_labelled_documents": len(rows),
            "included": len(included_rows),
            "excluded_by_date": len(rows) - len(included_rows),
            "current_metadata_by_layer_and_status": [
                {"layer": layer, "status": status, "documents": count}
                for (layer, status), count in sorted(counts.items())
            ],
        },
        "records": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bips-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-against", type=Path)
    args = parser.parse_args()
    expected = json.loads(args.verify_against.read_text()) if args.verify_against else None
    result = build(args.bips_root, expected)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))


if __name__ == "__main__":
    main()

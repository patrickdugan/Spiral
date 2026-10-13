"""Redact a Claude Code session export down to one investigation, without private review material.

Usage: python -I redact_export.py <export dir> <output dir> <terms.json>

Scope.  The log is meant to show this investigation only, but every turn's context also carried the
assistant's memory index (one line per note, most about the author's other work) and a git-status
snapshot of the whole working tree.  So each decoded string first loses every memory-index line whose
title is not in KEEP_MEMORY_TITLES (the notes this investigation wrote), each run of them collapsed into
one placeholder line, the session-start git-status snapshot, and every line holding one of the terms
file's "other_work_markers" (names of other projects' files).  The result of every Read of a memory
note that the session did not itself write is withheld, and the app's configuration files (DROP_FILES)
are not copied.

Privacy.  Some of that context, and the later stretch where this redaction was built, name private
security reviews of third-party software.  The terms live in a JSON file that is NOT committed
(publishing the terms would defeat the purpose).  Its lists:

  "memory_titles":       titles of memory-index lines about third-party reviews,
  "memory_titles_other": titles of memory-index lines about the author's machine,
  "dir_suffixes":        suffixes of working-tree directory names to replace in "?? <dir>/" lines,
  "tokens":              [regex, replacement, flags] triples,
  "withhold_substrings": case-insensitive substrings, and
  "withhold_words":      case-insensitive regexes matched between non-letters,
                         that may not survive anywhere outside base64 data.

JSON and JSON-lines files are processed record by record on DECODED strings, so escapes cannot hide a
boundary and a rule cannot run past the end of a string.  After the scope rules, each string gets the
memory-line rules, the directory rule and the token rules; if a withheld term is still present outside a
base64 run, the offending lines (or the whole string, if it has one line) become a placeholder.  A record
is re-serialized (compact, UTF-8) only if it changed, so untouched records keep their bytes and every
record still parses.  Plain-text files get the same rules on raw text, line by line.  The report counts
replacements per file and per category only, so it reveals nothing about the terms.
"""
import json
import re
import sys
from pathlib import Path

PLACEHOLDER = "[withheld by redaction: this text named the private review terms]"
REVIEW_LINE = "- [redacted: third-party security review memory]"
MACHINE_LINE = "- [redacted: memory about the author's machine or infrastructure]"
KEEP_MEMORY_TITLES = {"Feedback-channel programme", "RSI atlas + feedback patch", "Embedded chart data", "X posts access"}
OTHER_WORK_LINE = "[memory index entries about the author's other work: withheld]"
GIT_STATUS_LINE = "[git status of the author's whole working tree at session start: withheld]"
MEMORY_READ_TEXT = "[content of a memory note from the author's other work: withheld]"
DROP_FILES = {"metadata.json", "local-session-state.json"}
CATEGORIES = ("memory_index_lines_other_work", "other_work_lines", "git_status_snapshots", "memory_reads_withheld",
              "memory_index_lines_review", "memory_index_lines_machine", "working_tree_dirs", "tokens",
              "lines_withheld", "strings_withheld", "text_lines_withheld", "unparsed_records")

memory_anywhere = re.compile(r"- \[([^\]\\\n]{1,80})\]\(([a-z0-9][a-z0-9-]*\.md)\)")
redacted_line = re.compile(r"- \[redacted: [^\]\n]*\]")
OTHER_TEXT_LINE = "[text about the author's other work: withheld]"
git_status = re.compile(r"This is the git status at the start of the conversation\..*?Recent commits:\n"
                        r"(?:[0-9a-f]{7,40} [^\n]*(?:\n|$))*", re.DOTALL)
base64_run = re.compile(r"[A-Za-z0-9+/=]{40,}")


def load_rules(terms):
    def line_rules(title):
        head = r"- \[" + re.escape(title) + r"\]\("
        return (re.compile(head + r"[^)\n]*\)[^\n]*"),                # line ended by a real newline
                re.compile(head + r"[^)]*\)(?:\\[^n]|[^\"\\\n])*"))  # inside JSON text: ends at \n or a closing quote
    review = [r for t in terms["memory_titles"] for r in line_rules(t)]
    machine = [r for t in terms.get("memory_titles_other", []) for r in line_rules(t)]
    dirs = re.compile(r"\?\? [A-Za-z0-9_-]*(" + "|".join(re.escape(s) for s in terms["dir_suffixes"]) + r")/")
    tokens = [(re.compile(p, re.IGNORECASE if flag == "i" else 0), r)
              for p, r, flag in ((t[0], t[1], t[2] if len(t) > 2 else "") for t in terms["tokens"])]
    withhold = re.compile("|".join([re.escape(s) for s in terms.get("withhold_substrings", [])]
                                   + [r"(?<![A-Za-z])(?:" + w + r")(?![A-Za-z])" for w in terms.get("withhold_words", [])]),
                          re.IGNORECASE)
    return review, machine, dirs, tokens, withhold


def scope(s, counts, markers):
    """Remove what belongs to the author's other work: the git-status snapshot, every line holding a
    memory-index entry not written by this investigation (anywhere in the line, so line-numbered and
    JSON-escaped copies are caught), and every line holding an other-work marker from the terms file."""
    s, n = git_status.subn(GIT_STATUS_LINE + "\n", s)
    counts["git_status_snapshots"] += n
    out, run = [], None
    for line in s.split("\n"):
        kind = None
        if any(m.group(1) not in KEEP_MEMORY_TITLES for m in memory_anywhere.finditer(line)) \
                or redacted_line.search(line):
            kind = OTHER_WORK_LINE
            counts["memory_index_lines_other_work"] += 1
        elif markers is not None and markers.search(line) and not base64_only(line, markers):
            kind = OTHER_TEXT_LINE
            counts["other_work_lines"] += 1
        if kind is None:
            out.append(line)
        elif kind != run:
            out.append(kind)
        run = kind
    return "\n".join(out)


def base64_only(line, markers):
    runs = [m.span() for m in base64_run.finditer(line)]
    return all(any(a <= m.start() < b for a, b in runs) for m in markers.finditer(line))


def main():
    src, dst, terms_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    terms = json.loads(terms_path.read_text(encoding="utf-8"))
    review_rules, machine_rules, dir_rule, token_rules, withhold = load_rules(terms)
    marker_list = terms.get("other_work_markers", [])
    markers = re.compile("|".join(re.escape(m) for m in marker_list), re.IGNORECASE) if marker_list else None
    dst.mkdir(parents=True, exist_ok=True)

    def residual(s):
        runs = [m.span() for m in base64_run.finditer(s)]
        return any(not any(a <= m.start() < b for a, b in runs) for m in withhold.finditer(s))

    def rules(s, counts):
        for rule in review_rules:
            s, n = rule.subn(REVIEW_LINE, s)
            counts["memory_index_lines_review"] += n
        for rule in machine_rules:
            s, n = rule.subn(MACHINE_LINE, s)
            counts["memory_index_lines_machine"] += n
        s, n = dir_rule.subn("?? [redacted-review-dir]/", s)
        counts["working_tree_dirs"] += n
        for rule, replacement in token_rules:
            s, n = rule.subn(replacement, s)
            counts["tokens"] += n
        return s

    def walk(obj, counts):
        if isinstance(obj, str):
            new = rules(scope(obj, counts, markers), counts)
            if not residual(new):
                return new
            if "\n" in new:
                lines = new.split("\n")
                for i, line in enumerate(lines):
                    if residual(line):
                        lines[i] = PLACEHOLDER
                        counts["lines_withheld"] += 1
                new = "\n".join(lines)
                if not residual(new):
                    return new
            counts["strings_withheld"] += 1
            return PLACEHOLDER
        if isinstance(obj, list):
            return [walk(v, counts) for v in obj]
        if isinstance(obj, dict):
            return {walk(k, counts) if isinstance(k, str) else k: walk(v, counts) for k, v in obj.items()}
        return obj

    def plain(text, counts):
        text = rules(scope(text, counts, markers), counts)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if residual(line):
                lines[i] = PLACEHOLDER
                counts["text_lines_withheld"] += 1
        return "\n".join(lines)

    def blocks(obj):
        msg = obj.get("message") if isinstance(obj, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        return content if isinstance(content, list) else []

    def foreign_memory_reads(records):
        """Tool-use ids of Reads of memory notes this session did not write (MEMORY.md goes through scope())."""
        written, reads = set(), {}
        for record in records:
            try:
                obj = json.loads(record) if record.strip() else None
            except json.JSONDecodeError:
                continue
            for b in blocks(obj):
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                path = str(b.get("input", {}).get("file_path", "")).replace("\\", "/")
                if "/memory/" not in path:
                    continue
                name = path.rsplit("/", 1)[-1]
                if b.get("name") in ("Write", "Edit"):
                    written.add(name)
                elif b.get("name") == "Read" and name != "MEMORY.md":
                    reads[b.get("id")] = name
        return {i for i, name in reads.items() if name not in written}

    def withhold_reads(obj, ids, counts):
        if not ids or not isinstance(obj, dict):
            return obj
        hit = False
        for b in blocks(obj):
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in ids:
                b["content"] = MEMORY_READ_TEXT
                hit = True
        if hit:
            counts["memory_reads_withheld"] += 1
            if "toolUseResult" in obj:
                obj["toolUseResult"] = MEMORY_READ_TEXT
        return obj

    report = {}
    skipped = set(terms.get("skip_files", [])) | DROP_FILES
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if rel.name in skipped:
            continue
        text = path.read_text(encoding="utf-8")
        counts = dict.fromkeys(CATEGORIES, 0)
        if path.suffix in (".jsonl", ".json"):
            records = text.split("\n") if path.suffix == ".jsonl" else [text]
            foreign = foreign_memory_reads(records)
            out = []
            for record in records:
                if not record.strip():
                    out.append(record)
                    continue
                try:
                    obj = json.loads(record)
                except json.JSONDecodeError:
                    counts["unparsed_records"] += 1
                    out.append(plain(record, counts))
                    continue
                before = dict(counts)
                new = walk(withhold_reads(obj, foreign, counts), counts)
                if counts == before:
                    out.append(record)
                elif path.suffix == ".jsonl":
                    out.append(json.dumps(new, ensure_ascii=False, separators=(",", ":")))
                else:
                    out.append(json.dumps(new, ensure_ascii=False, indent=2))
            text = "\n".join(out)
        else:
            text = plain(text, counts)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        if any(counts.values()):
            report[str(rel).replace("\\", "/")] = {k: v for k, v in counts.items() if v}
    total = sum(sum(c.values()) for c in report.values())
    print(f"files written: {sum(1 for p in dst.rglob('*') if p.is_file())}; replacements: {total}")
    for rel, counts in sorted(report.items()):
        print(f"  {rel}: {counts}")
    (dst / "REDACTIONS.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

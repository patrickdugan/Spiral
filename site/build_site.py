"""Build the static GitHub Pages site for the feedback-channel notes.

Usage:
    python site/build_site.py <repo root> <output dir> <commit sha>

Needs markdown-it-py (3.x) and Pygments on the Python path. The site has:
  index.html            the findings note (paper/feedback_channel_findings.md), rendered
  notes/<stem>.html     every supporting note, rendered
  lean/index.html       the Lean claims table (lean/CLAIMS.md) and the list of Lean sources
  lean/<path>.html      each Lean source, highlighted, with a line anchor per line (#L-12)
Math in the notes is written as \\( ... \\) and \\[ ... \\]; it is protected from the Markdown
renderer and typeset in the browser by MathJax. Links between notes become links between pages;
links to Lean sources become links to the highlighted pages; links to any other repository file
become GitHub links pinned to <commit sha>, so the site never points at a moving branch.
"""
import html
import re
import shutil
import sys
from pathlib import Path

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

REPO_URL = "https://github.com/patrickdugan/Spiral"

NOTES = [  # (path in repo, short title for navigation)
    ("paper/rl_training_signal_limits.md", "Training-signal limits"),
    ("paper/evaluation_design_calculus.md", "Evaluation design calculus"),
    ("paper/evaluation_feedback_insertions.md", "Feedback insertions"),
    ("paper/evaluation_feedback_lattice.md", "Partial leakage as a lattice"),
    ("paper/leak_topology.md", "Leak topology"),
    ("paper/evaluation_feedback_multigen.md", "The selection gap across generations"),
    ("paper/evaluation_feedback_composition.md", "Composition laws"),
    ("paper/selection_law_kl_containment.md", "Best-of-K in the KL slice"),
    ("paper/judge_shared_error_measurement.md", "Measuring the judge's shared error"),
    ("paper/gold_calibration_second_grader.md", "Gold calibration"),
    ("paper/feedback_channel_rsitopology_crosswalk.md", "RSITopology crosswalk"),
    ("paper/rsi_claims_atlas.md", "Claims atlas"),
    ("docs/feedback_channel_journey_2026-10-11_13.md", "Journey map"),
]
FINDINGS = "paper/feedback_channel_findings.md"

MATH = re.compile(r"\\\[.*?\\\]|\\\(.*?\\\)|\$\$.*?\$\$", re.DOTALL)
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)

CSS = """
:root {
  --bg: #f6f7f9; --surface: #ffffff; --ink: #1b2330; --muted: #5a6577; --rule: #d9dee6;
  --accent: #2f5d8a; --code-bg: #eef1f5;
  --font-display: "Spectral", "Iowan Old Style", Georgia, serif;
  --font-body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #12161d; --surface: #1a202a; --ink: #e3e8ef; --muted: #9aa5b5; --rule: #2c3442;
          --accent: #8fb4dc; --code-bg: #202733; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body);
       font-size: 1.0625rem; line-height: 1.6; padding-inline: 16px; padding-block: 0 4rem; }
.top { max-width: 52rem; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 0.4rem 1.25rem;
       align-items: baseline; padding-block: 1rem; border-bottom: 1px solid var(--rule); }
.top .site { font-family: var(--font-display); font-weight: 600; font-size: 1.1rem; color: var(--ink);
             text-decoration: none; margin-right: auto; }
.top a { color: var(--accent); text-decoration: none; font-size: 0.95rem; }
.top a:hover, .top a:focus-visible { text-decoration: underline; }
main { max-width: 52rem; margin: 0 auto; padding-top: 2rem; }
main > * { max-width: 100%; }
h1, h2, h3 { font-family: var(--font-display); line-height: 1.25; text-wrap: balance; }
h1 { font-size: clamp(1.8rem, 4.5vw, 2.4rem); margin: 0 0 1rem; }
h2 { font-size: 1.4rem; margin: 2.2rem 0 0.8rem; }
h3 { font-size: 1.15rem; margin: 1.6rem 0 0.6rem; }
p, li { max-width: 68ch; }
a { color: var(--accent); text-underline-offset: 0.18em; }
code { font-family: var(--font-mono); font-size: 0.86em; background: var(--code-bg); padding: 0.05em 0.3em; border-radius: 3px; }
pre { background: var(--code-bg); padding: 0.8rem 1rem; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; font-size: 0.93rem; }
.table-wrap { overflow-x: auto; max-width: 100%; margin: 1rem 0; }
th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { font-family: var(--font-mono); font-size: 0.75rem; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); font-weight: 500; }
blockquote { margin: 1rem 0; padding-left: 1rem; border-left: 3px solid var(--rule); color: var(--muted); }
.meta { color: var(--muted); font-size: 0.92rem; }
.notes-list { display: grid; gap: 0.35rem; padding-left: 1.2rem; }
mjx-container[display="true"] { overflow-x: auto; overflow-y: hidden; max-width: 100%; }
mjx-container:not([display="true"]) { display: inline-block; max-width: 100%; overflow-x: auto; overflow-y: hidden; vertical-align: middle; }
code { overflow-wrap: anywhere; }
pre, .lean-src { max-width: 100%; overflow-x: auto; }
pre code { overflow-wrap: normal; }
h1 { overflow-wrap: anywhere; }
footer { max-width: 52rem; margin: 3rem auto 0; border-top: 1px solid var(--rule); padding-top: 1rem; color: var(--muted); font-size: 0.9rem; }
.lean-src { font-family: var(--font-mono); font-size: 0.85rem; line-height: 1.5; }
.lean-src .highlight pre { background: var(--code-bg); }
.lean-src a[id^="L-"] { scroll-margin-top: 4rem; }
"""

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;1,400&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="{root}style.css">
<script>
window.MathJax = {{ tex: {{ inlineMath: [["\\\\(", "\\\\)"]], displayMath: [["\\\\[", "\\\\]"], ["$$", "$$"]] }},
                   options: {{ skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"] }} }};
</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-chtml.js"></script>
</head>
<body>
<nav class="top" aria-label="Site">
  <a class="site" href="{root}index.html">Feedback-channel findings</a>
  <a href="{root}notes/index.html">Notes</a>
  <a href="{root}lean/index.html">Lean proofs</a>
  <a href="{root}notes/feedback_channel_journey_2026-10-11_13.html">Journey</a>
  <a href="{repo}/tree/{sha}">Source</a>
</nav>
<main>
"""

FOOT = """</main>
<footer>
  Built from <a href="{repo}/tree/{sha}">patrickdugan/Spiral@{short}</a>. Every number in these notes is exact
  arithmetic on declared quantities; no model, judge or grader was run. Each module's verifier regenerates
  its receipt with the SHA-256 of its sources.
</footer>
</body>
</html>
"""


def protect_math(text):
    """Replace math and code spans with placeholders so the Markdown renderer leaves them alone."""
    saved = []

    def keep(m):
        saved.append(m.group(0))
        return f"MATHPROTECT{len(saved) - 1}END"

    # code first, so math-like text inside code stays code
    code_saved = []

    def keep_code(m):
        code_saved.append(m.group(0))
        return f"CODEPROTECT{len(code_saved) - 1}END"

    text = CODE.sub(keep_code, text)
    text = MATH.sub(keep, text)
    text = re.sub(r"CODEPROTECT(\d+)END", lambda m: code_saved[int(m.group(1))], text)
    return text, saved


def restore_math(rendered, saved):
    return re.sub(r"MATHPROTECT(\d+)END", lambda m: html.escape(saved[int(m.group(1))], quote=False), rendered)


class Site:
    def __init__(self, repo, out, sha):
        self.repo, self.out, self.sha = repo, out, sha
        self.md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table").enable("strikethrough")
        self.note_pages = {}  # repo path -> site path
        for path, _ in NOTES:
            if (repo / path).exists():
                self.note_pages[path] = "notes/" + Path(path).stem + ".html"
        self.note_pages[FINDINGS] = "index.html"
        self.lean_files = sorted(p.relative_to(repo).as_posix() for p in (repo / "lean").rglob("*.lean")
                                 if ".lake" not in p.parts) if (repo / "lean").exists() else []

    def blob(self, path, anchor=""):
        return f"{REPO_URL}/blob/{self.sha}/{path}{anchor}"

    def resolve(self, href, from_path):
        """Map a link written in a repository file to a link on the site."""
        if re.match(r"^[a-z]+:", href) or href.startswith("#"):
            return href
        target, _, anchor = href.partition("#")
        anchor = "#" + anchor if anchor else ""
        base = Path(from_path).parent
        resolved = (base / target).as_posix()
        parts = []
        for part in resolved.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        resolved = "/".join(parts)
        if resolved in self.note_pages:
            return ("@ROOT@" + self.note_pages[resolved]) + anchor
        if resolved.endswith(".lean") and resolved in self.lean_files:
            m = re.match(r"#L(\d+)", anchor)
            return "@ROOT@" + resolved[:-5] + ".html" + (f"#L-{m.group(1)}" if m else anchor)
        return self.blob(resolved, anchor)

    def render_md(self, path, root):
        text = (self.repo / path).read_text(encoding="utf-8")
        protected, saved = protect_math(text)
        tokens = self.md.parse(protected)
        for tok in tokens:
            for child in tok.children or []:
                if child.type == "link_open":
                    href = child.attrGet("href") or ""
                    child.attrSet("href", self.resolve(href, path).replace("@ROOT@", root))
        body = self.md.renderer.render(tokens, self.md.options, {})
        body = restore_math(body, saved)
        body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), Path(path).stem)
        return title, body

    def page(self, rel_out, title, body):
        depth = rel_out.count("/")
        root = "../" * depth
        doc = (HEAD.format(title=html.escape(title), root=root, repo=REPO_URL, sha=self.sha)
               + body + FOOT.format(repo=REPO_URL, sha=self.sha, short=self.sha[:7]))
        target = self.out / rel_out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(doc, encoding="utf-8", newline="\n")

    def build(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        (self.out / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8", newline="\n")
        # findings as the home page
        title, body = self.render_md(FINDINGS, "")
        self.page("index.html", "Feedback-Channel Findings", body)
        # notes
        items = []
        for path, short in NOTES:
            if path not in self.note_pages:
                continue
            rel = self.note_pages[path]
            title, body = self.render_md(path, "../")
            src = f'<p class="meta">Source: <a href="{self.blob(path)}">{html.escape(path)}</a></p>\n'
            self.page(rel, title, src + body)
            items.append(f'<li><a href="{Path(rel).name}">{html.escape(short)}</a> '
                         f'<span class="meta">({html.escape(path)})</span></li>')
        self.page("notes/index.html", "Notes",
                  "<h1>Notes</h1>\n<p>The findings page summarizes these notes; each carries its own evidence "
                  "levels, files, and the commands that regenerate its receipt.</p>\n"
                  '<ul class="notes-list">\n' + "\n".join(items) + "\n</ul>\n")
        # Lean sources
        lexer = get_lexer_by_name("lean4")
        fmt = HtmlFormatter(linenos="inline", anchorlinenos=True, lineanchors="L", cssclass="highlight")
        style = fmt.get_style_defs(".highlight")
        (self.out / "lean").mkdir(parents=True, exist_ok=True)
        (self.out / "lean" / "pygments.css").write_text(style + "\n", encoding="utf-8", newline="\n")
        listing = []
        for rel in self.lean_files:
            src = (self.repo / rel).read_text(encoding="utf-8")
            code = highlight(src, lexer, fmt)
            out_rel = rel[:-5] + ".html"
            depth = out_rel.count("/")
            css = "../" * (depth - 1) + "pygments.css"
            body = (f'<link rel="stylesheet" href="{css}">\n<h1>{html.escape(rel)}</h1>\n'
                    f'<p class="meta"><a href="{self.blob(rel)}">View on GitHub</a></p>\n'
                    f'<div class="lean-src">{code}</div>\n')
            self.page(out_rel, rel, body)
            listing.append(f'<li><a href="{"/".join(out_rel.split("/")[1:])}">{html.escape(rel)}</a></li>')
        claims = ""
        if (self.repo / "lean/CLAIMS.md").exists():
            _, claims = self.render_md("lean/CLAIMS.md", "../")
        self.page("lean/index.html", "Lean proofs",
                  (claims or "<h1>Lean proofs</h1>\n")
                  + "<h2>Sources</h2>\n<ul class=\"notes-list\">\n" + "\n".join(listing) + "\n</ul>\n")
        return len(items), len(listing)


def main():
    repo, out, sha = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
    notes, lean = Site(repo, out, sha).build()
    print(f"built {out}: findings, {notes} notes, {lean} Lean sources")


if __name__ == "__main__":
    main()

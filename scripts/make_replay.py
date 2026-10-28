"""Build docs/index.html: a static replay of real poltergeist output, plus the benchmark table if results exist.

    python scripts/make_replay.py

Nothing runs in the browser. The page is a recording, and says so.
"""

import datetime
import html
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pre(text: str) -> str:
    # Numeric references keep the file ASCII-only (a recorded look-alike letter stays a look-alike on screen, not in the source).
    return "<pre>" + html.escape(text.rstrip()).encode("ascii", "xmlcharrefreplace").decode("ascii") + "</pre>"


def results_section(results: list[dict]) -> str:
    if not results:
        return "<p>No model results have been recorded yet.</p>"
    rows = []
    for result in results:
        for mode, data in result["modes"].items():
            s = data["summary"]
            pct = lambda v: "-" if v is None else f"{round(v * 100)}%"  # noqa: E731
            rows.append(
                f"<tr><td>{html.escape(result['label'])}</td><td>{mode}</td><td>{pct(s['dev_category'])}</td>"
                f"<td>{pct(s['real_category'])}</td><td>{pct(s['heldout_category'])}</td><td>{pct(s['heldout_fix'])}</td>"
                f"<td>{pct(s['valid'])}</td><td>{s['median_seconds']:.0f}s</td></tr>"
            )
    base = results[0]["lore_only"]["summary"]
    rows.append(
        f"<tr><td>no model: platform facts only</td><td>lookup</td><td>{round(base['dev_category'] * 100)}%</td>"
        f"<td>{round(base['real_category'] * 100)}%</td><td>{round(base['heldout_category'] * 100)}%</td><td>-</td><td>-</td><td>-</td></tr>"
    )
    return (
        '<div class="scroll"><table><thead><tr><th>Model</th><th>Prompt</th><th>Category, dev (15)</th><th>of which real (5)</th>'
        "<th>Category, held-out (10)</th><th>Fix accepted, held-out</th><th>Valid JSON</th><th>Median time</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>poltergeist: a replay</title>
<style>
:root { --bg:#f7f5f2; --fg:#1d1b22; --muted:#5b5864; --card:#ffffff; --line:#d9d4cc; --accent:#6b3fa0; --code-bg:#1d1b22; --code-fg:#ece8f4; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#14121a; --fg:#ece8f4; --muted:#a29db0; --card:#1d1a26; --line:#322e3f; --accent:#b58cf0; --code-bg:#0e0c13; --code-fg:#ece8f4; } }
:root[data-theme="dark"] { --bg:#14121a; --fg:#ece8f4; --muted:#a29db0; --card:#1d1a26; --line:#322e3f; --accent:#b58cf0; --code-bg:#0e0c13; --code-fg:#ece8f4; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:860px; margin:0 auto; padding:32px 16px 64px; }
h1 { font-size:2rem; margin:0 0 4px; } h2 { font-size:1.25rem; margin:40px 0 8px; }
.lede { color:var(--muted); margin:0 0 24px; }
.note { border-left:4px solid var(--accent); background:var(--card); padding:12px 16px; border-radius:0 8px 8px 0; }
pre { background:var(--code-bg); color:var(--code-fg); padding:14px 16px; border-radius:8px; overflow-x:auto; font:13px/1.5 ui-monospace, "Cascadia Mono", Consolas, monospace; white-space:pre-wrap; word-break:break-word; }
.scroll { overflow-x:auto; } table { border-collapse:collapse; width:100%; font-size:14px; background:var(--card); }
th, td { border:1px solid var(--line); padding:6px 10px; text-align:left; } th { background:var(--bg); }
code { font-family:ui-monospace, Consolas, monospace; }
</style>
</head>
<body>
<main>
<h1>poltergeist</h1>
<p class="lede">Find the characters you cannot see, then ask a model that runs on your own machine about the bugs they cause.</p>
<p class="note">This page is a <strong>recording</strong> of real command output, made on __DATE__ by <code>scripts/make_replay.py</code>.
Nothing runs in your browser and no model is called from this page.</p>

<h2>1. A folder of haunted files</h2>
<p>Seven files that look normal in an editor. One of them carries a hidden instruction that a model would read and you would not.</p>
__SCAN__

<h2>2. The exorcism, as a dry run</h2>
<p>Every hidden character is shown as a visible marker, and nothing is written unless you pass <code>--write</code>.</p>
__EXORCISE__

<h2>3. What the deterministic pass knows before any model is asked</h2>
__EVIDENCE__

<h2>4. How well do small local models read the bugs?</h2>
<p>Fifteen development cases (five from real bugs in symfony/ai) and ten held-out cases, written after the platform facts were frozen.</p>
__RESULTS__
</main>
</body>
</html>
"""


def main() -> None:
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "results").glob("*.json"))]
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_examples.py"), "haunted"], cwd=work, check=True, capture_output=True)
        (work / "observed.txt").write_text("KeyError: 'timeout'. settings.yml shows the line timeout: 30 in the editor.", encoding="utf-8")

        def cli(*args: str) -> str:
            done = subprocess.run(
                [sys.executable, "-m", "poltergeist", *args], cwd=work, env=env, capture_output=True, text=True, encoding="utf-8"
            )
            return done.stdout.replace("\\", "/")

        scan = cli("scan", "haunted")
        exorcise = cli("exorcise", "haunted/settings.yml", "haunted/access.js", "haunted/users.csv", "--eol", "lf")
        evidence = cli("seance", "--code", "haunted/settings.yml", "--observed", "observed.txt", "--language", "python", "--evidence-only")

    page = (
        PAGE.replace("__DATE__", datetime.date.today().isoformat())
        .replace("__SCAN__", pre(scan))
        .replace("__EXORCISE__", pre(exorcise))
        .replace("__EVIDENCE__", pre(evidence))
        .replace("__RESULTS__", results_section(results))
    )
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(page):,} bytes, {len(results)} result file(s))")


if __name__ == "__main__":
    main()

"""Run the ghost cases against a local model and score the answers."""

from __future__ import annotations

import datetime
import json
import re
import statistics
from collections.abc import Callable
from pathlib import Path

from .ghosts import reveal
from .llm import Client
from .lore import CATEGORIES, lookup
from .seance import MODES, Diagnosis, diagnose

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"
REQUIRED = ("id", "source", "language", "code", "observed", "category", "fix_any")


def load_cases(directory: Path = CASES_DIR) -> list[dict]:
    cases = []
    for path in sorted(directory.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        missing = [key for key in REQUIRED if key not in case]
        if missing:
            raise ValueError(f"{path.name}: missing {', '.join(missing)}")
        if case["category"] not in CATEGORIES:
            raise ValueError(f"{path.name}: unknown category {case['category']!r}")
        if case["id"] != path.stem:
            raise ValueError(f"{path.name}: id {case['id']!r} must equal the file name")
        cases.append(case)
    return cases


def is_real(case: dict) -> bool:
    return not case["source"].startswith("synthetic")


def is_heldout(case: dict) -> bool:
    """Written after the platform facts and the prompts were frozen, and never used to adjust them."""
    return case["source"] == "synthetic-heldout"


def fix_matches(case: dict, diagnosis: Diagnosis) -> bool:
    """The fix passes when the answer proposes any of the changes the case accepts. A keyword rubric, not a test run."""
    answer = f"{diagnosis.fix}\n{diagnosis.why}"
    return diagnosis.valid and any(re.search(pattern, answer, re.IGNORECASE | re.DOTALL) for pattern in case["fix_any"])


def score(case: dict, diagnosis: Diagnosis) -> dict:
    return {
        "valid": diagnosis.valid,
        "category_ok": diagnosis.valid and diagnosis.category == case["category"],
        "fix_ok": fix_matches(case, diagnosis),
    }


def lore_only(case: dict) -> dict:
    """No model at all: the category of the first platform fact whose pattern matches."""
    hits = lookup(reveal(case["observed"]), reveal(case["code"]))
    guess = hits[0].category if hits else None
    return {"valid": guess is not None, "category_ok": guess == case["category"], "fix_ok": False, "category": guess}


def summarize(rows: list[dict], cases: list[dict]) -> dict:
    by_id = {case["id"]: case for case in cases}

    def share(subset: list[dict], key: str = "category_ok") -> float | None:
        return sum(row[key] for row in subset) / len(subset) if subset else None

    real = [row for row in rows if is_real(by_id[row["id"]])]
    heldout = [row for row in rows if is_heldout(by_id[row["id"]])]
    dev = [row for row in rows if not is_heldout(by_id[row["id"]])]
    seconds = [row["seconds"] for row in rows if "seconds" in row]
    return {
        "n": len(rows),
        "category": share(rows),
        "fix": share(rows, "fix_ok"),
        "valid": share(rows, "valid"),
        "dev_n": len(dev),
        "dev_category": share(dev),
        "real_n": len(real),
        "real_category": share(real),
        "heldout_n": len(heldout),
        "heldout_category": share(heldout),
        "heldout_fix": share(heldout, "fix_ok"),
        "median_seconds": statistics.median(seconds) if seconds else None,
    }


def run(
    client: Client,
    cases: list[dict],
    label: str,
    modes: tuple[str, ...] = MODES,
    progress: Callable[[str], None] = print,
) -> dict:
    result: dict = {
        "label": label,
        "model": client.model_name().replace("\\", "/").rsplit("/", 1)[-1],
        "date": datetime.date.today().isoformat(),
        "modes": {},
        "lore_only": None,
    }
    for mode in modes:
        rows = []
        for case in cases:
            diagnosis, reply = diagnose(client, case["language"], case["code"], case["observed"], mode)
            row = {
                "id": case["id"],
                **score(case, diagnosis),
                "category": diagnosis.category,
                "why": diagnosis.why,
                "fix": diagnosis.fix,
                "seconds": round(reply.seconds, 2),
                "prompt_tokens": reply.prompt_tokens,
                "completion_tokens": reply.completion_tokens,
            }
            rows.append(row)
            progress(
                f"{label} [{mode}] {case['id']}: "
                f"category {'ok' if row['category_ok'] else 'WRONG'} ({row['category'] or 'unparseable'}), "
                f"fix {'ok' if row['fix_ok'] else 'no'}, {row['seconds']}s"
            )
        result["modes"][mode] = {"summary": summarize(rows, cases), "cases": rows}
    rows = [{"id": case["id"], **lore_only(case)} for case in cases]
    result["lore_only"] = {"summary": summarize(rows, cases), "cases": rows}
    return result


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{round(value * 100)}%"


def markdown_table(results: list[dict]) -> str:
    lines = [
        "| Model | Mode | Category, dev cases | of which real bugs | Category, held-out cases | Fix accepted, held-out | Valid JSON | Median seconds |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        for mode, data in result["modes"].items():
            s = data["summary"]
            lines.append(
                f"| {result['label']} | {mode} | {_pct(s['dev_category'])} ({s['dev_n']}) | {_pct(s['real_category'])} ({s['real_n']}) "
                f"| {_pct(s['heldout_category'])} ({s['heldout_n']}) | {_pct(s['heldout_fix'])} | {_pct(s['valid'])} "
                f"| {s['median_seconds']:.1f} |"
            )
    if results:
        s = results[0]["lore_only"]["summary"]
        lines.append(
            f"| no model: platform facts only | lookup | {_pct(s['dev_category'])} ({s['dev_n']}) | {_pct(s['real_category'])} ({s['real_n']}) "
            f"| {_pct(s['heldout_category'])} ({s['heldout_n']}) | - | - | - |"
        )
        chance = _pct(1 / len(CATEGORIES))
        lines.append(f"| chance | - | {chance} | {chance} | {chance} | - | - | - |")
    return "\n".join(lines)

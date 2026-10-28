"""Ask a local model which ghost is haunting a piece of code."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .ghosts import reveal, scan_text
from .llm import Client, Reply
from .lore import CATEGORIES, CATEGORY_HELP, Lore, lookup

MODES = ("plain", "grounded")

SYSTEM = (
    "You are a careful engineer who debugs code that behaves differently on different operating systems, "
    "or after text passes through different tools. You answer only with a JSON object."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "why": {"type": "string"},
        "fix": {"type": "string"},
    },
    "required": ["category", "why", "fix"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Diagnosis:
    category: str
    why: str
    fix: str
    valid: bool
    raw: str


def evidence(code: str, observed: str) -> tuple[list[str], list[Lore]]:
    """What a deterministic pass finds before any model is asked: hidden characters and matching platform facts."""
    lines = []
    for label, text in (("observed output", observed), ("code", code)):
        for finding in scan_text(text).findings:
            if finding.kind in ("crlf", "mixed-eol", "lone-cr"):
                continue
            lines.append(f"{label}, line {finding.line}: {finding.title} {finding.codepoints} {finding.detail}".strip())
    return lines, lookup(reveal(observed), reveal(code))


def build_prompt(language: str, code: str, observed: str, mode: str = "plain") -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    categories = "\n".join(f"- {name}: {CATEGORY_HELP[name]}" for name in CATEGORIES)
    # "plain" sends the text as it was pasted, hidden characters included; "grounded" makes them visible first.
    show = reveal if mode == "grounded" else str
    parts = [
        f"Language: {language}",
        f"Code:\n```\n{show(code)}\n```",
        f"What was observed:\n{show(observed)}",
    ]
    if mode == "grounded":
        found, book = evidence(code, observed)
        if found:
            parts.append("Hidden characters found by a scanner (computed, not guessed):\n" + "\n".join(f"- {x}" for x in found))
        if book:
            parts.append("Platform facts that may apply:\n" + "\n".join(f"- {entry.text}" for entry in book))
    parts.append(
        f"Which kind of hidden difference causes this?\n{categories}\n\n"
        'Reply with JSON: {"category": one of the names above, "why": one or two sentences saying what differs '
        'between the machines or tools and why, "fix": the smallest change, as code or one sentence}.'
    )
    return "\n\n".join(parts)


def parse(text: str) -> Diagnosis:
    candidate = text.strip()
    if not candidate.startswith("{"):
        match = re.search(r"\{.*\}", candidate, re.DOTALL)
        candidate = match.group(0) if match else ""
    try:
        data = json.loads(candidate)
        category = data["category"]
        why = str(data.get("why", ""))
        fix = str(data.get("fix", ""))
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return Diagnosis("", "", "", False, text)
    return Diagnosis(category, why, fix, category in CATEGORIES, text)


def diagnose(client: Client, language: str, code: str, observed: str, mode: str = "plain") -> tuple[Diagnosis, Reply]:
    reply = client.chat(SYSTEM, build_prompt(language, code, observed, mode), schema=SCHEMA, max_tokens=350)
    return parse(reply.text), reply

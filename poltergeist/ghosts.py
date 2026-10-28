"""Find the characters you cannot see.

A ghost here is a character that changes what a program does but not what an editor shows:
a carriage return, a byte order mark, a zero-width space, a bidirectional override, a Unicode
tag character that smuggles text past a human reader.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# kind -> (title, risk, what it does)
KINDS: dict[str, tuple[str, str, str]] = {
    "crlf": (
        "Windows line endings",
        "info",
        "Every line ends in CR LF. Harmless until something splits on LF alone, runs the file on "
        "Linux (a shebang line then names an interpreter ending in CR), or compares it byte for byte.",
    ),
    "mixed-eol": (
        "mixed line endings",
        "warn",
        "Some lines end in CR LF and others in LF, so any code that assumes one style mishandles the other.",
    ),
    "lone-cr": (
        "lone carriage return",
        "warn",
        "A CR that is not followed by LF: it rewinds a terminal and splits lines in some parsers but not in others.",
    ),
    "bom": (
        "byte order mark",
        "warn",
        "U+FEFF at the start of the file. It becomes part of the first key, header or identifier "
        "and makes a JSON parser reject the file.",
    ),
    "zero-width": (
        "zero-width character",
        "warn",
        "Takes no space on screen but is part of the string: two identifiers or keys that look the same compare unequal.",
    ),
    "space-lookalike": (
        "look-alike space",
        "warn",
        "Looks like a space, is not U+0020: shells, YAML and tokenizers treat it as an ordinary letter.",
    ),
    "control": (
        "control character",
        "warn",
        "A non-printing control code; terminals and parsers each react differently.",
    ),
    "bidi": (
        "bidirectional control",
        "high",
        "Reorders how the text is displayed, so the code a reviewer reads is not the code the compiler runs (Trojan Source).",
    ),
    "tag": (
        "Unicode tag character",
        "high",
        "Renders as nothing yet encodes ASCII: text can be hidden inside a file or prompt that a model will read and a human will not.",
    ),
    "variation-selector": (
        "variation selector supplement",
        "high",
        "Invisible code points that can carry hidden data after any visible character.",
    ),
    "mixed-script": (
        "mixed-script word",
        "high",
        "A word that mixes Latin letters with look-alikes from another alphabet: it reads like one name and is another.",
    ),
}

_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0x180E, 0x00AD, 0x200E, 0x200F, 0x061C}
_SPACE_LOOKALIKES = {0x00A0, 0x1680, 0x202F, 0x205F, 0x3000, *range(0x2000, 0x200B)}
_BIDI = {*range(0x202A, 0x202F), *range(0x2066, 0x206A)}
_TAGS = range(0xE0000, 0xE0080)
_VS_SUPPLEMENT = range(0xE0100, 0xE01F0)
_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")
_WORD = re.compile(r"\w+", re.UNICODE)
_TAG_RUN = re.compile("[\U000e0000-\U000e007f]+")


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int
    column: int
    text: str  # the offending characters, verbatim
    detail: str = ""
    path: str = "<text>"

    @property
    def risk(self) -> str:
        return KINDS[self.kind][1]

    @property
    def title(self) -> str:
        return KINDS[self.kind][0]

    @property
    def codepoints(self) -> str:
        return " ".join(f"U+{ord(c):04X}" for c in self.text)


@dataclass
class Report:
    path: str
    findings: list[Finding] = field(default_factory=list)
    skipped: str = ""

    @property
    def clean(self) -> bool:
        return not self.findings


def reveal(text: str) -> str:
    """Make every ghost in `text` visible: a CR becomes ␍, an invisible character becomes ‹U+200B›.

    A run of Unicode tag characters that spells text is shown as that text, flagged as hidden.
    """
    text = _TAG_RUN.sub(lambda m: f"‹hidden text: {decode_tags(m.group())!r}›" if decode_tags(m.group()) else m.group(), text)
    out = []
    for ch in text:
        if ch == "\r":
            out.append("␍")
        elif ch in "\n\t":
            out.append(ch)
        elif _kind_of(ch) is not None and ch != "\ufeff":
            out.append(f"‹U+{ord(ch):04X}›")
        elif ch == "\ufeff":
            out.append("‹BOM›")
        else:
            out.append(ch)
    return "".join(out)


def _kind_of(ch: str) -> str | None:
    cp = ord(ch)
    if cp in _BIDI:
        return "bidi"
    if cp in _TAGS:
        return "tag"
    if cp in _VS_SUPPLEMENT:
        return "variation-selector"
    if cp in _ZERO_WIDTH or cp == 0xFEFF:
        return "zero-width"
    if cp in _SPACE_LOOKALIKES:
        return "space-lookalike"
    if ch not in "\t\n\r" and unicodedata.category(ch) == "Cc":
        return "control"
    return None


def decode_tags(run: str) -> str:
    """The ASCII hidden in a run of Unicode tag characters (U+E0020..U+E007E)."""
    return "".join(chr(ord(c) - 0xE0000) for c in run if 0xE0020 <= ord(c) <= 0xE007E)


def _scripts_of(word: str) -> set[str]:
    found = set()
    for ch in word:
        if ch.isalpha():
            name = unicodedata.name(ch, "")
            for script in _SCRIPTS:
                if name.startswith(script):
                    found.add(script)
    return found


def scan_text(text: str, path: str = "<text>") -> Report:
    report = Report(path)
    add = report.findings.append

    crlf = text.count("\r\n")
    lone_cr = len(re.findall(r"\r(?!\n)", text))
    lf = text.count("\n") - crlf
    if crlf and lf:
        first = _first_minority_line(text, minority_is_crlf=crlf < lf)
        add(Finding("mixed-eol", first, 1, "\r\n", f"{crlf} CR LF line(s) and {lf} LF line(s)", path))
    elif crlf:
        add(Finding("crlf", 1, 1, "\r\n", f"all {crlf} line(s) end in CR LF", path))
    if lone_cr:
        line = text[: re.search(r"\r(?!\n)", text).start()].count("\n") + 1
        add(Finding("lone-cr", line, 1, "\r", f"{lone_cr} carriage return(s) not followed by LF", path))

    for number, line in enumerate(text.split("\n"), start=1):
        _scan_line(line, number, path, add, at_file_start=number == 1)
    return report


def _first_minority_line(text: str, minority_is_crlf: bool) -> int:
    for number, line in enumerate(text.split("\n")[:-1], start=1):
        if line.endswith("\r") == minority_is_crlf:
            return number
    return 1


def _scan_line(line: str, number: int, path: str, add, *, at_file_start: bool) -> None:
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\ufeff" and at_file_start and i == 0:
            add(Finding("bom", number, 1, ch, "at the start of the file", path))
            i += 1
            continue
        kind = _kind_of(ch)
        if kind is None:
            i += 1
            continue
        j = i + 1
        while j < len(line) and _kind_of(line[j]) == kind:
            j += 1
        run = line[i:j]
        detail = ""
        if kind == "tag":
            hidden = decode_tags(run)
            detail = f"hidden text: {hidden!r}" if hidden else "tag characters with no readable payload"
        elif kind == "zero-width" and len(run) > 1:
            detail = f"{len(run)} in a row"
        add(Finding(kind, number, i + 1, run, detail, path))
        i = j
    for match in _WORD.finditer(line):
        scripts = _scripts_of(match.group())
        if len(scripts) > 1:
            odd = "".join(c for c in match.group() if c.isalpha() and not unicodedata.name(c, "").startswith("LATIN"))
            add(
                Finding(
                    "mixed-script",
                    number,
                    match.start() + 1,
                    odd,
                    f"in the word {match.group()!r}: {' + '.join(sorted(scripts))}",
                    path,
                )
            )

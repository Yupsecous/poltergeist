"""A small, hand-written book of platform facts, looked up by pattern before the model is asked.

Retrieval is deterministic: no embeddings, no model. The entries state generic facts about operating
systems and text, never the answer to a particular case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES = (
    "line-endings",
    "invisible-characters",
    "path-and-filesystem",
    "executable-naming",
    "encoding-and-locale",
)

CATEGORY_HELP = {
    "line-endings": "CR LF versus LF, platform line-ending constants, a script saved with Windows line endings",
    "invisible-characters": "byte order marks, zero-width or non-breaking spaces, bidirectional controls, hidden Unicode",
    "path-and-filesystem": "path separators, letter case of file names, file-system rules that differ per OS",
    "executable-naming": "program names and extensions (.exe, .cmd), how a command is found and launched",
    "encoding-and-locale": "default text encodings, locale-dependent number and date formats",
}


@dataclass(frozen=True)
class Lore:
    id: str
    category: str
    pattern: re.Pattern[str]
    text: str


def _entry(id: str, category: str, pattern: str, text: str) -> Lore:
    return Lore(id, category, re.compile(pattern, re.IGNORECASE), text)


LORE: tuple[Lore, ...] = (
    _entry(
        "line-ending-constants",
        "line-endings",
        r"PHP_EOL|os\.linesep|Environment\.NewLine|lineSeparator|line\.separator|\\r|\^M|CRLF|bad interpreter|␍",
        "PHP_EOL, os.linesep and Environment.NewLine are CR LF on Windows and LF elsewhere. They suit text written "
        "for the local console or file. They are wrong for splitting or joining data that another program produced "
        "or will read (CLI output, network text, prompts, test expectations): that data has its own fixed line ending. "
        "A shell script saved with CR LF fails on Linux because the interpreter name ends in a carriage return.",
    ),
    _entry(
        "invisible-text",
        "invisible-characters",
        r"\\u200[b-d]|\\ufeff|\\xa0|\\u00a0|‹U\+|‹BOM›|zero-width|invisible|\\u202[a-e]|\\u206[6-9]|ï»¿|non-breaking",
        "Some characters take no space on screen yet belong to the string. A byte order mark (U+FEFF) glues itself to "
        "the first CSV header or JSON key. A zero-width space (U+200B) makes two keys that look identical unequal. "
        "A non-breaking space (U+00A0) is not a separator for shells or YAML. Bidirectional controls (U+202E) reorder "
        "how code is displayed. When the repr of a value differs from what the editor shows, suspect one of these.",
    ),
    _entry(
        "path-separator",
        "path-and-filesystem",
        r"\\\\[A-Za-z_]|[\"'][\\\\/][\"']\s*\+|\+\s*[\"'][\\\\/][\"']|os\.sep|\b[A-Za-z]:\\",
        "Windows separates path parts with a backslash and also accepts a slash. On Linux and macOS a backslash is an "
        "ordinary character in a file name, so 'data\\input.csv' names a single file with a backslash in it. Build "
        "paths with the language's path API (os.path.join, pathlib, Path.Combine), never by concatenating separators.",
    ),
    _entry(
        "case-sensitivity",
        "path-and-filesystem",
        r"Cannot find module|ModuleNotFoundError|case-insensitive|case.sensitiv",
        "The default file systems of Windows and macOS ignore letter case and Linux does not. An import or path whose "
        "case differs from the real file name works on the first two and fails on Linux, usually first in CI.",
    ),
    _entry(
        "executable-suffix",
        "executable-naming",
        r"\.exe\b|\.cmd\b|\.bat\b|PATHEXT|subprocess\.(?:run|Popen|call|check_output)|shutil\.which|basename\(",
        "On Windows programs carry an extension (php.exe, npm.cmd, tool.bat). The name is completed through PATHEXT "
        "only when a shell runs the command, so code that matches a program name against 'php', or launches 'npm' "
        "without a shell, works on Linux and fails on Windows. Resolve the program (shutil.which) or accept the "
        "optional suffix, case-insensitively.",
    ),
    _entry(
        "default-encoding",
        "encoding-and-locale",
        r"UnicodeDecodeError|UnicodeEncodeError|charmap|cp125\d|codec can't (?:de|en)code",
        "open() without encoding= uses the platform's locale encoding: cp1252 on many Windows setups, UTF-8 on Linux "
        "and macOS. A UTF-8 file with non-ASCII text then decodes on one and raises or garbles on the other. Pass "
        "encoding='utf-8' explicitly.",
    ),
    _entry(
        "locale-numbers",
        "encoding-and-locale",
        r"locale\.|setlocale|atof|LC_ALL|LC_NUMERIC|decimal.?(?:comma|mark|separator)|de_DE",
        "Parsing or formatting numbers and dates through the process locale reads '1,234.5' differently under de_DE, "
        "where the comma is the decimal mark. Use a fixed format for data, and the locale only for display to a person.",
    ),
)


def lookup(*texts: str, limit: int = 3) -> list[Lore]:
    """The entries whose pattern appears in any of `texts`, in book order."""
    haystack = "\n".join(texts)
    return [entry for entry in LORE if entry.pattern.search(haystack)][:limit]

"""Remove the ghosts, conservatively, and show exactly what changed."""

from __future__ import annotations

import difflib
import os
import re
from collections.abc import Iterator
from pathlib import Path

from .ghosts import Report, reveal, scan_text

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "vendor", "__pycache__", ".venv", "venv", ".mypy_cache"}
MAX_BYTES = 2_000_000

# Never legitimate inside source code, safe to drop by default.
_ALWAYS = "\ufeff\u200b\u2060\u180e" + "".join(map(chr, [*range(0x202A, 0x202F), *range(0x2066, 0x206A)]))
_ALWAYS_RE = re.compile(f"[{_ALWAYS}]|[\U000e0000-\U000e007f]|[\U000e0100-\U000e01ef]")
# Legitimate in prose (emoji sequences, Persian and Indic shaping, right-to-left text, typography).
_PROSE = "\u200c\u200d\u200e\u200f\u061c\u00ad"
_SPACES_RE = re.compile("[\u00a0\u1680\u202f\u205f\u3000\u2000-\u200a]")


def exorcise_text(text: str, *, eol: str = "keep", everything: bool = False) -> str:
    """Return `text` without its ghosts.

    By default only characters that never belong in source code are removed. `everything=True` also
    drops joiners, direction marks and soft hyphens and turns look-alike spaces into U+0020.
    `eol="lf"` rewrites CR LF and lone CR as LF. Mixed-script words are reported, never rewritten.
    """
    out = _ALWAYS_RE.sub("", text)
    if everything:
        out = re.sub(f"[{_PROSE}]", "", out)
        out = _SPACES_RE.sub(" ", out)
    if eol == "lf":
        out = out.replace("\r\n", "\n").replace("\r", "\n")
    elif eol != "keep":
        raise ValueError(f"unknown eol policy {eol!r}")
    return out


def iter_files(paths: list[str]) -> Iterator[Path]:
    for raw in paths:
        root = Path(raw)
        if root.is_file():
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                yield Path(dirpath) / name


def read_text(path: Path) -> tuple[str | None, str]:
    """The decoded text of `path`, or (None, reason) when it should not be scanned."""
    if path.is_symlink():
        return None, "symlink"
    try:
        if path.stat().st_size > MAX_BYTES:
            return None, "larger than 2 MB"
        data = path.read_bytes()
    except OSError as error:
        return None, f"unreadable: {error.strerror or error}"
    if b"\0" in data[:8192]:
        return None, "binary"
    try:
        return data.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "not valid UTF-8"


def scan_path(path: Path) -> Report:
    text, reason = read_text(path)
    if text is None:
        return Report(str(path), skipped=reason)
    return scan_text(text, str(path))


def plan(path: Path, *, eol: str = "keep", everything: bool = False) -> tuple[str, str, str] | None:
    """(old, new, unified diff of the revealed text) for a file that would change, else None."""
    old, _ = read_text(path)
    if old is None:
        return None
    new = exorcise_text(old, eol=eol, everything=everything)
    if new == old:
        return None
    diff = "".join(
        difflib.unified_diff(
            reveal(old).splitlines(keepends=True),
            reveal(new).splitlines(keepends=True),
            fromfile=f"a/{path.as_posix()}",
            tofile=f"b/{path.as_posix()}",
        )
    )
    return old, new, diff


def write(path: Path, new: str) -> None:
    """Replace `path` with `new` as UTF-8 exactly as given: no newline translation, no half-written file."""
    temporary = path.with_name(f".{path.name}.exorcism")
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        handle.write(new)
    os.replace(temporary, path)

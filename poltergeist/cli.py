"""poltergeist: find the characters you cannot see, and ask a local model about the bugs they cause."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench, exorcise
from .llm import Client, NotLocalError, ServerError
from .seance import MODES, diagnose, evidence

RISK_ORDER = {"info": 0, "warn": 1, "high": 2}


def _scan(args: argparse.Namespace) -> int:
    reports = [exorcise.scan_path(path) for path in exorcise.iter_files(args.paths)]
    scanned = [r for r in reports if not r.skipped]
    haunted = [r for r in scanned if r.findings]
    if args.json:
        payload = [
            {
                "path": r.path,
                "findings": [
                    {
                        "kind": f.kind,
                        "risk": f.risk,
                        "line": f.line,
                        "column": f.column,
                        "codepoints": f.codepoints,
                        "detail": f.detail,
                    }
                    for f in r.findings
                ],
            }
            for r in haunted
        ]
        print(json.dumps(payload, indent=2))
    else:
        for report in haunted:
            print(report.path)
            for f in report.findings:
                if f.kind == "mixed-script":
                    shown = ""
                elif len(f.text) <= 4:
                    shown = f"{f.codepoints} "
                else:
                    shown = f"{len(f.text)} characters, "
                print(f"  {f.line}:{f.column}  {f.risk:<4}  {f.title}  {shown}{f.detail}".rstrip())
        total = sum(len(r.findings) for r in haunted)
        if total:
            print(f"\n{total} finding(s) in {len(haunted)} of {len(scanned)} file(s).")
        else:
            print(f"No ghosts in {len(scanned)} file(s). The house is quiet.")
    threshold = RISK_ORDER[args.fail_on]
    worst = max((RISK_ORDER[f.risk] for r in haunted for f in r.findings), default=-1)
    return 1 if worst >= threshold else 0


def _exorcise(args: argparse.Namespace) -> int:
    changed = 0
    for path in exorcise.iter_files(args.paths):
        result = exorcise.plan(path, eol=args.eol, everything=args.all)
        if result is None:
            continue
        _, new, diff = result
        changed += 1
        if args.write:
            exorcise.write(path, new)
            print(f"exorcised {path}")
        else:
            print(diff, end="" if diff.endswith("\n") else "\n")
    if changed and not args.write:
        print(f"\n{changed} file(s) would change. Nothing was written; run again with --write to apply.")
    elif not changed:
        print("Nothing to exorcise.")
    return 0


def _client(args: argparse.Namespace) -> Client:
    return Client(args.url)


def _seance(args: argparse.Namespace) -> int:
    code = Path(args.code).read_text(encoding="utf-8", newline="")
    observed = sys.stdin.read() if args.observed == "-" else Path(args.observed).read_text(encoding="utf-8", newline="")
    found, book = evidence(code, observed)
    print("What a deterministic pass sees (no model involved):")
    for line in found or ["no hidden characters"]:
        print(f"  - {line}")
    for entry in book:
        print(f"  - platform fact [{entry.id}]: {entry.text}")
    if args.evidence_only:
        return 0
    client = _client(args)
    diagnosis, reply = diagnose(client, args.language, code, observed, args.mode)
    print(f"\nThe model's reading ({client.model_name()}, {args.mode} prompt, {reply.seconds:.0f}s):")
    if not diagnosis.valid:
        print("  the model did not return a usable answer:")
        print(f"  {diagnosis.raw[:300]}")
        return 1
    print(f"  category: {diagnosis.category}\n  why:      {diagnosis.why}\n  fix:      {diagnosis.fix}")
    return 0


def _bench(args: argparse.Namespace) -> int:
    cases = bench.load_cases()[: args.limit]
    modes = tuple(m for m in args.modes.split(",") if m)
    unknown = [m for m in modes if m not in MODES]
    if unknown:
        print(f"unknown mode(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    result = bench.run(_client(args), cases, args.label, modes, progress=lambda line: print(line, flush=True))
    out = Path(args.out or f"results/{args.label}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    # ASCII-only on purpose: a model's answer may contain hidden characters, and results are committed.
    out.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {out}\n")
    print(bench.markdown_table([result]))
    return 0


def _report(args: argparse.Namespace) -> int:
    results = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.files]
    print(bench.markdown_table(results))
    return 0


def _cases(_: argparse.Namespace) -> int:
    cases = bench.load_cases()
    rows = [{"id": c["id"], **bench.lore_only(c)} for c in cases]
    print(f"{len(cases)} cases ({sum(bench.is_real(c) for c in cases)} from real bugs)\n")
    for case, row in zip(cases, rows):
        mark = "ok " if row["category_ok"] else "-- "
        print(f"{mark}{case['id']:<24} {case['category']:<22} lore-only guess: {row['category'] or 'none'}")
    summary = bench.summarize(rows, cases)
    print(f"\nPlatform facts alone, with no model: {summary['category'] * 100:.0f}% of categories right.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poltergeist", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list the invisible and look-alike characters in files")
    scan.add_argument("paths", nargs="+")
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--fail-on", choices=list(RISK_ORDER), default="warn", help="exit 1 at or above this risk (default: warn)")
    scan.set_defaults(run=_scan)

    ex = sub.add_parser("exorcise", help="remove ghosts (a dry run unless --write is given)")
    ex.add_argument("paths", nargs="+")
    ex.add_argument("--write", action="store_true")
    ex.add_argument("--eol", choices=["keep", "lf"], default="keep")
    ex.add_argument("--all", action="store_true", help="also drop joiners, direction marks, soft hyphens; look-alike spaces become spaces")
    ex.set_defaults(run=_exorcise)

    se = sub.add_parser("seance", help="ask a local model which ghost causes a bug")
    se.add_argument("--code", required=True, help="file with the code")
    se.add_argument("--observed", required=True, help="file with what was observed, or - for stdin")
    se.add_argument("--language", default="unknown")
    se.add_argument("--mode", choices=list(MODES), default="grounded")
    se.add_argument("--url", default="http://127.0.0.1:8081")
    se.add_argument("--evidence-only", action="store_true", help="show the deterministic findings and stop; no model needed")
    se.set_defaults(run=_seance)

    be = sub.add_parser("bench", help="run the ghost cases against a local model")
    be.add_argument("--url", default="http://127.0.0.1:8081")
    be.add_argument("--label", required=True, help="name for this model in the results table")
    be.add_argument("--modes", default=",".join(MODES))
    be.add_argument("--limit", type=int, default=None)
    be.add_argument("--out")
    be.set_defaults(run=_bench)

    rp = sub.add_parser("report", help="print the results table for saved runs")
    rp.add_argument("files", nargs="+")
    rp.set_defaults(run=_report)

    ca = sub.add_parser("cases", help="list the cases and what the platform facts alone score (no model)")
    ca.set_defaults(run=_cases)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except (NotLocalError, ServerError) as error:
        print(f"poltergeist: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(f"poltergeist: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

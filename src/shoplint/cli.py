"""shoplint command line."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import yaml

from . import __version__, report
from .export import acp_rows
from .probe import load_questions, probe, summary
from .rules import audit, builtin_packs, load_pack
from .shopify import read_csv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shoplint")
    ap.add_argument("--version", action="version", version=f"shoplint {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="check a Shopify product CSV")
    a.add_argument("csv", type=Path)
    a.add_argument(
        "--pack",
        action="append",
        help=f"built-in pack name or path to a YAML pack (default: {', '.join(builtin_packs())})",
    )
    a.add_argument("--questions", type=Path, help="your own buyer-question YAML for the probe")
    a.add_argument("--html", type=Path, help="also write an HTML report")
    a.add_argument(
        "--findings-csv", type=Path, help="also write findings as CSV, one row per problem"
    )
    a.add_argument("--json", type=Path, help="also write findings and probe results as JSON")
    a.add_argument("--title", default="Catalog readiness")
    a.add_argument("--fail-on", choices=["error", "warning", "never"], default="error")

    e = sub.add_parser("export", help="write an ACP product feed (JSON Lines)")
    e.add_argument("csv", type=Path)
    e.add_argument("--store-url", required=True)
    e.add_argument("--seller", required=True)
    e.add_argument("--currency", default="INR")
    e.add_argument("-o", "--out", type=Path, required=True)

    sub.add_parser("packs", help="list built-in rule packs")

    args = ap.parse_args(argv)

    if args.cmd == "packs":
        for name in builtin_packs():
            p = load_pack(name)
            print(f"{name:<9} {len(p.rules):>2} rules  read {p.checked}  {p.title}")
        return 0

    try:
        products = read_csv(args.csv)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    if args.cmd == "export":
        rows, skipped = acp_rows(products, args.store_url, args.seller, args.currency)
        with args.out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(rows)} rows to {args.out}")
        for s in skipped:
            print(f"  skipped {s}", file=sys.stderr)
        return 0

    if not products:
        print("warning: the file has a header but no products", file=sys.stderr)
    try:
        packs = [load_pack(n) for n in (args.pack or builtin_packs())]
    except (OSError, ValueError, KeyError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    try:
        questions = load_questions(args.questions)
    except (OSError, ValueError, yaml.YAMLError, re.error) as err:
        print(f"error: --questions: {err}", file=sys.stderr)
        return 2
    findings = audit(products, packs)
    answers = summary(probe(products, questions))
    print(report.text(findings, packs, answers, len(products)))
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(
            report.html_page(args.title, findings, packs, answers, len(products)),
            encoding="utf-8",
        )
    if args.findings_csv:
        if args.findings_csv.resolve() == args.csv.resolve():
            print("error: --findings-csv would overwrite the input file", file=sys.stderr)
            return 2
        with args.findings_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["level", "rule", "product", "detail", "why"])
            for fd in findings:
                w.writerow([fd.level, fd.rule, fd.target, fd.detail, fd.message])
    if args.json:
        args.json.write_text(
            json.dumps({"findings": [f.__dict__ for f in findings], "probe": answers}, indent=2),
            encoding="utf-8",
        )
    levels = {f.level for f in findings}
    if args.fail_on == "error" and "error" in levels:
        return 1
    if args.fail_on == "warning" and levels & {"error", "warning"}:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

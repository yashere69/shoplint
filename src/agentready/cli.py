"""agentready command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, report
from .export import acp_rows
from .probe import probe, summary
from .rules import audit, builtin_packs, load_pack
from .shopify import read_csv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentready")
    ap.add_argument("--version", action="version", version=f"agentready {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="check a Shopify product CSV")
    a.add_argument("csv", type=Path)
    a.add_argument(
        "--pack",
        action="append",
        help=f"built-in pack name or path to a YAML pack (default: {', '.join(builtin_packs())})",
    )
    a.add_argument("--html", type=Path, help="also write an HTML report")
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

    packs = [load_pack(n) for n in (args.pack or builtin_packs())]
    findings = audit(products, packs)
    answers = summary(probe(products))
    print(report.text(findings, packs, answers, len(products)))
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(
            report.html_page(args.title, findings, packs, answers, len(products)),
            encoding="utf-8",
        )
    if args.json:
        args.json.write_text(
            json.dumps(
                {"findings": [f.__dict__ for f in findings], "probe": answers}, indent=2
            ),
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

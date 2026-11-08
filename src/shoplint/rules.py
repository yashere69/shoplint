"""Rule packs: dated YAML files that bind check functions to a spec.

Specs for agent commerce move monthly, so every pack records which document it was written
against and when that document was read. The report prints both, so an old result can't
be mistaken for a current one.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml

from .checks import REGISTRY, Context
from .shopify import Product

LEVELS = ("error", "warning", "info")


@dataclass
class Rule:
    id: str
    level: str
    check: str
    params: dict
    message: str


@dataclass
class Pack:
    name: str
    title: str
    source: str
    checked: str
    rules: list[Rule]


@dataclass
class Finding:
    pack: str
    rule: str
    level: str
    target: str
    message: str
    detail: str


def load_pack(path_or_name: str) -> Pack:
    p = Path(path_or_name)
    if p.suffix in {".yaml", ".yml"} and p.exists():
        text = p.read_text(encoding="utf-8")
    elif path_or_name in builtin_packs():
        text = (
            resources.files("shoplint.packs")
            .joinpath(f"{path_or_name}.yaml")
            .read_text(encoding="utf-8")
        )
    else:
        raise ValueError(
            f"no rule pack {path_or_name!r}: use one of {', '.join(builtin_packs())} "
            "or a path to a .yaml file"
        )
    data = yaml.safe_load(text)
    rules = []
    for r in data["rules"]:
        if r["check"] not in REGISTRY:
            raise ValueError(f"{data['pack']}: rule {r['id']} uses unknown check {r['check']!r}")
        if r.get("level", "warning") not in LEVELS:
            raise ValueError(f"{data['pack']}: rule {r['id']} has bad level {r.get('level')!r}")
        rules.append(
            Rule(
                id=r["id"],
                level=r.get("level", "warning"),
                check=r["check"],
                params=r.get("params", {}),
                message=r["message"],
            )
        )
    return Pack(data["pack"], data["title"], data["source"], str(data["checked"]), rules)


def builtin_packs() -> list[str]:
    return sorted(
        f.name.removesuffix(".yaml")
        for f in resources.files("shoplint.packs").iterdir()
        if f.name.endswith(".yaml")
    )


def audit(products: list[Product], packs: list[Pack]) -> list[Finding]:
    ctx = Context(products)
    findings = []
    for pack in packs:
        for rule in pack.rules:
            fn = REGISTRY[rule.check]
            for p in products:
                if p.status == "draft" and rule.check != "active_but_empty":
                    continue  # drafts aren't syndicated; don't drown the report in them
                for target, detail in fn(p, rule.params, ctx):
                    findings.append(
                        Finding(pack.name, rule.id, rule.level, target, rule.message, detail)
                    )
    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    findings.sort(key=lambda f: (order[f.level], f.rule, f.target))
    return findings

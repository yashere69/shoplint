"""Question probe: can a buyer's question be answered from structured product data?

For each product we ask the questions shoppers actually send ("what fabric?", "is XL in
stock?", "is the dupatta included?") and classify where the answer lives:

  structured   an option, metafield, tag or inventory field holds it
  prose-only   only the description mentions it, so a feed or filter can't use it and an
               agent has to read marketing copy to guess
  missing      nowhere

Questions come from YAML (`questions/apparel-india.yaml` by default), so another category
can bring its own. The probe is deliberately not an LLM. It answers "is the fact present as
data", which is what feed specs reward, and it is deterministic, so before/after numbers
are comparable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from .shopify import Product


@dataclass
class Question:
    id: str
    ask: str
    prose: str
    options: list[str] = field(default_factory=list)
    metafields: list[str] = field(default_factory=list)
    tags: str | None = None
    inventory: bool = False
    applies_text: str | None = None
    applies_tags: str | None = None
    applies_fields: list[str] = field(default_factory=lambda: ["title", "type", "description"])

    def applies(self, p: Product) -> bool:
        if not (self.applies_text or self.applies_tags):
            return True
        text = " ".join(str(getattr(p, f, "")) for f in self.applies_fields)
        if self.applies_text and re.search(self.applies_text, text, re.I):
            return True
        return bool(self.applies_tags and _tags(p, self.applies_tags))

    def structured(self, p: Product) -> bool:
        if self.options and p.has_option(*self.options):
            return True
        if self.metafields and p.metafield(*self.metafields):
            return True
        if self.tags and _tags(p, self.tags):
            return True
        return self.inventory and any(v.tracker or v.qty for v in p.variants)


def _tags(p: Product, pattern: str) -> bool:
    return any(re.search(pattern, t, re.I) for t in p.tags)


def load_questions(path: str | Path | None = None) -> list[Question]:
    """The built-in Indian ethnic-wear set, or your own YAML in the same shape."""
    if path is None:
        text = (
            resources.files("agentready.questions")
            .joinpath("apparel-india.yaml")
            .read_text(encoding="utf-8")
        )
    else:
        text = Path(path).read_text(encoding="utf-8")
    out = []
    for i, q in enumerate(yaml.safe_load(text) or [], start=1):
        if not isinstance(q, dict) or not {"id", "ask", "prose"} <= set(q):
            raise ValueError(f"question {i}: needs id, ask and prose")
        st = q.get("structured") or {}
        ap = q.get("applies_if") or {}
        for rx in [q["prose"], st.get("tags"), ap.get("text"), ap.get("tags")]:
            if rx:
                re.compile(rx)
        out.append(
            Question(
                id=q["id"],
                ask=q["ask"],
                prose=q["prose"],
                options=st.get("options", []),
                metafields=st.get("metafields", []),
                tags=st.get("tags"),
                inventory=bool(st.get("inventory")),
                applies_text=ap.get("text"),
                applies_tags=ap.get("tags"),
                applies_fields=ap.get("fields", ["title", "type", "description"]),
            )
        )
    return out


@dataclass
class Answer:
    product: str
    question: str
    where: str  # structured | prose-only | missing


def probe(products: list[Product], questions: list[Question] | None = None) -> list[Answer]:
    questions = questions if questions is not None else load_questions()
    out = []
    for p in products:
        if p.status == "draft":
            continue
        text = p.description
        for q in questions:
            if not q.applies(p):
                continue
            if q.structured(p):
                where = "structured"
            elif re.search(q.prose, text, re.I):
                where = "prose-only"
            else:
                where = "missing"
            out.append(Answer(p.handle, q.id, where))
    return out


def summary(answers: list[Answer]) -> dict:
    total = len(answers)
    count = {w: sum(a.where == w for a in answers) for w in ("structured", "prose-only", "missing")}
    per_q: dict[str, dict[str, int]] = {}
    for a in answers:
        per_q.setdefault(a.question, {"structured": 0, "prose-only": 0, "missing": 0})
        per_q[a.question][a.where] += 1
    return {
        "questions": total,
        "answerable": count["structured"],
        "answerable_pct": round(100 * count["structured"] / total, 1) if total else 0.0,
        **count,
        "by_question": per_q,
    }

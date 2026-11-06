"""Question probe: can a buyer's question be answered from structured product data?

For each product we ask the questions shoppers actually send ("what fabric?", "is XL in
stock?", "is the dupatta included?") and classify where the answer lives:

  structured   an option, metafield, tag or inventory field holds it
  prose-only   only the description mentions it, so a feed or filter can't use it and an
               agent has to read marketing copy to guess
  missing      nowhere

The probe is deliberately not an LLM. It answers "is the fact present as data", which is
what feed specs reward, and it is deterministic, so before/after numbers are comparable.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .shopify import Product

FABRICS = (
    r"cotton|linen|silk|chanderi|georgette|chiffon|rayon|viscose|modal|mul|khadi|crepe|"
    r"organza|muslin|tussar|kota"
)
COLOURS = (
    r"indigo|blue|red|maroon|green|yellow|mustard|pink|rust|white|ivory|black|beige|grey|"
    r"orange|peach|teal|navy|purple|lavender"
)
TECHNIQUES = r"hand[- ]?block|ajrakh|bagru|dabu|kalamkari|shibori|bandhani|ikat|chikankari"


@dataclass
class Question:
    id: str
    ask: str
    applies: Callable[[Product], bool]
    structured: Callable[[Product], bool]
    prose: str  # regex searched in the description when nothing structured exists


def _tags(p: Product, pattern: str) -> bool:
    return any(re.search(pattern, t, re.I) for t in p.tags)


def _is_set(p: Product) -> bool:
    return bool(re.search(r"\bset\b", f"{p.title} {p.type}", re.I))


QUESTIONS = [
    Question(
        "fabric",
        "What fabric is it?",
        lambda p: True,
        lambda p: (
            bool(p.metafield("fabric", "material") or p.has_option("fabric", "material"))
            or _tags(p, rf"^({FABRICS})$")
        ),
        rf"\b({FABRICS})\b",
    ),
    Question(
        "sizes",
        "Which sizes does it come in?",
        lambda p: True,
        lambda p: bool(p.has_option("size")),
        r"\b(XS|S|M|L|XL|XXL|free size|sizes?)\b",
    ),
    Question(
        "colour",
        "What colour is it?",
        lambda p: True,
        lambda p: bool(
            p.has_option("color", "colour") or p.metafield("color", "colour", "color-pattern")
        ),
        rf"\b({COLOURS})\b",
    ),
    Question(
        "in-stock",
        "Is it in stock?",
        lambda p: True,
        lambda p: any(v.tracker or v.qty for v in p.variants),
        r"\b(in stock|available|ready to ship)\b",
    ),
    Question(
        "care",
        "How do I wash it?",
        lambda p: True,
        lambda p: bool(p.metafield("care", "care_instructions", "wash_care")),
        r"\b(hand wash|machine wash|dry clean|wash)\b",
    ),
    Question(
        "length",
        "How long is the kurta?",
        lambda p: True,
        lambda p: bool(p.metafield("length", "kurta_length")),
        r"\b\d{2}(\.\d)?\s*(inches|inch|in|cm)\b",
    ),
    Question(
        "technique",
        "Is it hand block printed?",
        lambda p: (
            bool(re.search(r"print", f"{p.title} {p.description} {p.type}", re.I))
            or _tags(p, TECHNIQUES)
        ),
        lambda p: bool(p.metafield("technique", "print", "craft")) or _tags(p, TECHNIQUES),
        rf"\b({TECHNIQUES})\b",
    ),
    Question(
        "set-contents",
        "What's included in the set?",
        _is_set,
        lambda p: bool(p.metafield("set_includes", "includes", "set_contents")),
        r"\b(dupatta|pants?|palazzo|bottoms?|includes?)\b",
    ),
]


@dataclass
class Answer:
    product: str
    question: str
    where: str  # structured | prose-only | missing


def probe(products: list[Product]) -> list[Answer]:
    out = []
    for p in products:
        if p.status == "draft":
            continue
        text = p.description
        for q in QUESTIONS:
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

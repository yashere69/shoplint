"""Check functions referenced by name from rule packs.

Each check receives a product and the rule's params and yields (target, detail) pairs for
every problem it finds. `target` is the product handle, or "handle/SKU-or-row" for
variant-level problems. Keeping checks as plain functions means a new rule pack is mostly
YAML; Python is only needed for a genuinely new kind of check.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from decimal import Decimal, InvalidOperation

from .shopify import Product, Variant

Finding = tuple[str, str]
CheckFn = Callable[[Product, dict, "Context"], Iterator[Finding]]

REGISTRY: dict[str, CheckFn] = {}


class Context:
    """Catalog-wide facts some checks need (duplicate SKUs, size systems in use)."""

    def __init__(self, products: list[Product]):
        self.products = products
        self.sku_counts: dict[str, int] = {}
        for p in products:
            for v in p.variants:
                if v.sku:
                    self.sku_counts[v.sku] = self.sku_counts.get(v.sku, 0) + 1


def check(name: str) -> Callable[[CheckFn], CheckFn]:
    def register(fn: CheckFn) -> CheckFn:
        REGISTRY[name] = fn
        return fn

    return register


def _vt(p: Product, v: Variant) -> str:
    return f"{p.handle}/{v.sku or f'row{v.row}'}"


def _product_field(p: Product, name: str) -> str:
    if name == "description":
        return p.description
    if name == "image":
        return p.images[0].src if p.images else ""
    return str(getattr(p, name, "") or "")


# --- product-level -------------------------------------------------------------------------


@check("required")
def required(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    if not _product_field(p, params["field"]).strip():
        yield p.handle, f"{params['field']} is empty"


@check("max_length")
def max_length(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    value = _product_field(p, params["field"])
    if len(value) > params["max"]:
        yield p.handle, f"{params['field']} is {len(value)} characters (limit {params['max']})"


@check("min_words")
def min_words(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    n = len(_product_field(p, params["field"]).split())
    if 0 < n < params["min"]:
        yield p.handle, f"{params['field']} has {n} words; agents get little to work with"


@check("image_alt_text")
def image_alt_text(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    missing = [img.position or i + 1 for i, img in enumerate(p.images) if not img.alt]
    if missing:
        yield p.handle, f"images without alt text at positions {missing}"


@check("product_attribute")
def product_attribute(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    """An attribute present as an option or a metafield (apparel: size, color, material...)."""
    names = params["names"]
    if not (p.has_option(*names) or p.metafield(*names)):
        yield p.handle, f"no structured {params['label']} (option or metafield)"


@check("option_case_consistent")
def option_case_consistent(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    for name in p.option_names:
        values = p.option_values(name)
        by_lower: dict[str, set[str]] = {}
        for v in values:
            by_lower.setdefault(v.lower(), set()).add(v)
        clashes = [sorted(s) for s in by_lower.values() if len(s) > 1]
        if clashes:
            yield p.handle, f"{name} values differ only in case: {clashes}"


SIZE_SYSTEMS = {
    "letter": re.compile(r"^(xxs|xs|s|m|l|xl|xxl|2xl|xxxl|3xl|4xl|5xl)$", re.I),
    "word": re.compile(r"^(extra small|small|medium|large|extra large)$", re.I),
    "bust-inch": re.compile(r"^(2[8-9]|[3-5]\d)$"),
    "free": re.compile(r"^(free size|free|one size|os)$", re.I),
}


def size_system(value: str) -> str:
    for name, rx in SIZE_SYSTEMS.items():
        if rx.match(value.strip()):
            return name
    return "other"


@check("size_system_consistent")
def size_system_consistent(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    """Within a product, sizes should use one system ("S/M/L" or "36/38/40"), not a mix."""
    name = p.has_option("size")
    if not name:
        return
    systems = {size_system(v) for v in p.option_values(name)}
    if len(systems) > 1:
        yield p.handle, f"sizes mix systems {sorted(systems)}: {p.option_values(name)}"


@check("catalog_size_system")
def catalog_size_system(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    """Flag a product whose size system differs from the one most of the catalog uses."""
    counts: dict[str, int] = {}
    for q in ctx.products:
        n = q.has_option("size")
        for v in q.option_values(n) if n else []:
            s = size_system(v)
            if s != "free":
                counts[s] = counts.get(s, 0) + 1
    if not counts:
        return
    dominant = max(counts, key=lambda k: counts[k])
    name = p.has_option("size")
    own = {size_system(v) for v in p.option_values(name)} - {"free"} if name else set()
    if own and dominant not in own:
        yield p.handle, f"uses {sorted(own)} sizes while most of the catalog uses {dominant}"


# --- variant-level -------------------------------------------------------------------------


@check("variant_sku")
def variant_sku(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    for v in p.variants:
        if not v.sku:
            yield _vt(p, v), "variant has no SKU, so there is no stable item id"
        elif ctx.sku_counts.get(v.sku, 0) > 1:
            yield _vt(p, v), f"SKU {v.sku} is used by more than one variant"


def _decimal(s: str) -> Decimal | None:
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


@check("variant_price")
def variant_price(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    for v in p.variants:
        price = _decimal(v.price)
        if price is None or price <= 0:
            yield _vt(p, v), f"price {v.price!r} is not a positive amount"


@check("compare_at_above_price")
def compare_at_above_price(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    for v in p.variants:
        price, was = _decimal(v.price), _decimal(v.compare_at)
        if price is not None and was is not None and was <= price:
            yield _vt(p, v), f"compare-at {v.compare_at} is not above price {v.price}"


@check("availability_known")
def availability_known(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    """Feeds need in_stock/out_of_stock. Without inventory tracking we can only say 'unknown'."""
    for v in p.variants:
        if not v.tracker and not v.qty:
            yield _vt(p, v), "inventory not tracked, availability would be 'unknown'"


@check("variant_image")
def variant_image(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    """Colour variants should point at an image of that colour."""
    color = p.has_option("color", "colour")
    if not color or len(set(p.option_values(color))) < 2:
        return
    for v in p.variants:
        if not v.image:
            yield _vt(p, v), f"{v.options.get(color)} variant has no image of its own"


@check("active_but_empty")
def active_but_empty(p: Product, params: dict, ctx: Context) -> Iterator[Finding]:
    if p.status == "active" and not p.variants:
        yield p.handle, "active product with no purchasable variants"

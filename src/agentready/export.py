"""Write an OpenAI ACP product feed (JSON Lines) from a Shopify export.

One row per variant. Fields we can't derive honestly are left out rather than invented;
`export` returns the list of rows it had to skip and why. Variant-specific URLs need the
variant's numeric id, which the CSV export doesn't contain, so `url` is the product page.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .shopify import Product


def _availability(qty: str, tracker: str, policy: str) -> str:
    if not tracker and not qty:
        return "unknown"
    try:
        n = int(qty or 0)
    except ValueError:
        return "unknown"
    if n > 0:
        return "in_stock"
    return "backorder" if policy == "continue" else "out_of_stock"


def _price(amount: str, currency: str) -> str | None:
    try:
        d = Decimal(amount)
    except (InvalidOperation, ValueError):
        return None
    if d <= 0:
        return None
    return f"{d.quantize(Decimal('0.01'))} {currency.upper()}"


def acp_rows(
    products: list[Product], store_url: str, seller: str, currency: str
) -> tuple[list[dict], list[str]]:
    rows, skipped = [], []
    base = store_url.rstrip("/")
    for p in products:
        if p.status != "active":
            continue
        multi = len(p.variants) > 1
        for v in p.variants:
            label = f"{p.handle}/{v.sku or f'row{v.row}'}"
            price = _price(v.price, currency)
            image = v.image or (p.images[0].src if p.images else "")
            problems = [
                name
                for name, ok in (
                    ("sku", v.sku),
                    ("description", p.description),
                    ("brand", p.vendor),
                    ("image", image),
                    ("price", price),
                )
                if not ok
            ]
            if problems:
                skipped.append(f"{label}: missing {', '.join(problems)}")
                continue
            variant_name = " / ".join(v.options.values())
            row: dict = {
                "item_id": v.sku,
                "title": f"{p.title} - {variant_name}" if multi and variant_name else p.title,
                "description": p.description,
                "url": f"{base}/products/{p.handle}",
                "brand": p.vendor,
                "seller_name": seller,
                "image_url": image,
                "availability": _availability(v.qty, v.tracker, v.policy),
                "price": price,
            }
            if multi:
                row["group_id"] = p.handle
                row["listing_has_variations"] = True
                row["variant_dict"] = dict(v.options)
            size = p.has_option("size")
            color = p.has_option("color", "colour")
            if size and v.options.get(size):
                row["size"] = v.options[size]
            if color and v.options.get(color):
                row["color"] = v.options[color]
            material = p.metafield("material", "fabric")
            if material:
                row["material"] = material
            rows.append(row)
    return rows, skipped

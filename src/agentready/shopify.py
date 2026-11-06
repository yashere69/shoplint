"""Read Shopify's product CSV export into products with variants.

Shopify writes one row per variant (and extra rows per additional image). Only the first
row of a product carries product-level columns; following rows repeat just the Handle.
Metafields appear as columns like "Fabric (product.metafields.custom.fabric)".
"""

from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass, field
from pathlib import Path

_METAFIELD_COL = re.compile(r"\(product\.metafields\.(?P<ns>[\w-]+)\.(?P<key>[\w-]+)\)\s*$")
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|br|li|div|h\d)[^>]*>", re.I)


@dataclass
class Image:
    src: str
    alt: str
    position: int


@dataclass
class Variant:
    sku: str
    price: str
    compare_at: str
    qty: str
    tracker: str
    policy: str
    barcode: str
    image: str
    options: dict[str, str]  # option name -> value, e.g. {"Size": "M", "Color": "Indigo"}
    row: int


@dataclass
class Product:
    handle: str
    title: str
    body_html: str
    vendor: str
    type: str
    category: str
    tags: list[str]
    status: str
    seo_title: str
    seo_description: str
    option_names: list[str]
    metafields: dict[str, str]  # "custom.fabric" -> "Cotton"
    images: list[Image] = field(default_factory=list)
    variants: list[Variant] = field(default_factory=list)
    row: int = 0

    @property
    def description(self) -> str:
        return html_to_text(self.body_html)

    def option_values(self, name: str) -> list[str]:
        return [v.options[name] for v in self.variants if v.options.get(name)]

    def has_option(self, *names: str) -> str | None:
        wanted = {n.lower() for n in names}
        return next((n for n in self.option_names if n.lower() in wanted), None)

    def metafield(self, *keys: str) -> str | None:
        """Look up a metafield by key, ignoring namespace: metafield('fabric', 'material')."""
        wanted = {k.lower() for k in keys}
        for full, value in self.metafields.items():
            if full.split(".", 1)[-1].lower() in wanted and value.strip():
                return value.strip()
        return None


def html_to_text(s: str) -> str:
    s = _BLOCK.sub("\n", s or "")
    s = _TAG.sub("", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def read_csv(path: str | Path) -> list[Product]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "Handle" not in reader.fieldnames:
            raise ValueError(f"{path}: not a Shopify product export (no 'Handle' column)")
        meta_cols = {
            col: f"{m['ns']}.{m['key']}"
            for col in reader.fieldnames
            if (m := _METAFIELD_COL.search(col))
        }
        products: dict[str, Product] = {}
        for i, row in enumerate(reader, start=2):  # row 1 is the header

            def get(k: str, row: dict = row) -> str:
                return (row.get(k) or "").strip()

            handle = get("Handle")
            if not handle:
                continue
            p = products.get(handle)
            if p is None:
                option_names = [get(f"Option{n} Name") for n in (1, 2, 3) if get(f"Option{n} Name")]
                p = Product(
                    handle=handle,
                    title=get("Title"),
                    body_html=row.get("Body (HTML)") or "",
                    vendor=get("Vendor"),
                    type=get("Type"),
                    category=get("Product Category"),
                    tags=[t.strip() for t in get("Tags").split(",") if t.strip()],
                    status=get("Status").lower() or "active",
                    seo_title=get("SEO Title"),
                    seo_description=get("SEO Description"),
                    option_names=option_names,
                    metafields={key: get(col) for col, key in meta_cols.items() if get(col)},
                    row=i,
                )
                products[handle] = p
            if get("Image Src"):
                p.images.append(
                    Image(get("Image Src"), get("Image Alt Text"), int(get("Image Position") or 0))
                )
            has_variant = any(get(f"Option{n} Value") for n in (1, 2, 3)) or get("Variant Price")
            if has_variant:
                opts = {
                    name: get(f"Option{n} Value")
                    for n, name in enumerate(p.option_names, start=1)
                    if get(f"Option{n} Value")
                }
                p.variants.append(
                    Variant(
                        sku=get("Variant SKU"),
                        price=get("Variant Price"),
                        compare_at=get("Variant Compare At Price"),
                        qty=get("Variant Inventory Qty"),
                        tracker=get("Variant Inventory Tracker"),
                        policy=get("Variant Inventory Policy"),
                        barcode=get("Variant Barcode"),
                        image=get("Variant Image"),
                        options=opts,
                        row=i,
                    )
                )
        return list(products.values())

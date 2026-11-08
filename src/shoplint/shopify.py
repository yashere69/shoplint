"""Read Shopify's product CSV export into products with variants.

Shopify writes one row per variant (and extra rows per additional image). Only the first
row of a product carries product-level columns; following rows repeat just the handle.
Metafields appear as columns like "Fabric (product.metafields.custom.fabric)".

Shopify renamed most columns in its current template ("Handle" became "URL handle",
"Body (HTML)" became "Description", "Variant Price" became "Price", and so on). Both the
older and the current headers are read, matched without regard to case or spacing.
"""

from __future__ import annotations

import csv
import html
import io
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
    gift_card: bool = False

    @property
    def is_apparel(self) -> bool:
        """Size and colour rules only make sense for clothing. A gift card never is; a
        product with a category is apparel only under "Apparel & Accessories"; with no
        category, assume it is, since this tool is aimed at clothing stores."""
        if self.gift_card:
            return False
        return not self.category or self.category.lower().startswith("apparel")

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


# internal name -> header in the older export, header in the current template
_COLUMNS: dict[str, tuple[str, ...]] = {
    "handle": ("Handle", "URL handle"),
    "title": ("Title",),
    "body": ("Body (HTML)", "Description"),
    "vendor": ("Vendor",),
    "category": ("Product Category", "Product category"),
    "type": ("Type",),
    "tags": ("Tags",),
    "status": ("Status",),
    "seo_title": ("SEO Title",),
    "seo_description": ("SEO Description",),
    "sku": ("Variant SKU", "SKU"),
    "price": ("Variant Price", "Price"),
    "compare_at": ("Variant Compare At Price", "Compare-at price"),
    "qty": ("Variant Inventory Qty", "Inventory quantity"),
    "tracker": ("Variant Inventory Tracker", "Inventory tracker"),
    "policy": ("Variant Inventory Policy", "Continue selling when out of stock"),
    "barcode": ("Variant Barcode", "Barcodes"),
    "image_src": ("Image Src", "Product image URL"),
    "image_position": ("Image Position",),
    "image_alt": ("Image Alt Text",),
    "variant_image": ("Variant Image", "Variant image URL"),
    "gift_card": ("Gift Card",),
    **{f"option{n}_name": (f"Option{n} Name",) for n in (1, 2, 3)},
    **{f"option{n}_value": (f"Option{n} Value",) for n in (1, 2, 3)},
}


def _norm(header: str) -> str:
    return " ".join(header.replace("\ufeff", "").split()).lower()


def resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    """Map internal names to the headers this file actually uses."""
    by_norm = {_norm(h): h for h in fieldnames}
    out = {}
    for key, names in _COLUMNS.items():
        for name in names:
            if _norm(name) in by_norm:
                out[key] = by_norm[_norm(name)]
                break
    return out


def _delimiter(text: str) -> str:
    """Excel set to a European locale saves 'CSV' with semicolons; some tools write tabs."""
    header = text.split("\n", 1)[0]
    for d in (",", ";", "\t"):
        if d in header:
            return d
    return ","


def _open(path: str | Path):
    """Shopify exports UTF-8, but a CSV that has been opened and re-saved in Excel on
    Windows is usually cp1252. Try UTF-8 first and fall back rather than fail."""
    raw = Path(path).read_bytes()
    try:
        return io.StringIO(raw.decode("utf-8-sig"), newline=""), "utf-8"
    except UnicodeDecodeError:
        return io.StringIO(raw.decode("cp1252", errors="replace"), newline=""), "cp1252"


def read_csv(path: str | Path) -> list[Product]:
    f, _ = _open(path)
    with f:
        text = f.getvalue()
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
        cols = resolve_columns(list(reader.fieldnames or []))
        if "handle" not in cols:
            seen = ", ".join(repr(h) for h in (reader.fieldnames or [])[:5]) or "nothing"
            raise ValueError(
                f"{path}: not a Shopify product export: no 'Handle' or 'URL handle' column "
                f"(the header starts with {seen})"
            )
        meta_cols = {
            col: f"{m['ns']}.{m['key']}"
            for col in reader.fieldnames or []
            if (m := _METAFIELD_COL.search(col))
        }
        continue_col = _norm(cols.get("policy", "")) == "continue selling when out of stock"
        products: dict[str, Product] = {}
        for i, row in enumerate(reader, start=2):  # row 1 is the header

            def get(key: str, row: dict = row) -> str:
                col = cols.get(key)
                return (row.get(col) or "").strip() if col else ""

            def raw(col: str, row: dict = row) -> str:
                return (row.get(col) or "").strip()

            handle = get("handle")
            if not handle:
                continue
            p = products.get(handle)
            if p is None:
                option_names = [get(f"option{n}_name") for n in (1, 2, 3) if get(f"option{n}_name")]
                p = Product(
                    handle=handle,
                    title=get("title"),
                    body_html=(row.get(cols["body"]) or "") if "body" in cols else "",
                    vendor=get("vendor"),
                    type=get("type"),
                    category=get("category"),
                    tags=[t.strip() for t in get("tags").split(",") if t.strip()],
                    status=get("status").lower() or "active",
                    seo_title=get("seo_title"),
                    seo_description=get("seo_description"),
                    option_names=option_names,
                    metafields={key: raw(col) for col, key in meta_cols.items() if raw(col)},
                    row=i,
                    gift_card=get("gift_card").lower() in {"true", "yes", "1"},
                )
                products[handle] = p
            if get("image_src"):
                position = get("image_position")
                p.images.append(
                    Image(
                        get("image_src"),
                        get("image_alt"),
                        int(position) if position.isdigit() else 0,
                    )
                )
            has_variant = any(get(f"option{n}_value") for n in (1, 2, 3)) or get("price")
            if has_variant:
                opts = {
                    name: get(f"option{n}_value")
                    for n, name in enumerate(p.option_names, start=1)
                    if get(f"option{n}_value")
                }
                policy = get("policy")
                if continue_col and policy:  # TRUE/FALSE in the current template
                    policy = "continue" if policy.lower() in {"true", "yes", "1"} else "deny"
                p.variants.append(
                    Variant(
                        sku=get("sku"),
                        price=get("price"),
                        compare_at=get("compare_at"),
                        qty=get("qty"),
                        tracker=get("tracker"),
                        policy=policy.lower(),
                        barcode=get("barcode").split(";")[0].strip(),
                        image=get("variant_image"),
                        options=opts,
                        row=i,
                    )
                )
        return list(products.values())

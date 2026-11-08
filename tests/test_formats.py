"""Shopify exports as they arrive from real stores: the current template's renamed headers,
spreadsheet re-saves, and files nobody designed. These fixtures are constructed from
Shopify's column documentation, not copied from a store."""

import csv
import io
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from shoplint.probe import load_questions, probe
from shoplint.rules import audit, builtin_packs, load_pack
from shoplint.shopify import read_csv

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

# the older export's headers -> the names in Shopify's current product CSV template
CURRENT = {
    "Handle": "URL handle",
    "Body (HTML)": "Description",
    "Product Category": "Product category",
    "Published": "Published on online store",
    "Variant SKU": "SKU",
    "Variant Price": "Price",
    "Variant Compare At Price": "Compare-at price",
    "Variant Inventory Qty": "Inventory quantity",
    "Variant Inventory Tracker": "Inventory tracker",
    "Variant Inventory Policy": "Continue selling when out of stock",
    "Variant Barcode": "Barcodes",
    "Image Src": "Product image URL",
    "Image Position": "Image position",
    "Image Alt Text": "Image alt text",
    "Variant Image": "Variant image URL",
    "SEO Title": "SEO title",
    "SEO Description": "SEO description",
    **{f"Option{n} Name": f"Option{n} name" for n in (1, 2, 3)},
    **{f"Option{n} Value": f"Option{n} value" for n in (1, 2, 3)},
}


def rewrite(tmp_path: Path, name: str, headers=None, delimiter=",", encoding="utf-8") -> Path:
    rows = list(csv.reader(io.StringIO((EXAMPLES / "indigo-loom.csv").read_text("utf-8"))))
    header = rows[0]
    if headers:
        policy = header.index("Variant Inventory Policy")
        header = [headers.get(h, h) for h in header]
        if "Continue selling when out of stock" in header:  # the template uses TRUE/FALSE
            for r in rows[1:]:
                r[policy] = {"continue": "TRUE", "deny": "FALSE"}.get(r[policy], r[policy])
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter).writerows([header, *rows[1:]])
    path = tmp_path / name
    path.write_bytes(out.getvalue().encode(encoding))
    return path


def test_current_template_reads_the_same_as_the_older_export(tmp_path):
    """Regression: the current template has no 'Handle' column, so 0.2 refused every file
    exported from Shopify's current admin."""
    old = read_csv(EXAMPLES / "indigo-loom.csv")
    new = read_csv(rewrite(tmp_path, "current.csv", CURRENT))
    assert new == old


@pytest.mark.parametrize(
    "delimiter, encoding", [(";", "utf-8"), ("\t", "utf-8"), (",", "utf-8-sig"), (",", "cp1252")]
)
def test_spreadsheet_resaves(tmp_path, delimiter, encoding):
    path = rewrite(tmp_path, "resaved.csv", delimiter=delimiter, encoding=encoding)
    got = read_csv(path)
    assert [p.handle for p in got] == [p.handle for p in read_csv(EXAMPLES / "indigo-loom.csv")]


def test_headers_match_without_regard_to_case_or_spacing(tmp_path):
    p = tmp_path / "odd.csv"
    p.write_text(
        "url  HANDLE,title,variant price,option1 NAME,option1 value\n"
        "kurta,Kurta,999,Size,M\nkurta,,999,,L\n",
        encoding="utf-8",
    )
    (k,) = read_csv(p)
    assert (k.title, k.option_values("Size")) == ("Kurta", ["M", "L"])


def test_messy_cells_do_not_crash(tmp_path):
    """Regression: a non-numeric image position raised ValueError mid-file."""
    p = tmp_path / "messy.csv"
    p.write_text(
        "URL handle,Title,Price,Barcodes,Product image URL,Image position,Variant image URL\n"
        'a,"Kurta, ""Indigo""",999,890123;890124,https://x/a.jpg,1.0,\n'
        "a,,,,https://x/b.jpg,second,\n"
        "b,Dupatta,,,,,\n",
        encoding="utf-8",
    )
    a, b = read_csv(p)
    assert a.title == 'Kurta, "Indigo"' and a.variants[0].barcode == "890123"
    assert len(a.images) == 2 and b.variants == []


def test_a_file_that_is_not_a_product_export_says_so(tmp_path):
    p = tmp_path / "orders.csv"
    p.write_text("Name,Email,Financial Status\n#1001,a@b.c,paid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="URL handle.*'Name', 'Email'"):
        read_csv(p)


CELL = st.text(st.characters(exclude_categories=("Cs",)), max_size=12)


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.sampled_from(sorted(set(CURRENT) | set(CURRENT.values()) | {"Title", "Tags"})),
        min_size=1,
        max_size=10,
        unique=True,
    ),
    st.lists(st.lists(CELL, min_size=0, max_size=10), max_size=8),
)
def test_any_csv_is_read_or_refused_cleanly(tmp_path_factory, header, rows):
    """Whatever the file holds, the audit either runs or stops with a ValueError."""
    out = io.StringIO()
    csv.writer(out).writerows([header, *rows])
    path = tmp_path_factory.mktemp("fuzz") / "f.csv"
    path.write_text(out.getvalue(), encoding="utf-8")
    try:
        products = read_csv(path)
    except ValueError:
        return
    audit(products, [load_pack(n) for n in builtin_packs()])
    probe(products, load_questions(None))


def test_archived_products_and_gift_cards_are_not_held_to_apparel_rules(tmp_path):
    p = tmp_path / "store.csv"
    p.write_text(
        "URL handle,Title,Product category,Status,SKU,Price,Gift card,Product image URL\n"
        "gift,Gift Card,Gift Cards,active,GC-1,1000,TRUE,https://x/g.jpg\n"
        "old,Old Kurta,Apparel & Accessories > Clothing,archived,K-1,999,FALSE,\n"
        "bowl,Brass Bowl,Home & Garden > Decor,active,B-1,499,FALSE,https://x/b.jpg\n",
        encoding="utf-8",
    )
    findings = audit(read_csv(p), [load_pack(n) for n in builtin_packs()])
    targets = {(f.rule, f.target) for f in findings}
    assert not [t for t in targets if t[1].startswith("old")]  # archived: not syndicated
    assert ("gmc.size", "gift") not in targets and ("gmc.size", "bowl") not in targets

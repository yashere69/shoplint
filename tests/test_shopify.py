from pathlib import Path

import pytest

from shoplint.shopify import html_to_text, read_csv

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "indigo-loom.csv"


def test_groups_variant_rows_under_their_product():
    products = {p.handle: p for p in read_csv(SAMPLE)}
    dabu = products["indigo-dabu-kurta"]
    assert [v.sku for v in dabu.variants] == [f"IL-DAB-{s}" for s in "XS S M L XL XXL".split()]
    assert dabu.option_values("Size")[0] == "XS"
    assert len(dabu.images) == 2 and dabu.images[1].alt.startswith("Close-up")


def test_metafield_columns_are_parsed_and_namespace_is_optional():
    dabu = {p.handle: p for p in read_csv(SAMPLE)}["indigo-dabu-kurta"]
    assert dabu.metafields["custom.fabric"] == "Cotton"
    assert dabu.metafield("material", "fabric") == "Cotton"


def test_two_option_products_keep_option_names():
    lav = {p.handle: p for p in read_csv(SAMPLE)}["lavender-kurta"]
    assert lav.option_names == ["Size", "Color"]
    assert lav.variants[2].options == {"Size": "M", "Color": "Sage"}


def test_html_to_text():
    assert html_to_text("<p>Hand wash&nbsp;cold.</p><p>Dry in shade.</p>") == (
        "Hand wash\xa0cold.\nDry in shade."
    )


def test_rejects_non_shopify_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("name,price\nkurta,10\n")
    with pytest.raises(ValueError, match="Handle"):
        read_csv(p)

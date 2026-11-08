import pytest

from shoplint.shopify import Image, Product, Variant


def variant(sku="SKU-1", price="1000.00", options=None, **kw):
    base = dict(
        sku=sku,
        price=price,
        compare_at="",
        qty="5",
        tracker="shopify",
        policy="deny",
        barcode="",
        image="",
        options=options or {"Size": "M"},
        row=2,
    )
    base.update(kw)
    return Variant(**base)


@pytest.fixture
def make_product():
    def make(**kw):
        base = dict(
            handle="kurta",
            title="Cotton Kurta",
            body_html="<p>Soft cotton kurta.</p>",
            vendor="Brand",
            type="Kurta",
            category="",
            tags=[],
            status="active",
            seo_title="",
            seo_description="",
            option_names=["Size"],
            metafields={},
            images=[Image("https://cdn.example.com/a.jpg", "front", 1)],
            variants=[variant()],
            row=2,
        )
        base.update(kw)
        return Product(**base)

    return make

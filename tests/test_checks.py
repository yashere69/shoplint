from agentready.checks import REGISTRY, Context, size_system
from agentready.shopify import Image

from .conftest import variant


def run(name, product, params=None, others=()):
    ctx = Context([product, *others])
    return list(REGISTRY[name](product, params or {}, ctx))


def test_size_system_classifier():
    assert size_system("XL") == "letter"
    assert size_system("38") == "bust-inch"
    assert size_system("Free Size") == "free"
    assert size_system("Small") == "word"
    assert size_system("UK 10") == "other"


def test_size_mix(make_product):
    mixed = make_product(variants=[variant(options={"Size": "S"}), variant(options={"Size": "38"})])
    assert run("size_system_consistent", mixed)
    clean = make_product(variants=[variant(options={"Size": s}) for s in ("S", "M", "Free Size")])
    assert not run("size_system_consistent", clean) or "free" in str(
        run("size_system_consistent", clean)
    )


def test_duplicate_and_missing_sku(make_product):
    a = make_product(handle="a", variants=[variant(sku="X"), variant(sku="")])
    b = make_product(handle="b", variants=[variant(sku="X")])
    targets = [t for t, _ in run("variant_sku", a, others=[b])]
    assert targets == ["a/X", "a/row2"]


def test_price_and_compare_at(make_product):
    p = make_product(variants=[variant(price="0"), variant(price="abc")])
    assert len(run("variant_price", p)) == 2
    fake = make_product(variants=[variant(price="1000", compare_at="1000")])
    real = make_product(variants=[variant(price="1000", compare_at="1200")])
    assert run("compare_at_above_price", fake) and not run("compare_at_above_price", real)


def test_availability_needs_tracking(make_product):
    untracked = make_product(variants=[variant(tracker="", qty="")])
    assert run("availability_known", untracked)
    assert not run("availability_known", make_product())


def test_alt_text_reports_positions(make_product):
    p = make_product(images=[Image("a", "ok", 1), Image("b", "", 2)])
    assert run("image_alt_text", p) == [("kurta", "images without alt text at positions [2]")]


def test_option_case(make_product):
    p = make_product(
        option_names=["Color"],
        variants=[variant(options={"Color": "Blue"}), variant(options={"Color": "blue"})],
    )
    assert run("option_case_consistent", p)


def test_attribute_from_option_or_metafield(make_product):
    params = {"names": ["material", "fabric"], "label": "material"}
    assert run("product_attribute", make_product(), params)
    assert not run("product_attribute", make_product(metafields={"custom.fabric": "Silk"}), params)
    assert not run("product_attribute", make_product(option_names=["Size", "Fabric"]), params)


def test_variant_image_only_for_multi_colour(make_product):
    single = make_product(option_names=["Color"], variants=[variant(options={"Color": "Red"})])
    assert not run("variant_image", single)
    multi = make_product(
        option_names=["Color"],
        variants=[variant(options={"Color": "Red"}), variant(options={"Color": "Teal"}, image="t")],
    )
    assert [t for t, _ in run("variant_image", multi)] == ["kurta/SKU-1"]

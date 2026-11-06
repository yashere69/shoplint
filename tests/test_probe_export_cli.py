import json
from pathlib import Path

import yaml

from agentready.cli import main
from agentready.export import acp_rows
from agentready.probe import probe, summary
from agentready.rules import audit, builtin_packs, load_pack
from agentready.shopify import read_csv

ROOT = Path(__file__).resolve().parent.parent
BEFORE = ROOT / "examples" / "indigo-loom.csv"
AFTER = ROOT / "examples" / "indigo-loom-fixed.csv"


def test_sample_catalog_matches_reviewed_expectations():
    findings = audit(read_csv(BEFORE), [load_pack(n) for n in builtin_packs()])
    got = sorted([f.rule, f.target] for f in findings if f.level != "info")
    expected = sorted(yaml.safe_load((ROOT / "eval" / "expected.yaml").read_text()))
    assert got == expected


def test_probe_separates_structured_from_prose(make_product):
    p = make_product(body_html="<p>Pure linen, hand wash only.</p>")
    where = {a.question: a.where for a in probe([p])}
    assert where["fabric"] == "prose-only"
    assert where["care"] == "prose-only"
    assert where["sizes"] == "structured"
    assert where["colour"] == "missing"


def test_fixing_the_catalog_raises_answerability():
    before = summary(probe(read_csv(BEFORE)))["answerable_pct"]
    after = summary(probe(read_csv(AFTER)))["answerable_pct"]
    assert after > before


def test_acp_export_never_invents_fields():
    rows, skipped = acp_rows(read_csv(BEFORE), "https://shop.example.com", "Indigo Loom", "inr")
    assert any("handloom-cotton-saree" in s and "image" in s for s in skipped)
    assert any("block-print-palazzo" in s and "sku" in s for s in skipped)
    dabu = next(r for r in rows if r["item_id"] == "IL-DAB-M")
    assert dabu["price"] == "1890.00 INR"
    assert dabu["availability"] == "in_stock"
    assert dabu["group_id"] == "indigo-dabu-kurta" and dabu["variant_dict"] == {"Size": "M"}
    assert dabu["url"] == "https://shop.example.com/products/indigo-dabu-kurta"
    untracked = next(r for r in rows if r["item_id"] == "IL-LEH-M")
    assert untracked["availability"] == "unknown"


def test_cli_audit_exit_codes_and_outputs(tmp_path, capsys):
    assert main(["audit", str(AFTER), "--fail-on", "error"]) == 0
    assert (
        main(
            [
                "audit",
                str(BEFORE),
                "--html",
                str(tmp_path / "r.html"),
                "--json",
                str(tmp_path / "r.json"),
            ]
        )
        == 1
    )
    html = (tmp_path / "r.html").read_text()
    assert '<html lang="en">' in html and "acp.item-id" in html
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["probe"]["questions"] > 0
    assert (
        main(
            [
                "export",
                str(AFTER),
                "--store-url",
                "https://x.example",
                "--seller",
                "S",
                "-o",
                str(tmp_path / "feed.jsonl"),
            ]
        )
        == 0
    )
    assert len((tmp_path / "feed.jsonl").read_text().splitlines()) > 20


def test_cli_rejects_unknown_file(capsys):
    assert main(["audit", "nope.csv"]) == 2

import json
from pathlib import Path

import yaml

from shoplint.cli import main
from shoplint.export import acp_rows
from shoplint.probe import probe, summary
from shoplint.rules import audit, builtin_packs, load_pack
from shoplint.shopify import read_csv

ROOT = Path(__file__).resolve().parent.parent
BEFORE = ROOT / "examples" / "indigo-loom.csv"
AFTER = ROOT / "examples" / "indigo-loom-fixed.csv"


def test_sample_catalog_matches_reviewed_expectations():
    findings = audit(read_csv(BEFORE), [load_pack(n) for n in builtin_packs()])
    got = sorted([f.rule, f.target] for f in findings if f.level != "info")
    expected = sorted(yaml.safe_load((ROOT / "eval" / "expected.yaml").read_text(encoding="utf-8")))
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
    html = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in html and "acp.item-id" in html
    data = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
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
    assert len((tmp_path / "feed.jsonl").read_text(encoding="utf-8").splitlines()) > 20


def test_cli_rejects_unknown_file(capsys):
    assert main(["audit", "nope.csv"]) == 2


def test_excel_resaved_cp1252_csv_is_read(tmp_path):
    p = tmp_path / "excel.csv"
    p.write_bytes("Handle,Title,Variant Price\nk,Kurta café,999\n".encode("cp1252"))
    (product,) = read_csv(p)
    assert product.title == "Kurta café"


def test_unknown_pack_is_a_clean_error(capsys):
    assert main(["audit", str(BEFORE), "--pack", "nope"]) == 2
    assert "use one of acp, gmc, hygiene" in capsys.readouterr().err


def test_large_catalog_stays_fast(tmp_path):
    import time

    lines = ["Handle,Title,Option1 Name,Option1 Value,Variant SKU,Variant Price"]
    for i in range(3000):
        for j, size in enumerate(["S", "M", "L", "XL"]):
            lines.append(
                f"p{i},{'Kurta' if j == 0 else ''},{'Size' if j == 0 else ''},"
                f"{size},SKU{i}{size},999"
            )
    p = tmp_path / "big.csv"
    p.write_text("\n".join(lines), encoding="utf-8")
    start = time.perf_counter()
    findings = audit(read_csv(p), [load_pack(n) for n in builtin_packs()])
    assert time.perf_counter() - start < 5  # was ~20 s when size systems were recounted
    assert findings


def test_custom_question_set(tmp_path, make_product):
    from shoplint.probe import load_questions

    qs = tmp_path / "q.yaml"
    qs.write_text(
        "- id: warranty\n  ask: Is there a warranty?\n"
        "  structured: {metafields: [warranty]}\n  prose: '\\bwarranty\\b'\n"
        "- id: voltage\n  ask: What voltage?\n  applies_if: {text: lamp}\n"
        "  structured: {options: [voltage]}\n  prose: '\\d+ ?V\\b'\n",
        encoding="utf-8",
    )
    questions = load_questions(qs)
    kettle = make_product(title="Steel kettle", body_html="<p>1 year warranty</p>")
    where = {a.question: a.where for a in probe([kettle], questions)}
    assert where == {"warranty": "prose-only"}  # voltage only applies to lamps


def test_bad_question_file_is_a_clean_error(tmp_path, capsys):
    qs = tmp_path / "q.yaml"
    qs.write_text("- id: x\n  ask: y\n", encoding="utf-8")
    assert main(["audit", str(BEFORE), "--questions", str(qs)]) == 2
    assert "needs id, ask and prose" in capsys.readouterr().err


def test_findings_csv_and_input_protection(tmp_path):
    import csv as csvmod

    out = tmp_path / "fixes.csv"
    main(["audit", str(BEFORE), "--findings-csv", str(out), "--fail-on", "never"])
    rows = list(csvmod.DictReader(out.open(encoding="utf-8")))
    assert rows[0].keys() == {"level", "rule", "product", "detail", "why"}
    assert any(r["rule"] == "acp.item-id" for r in rows)
    copy = tmp_path / "in.csv"
    copy.write_bytes(BEFORE.read_bytes())
    assert main(["audit", str(copy), "--findings-csv", str(copy)]) == 2
    assert copy.read_bytes() == BEFORE.read_bytes()

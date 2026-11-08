# Changelog

Versions before 0.3.0 were published under the name agentready.

## Unreleased

- Output is UTF-8 even when redirected on Windows, where it used to follow the code page
  and fail on Devanagari text.
- CI runs the tests on Windows and macOS as well as Linux.
- A rule pack that isn't valid YAML, or lacks a required key, is reported with the file
  and line instead of a traceback.
- An export with a header and no products is an error (exit 2) for both `audit` and
  `export`. Before, `audit` reported 0/0 answerable and exited 0.

## 0.3.0

- Renamed from agentready: that name on PyPI belongs to an unrelated project.
- Reads Shopify's current product CSV template (`URL handle`, `Description`, `Price`,
  `Continue selling when out of stock`, `Barcodes`…) as well as older exports. 0.2 refused
  every file exported from the current admin. Headers match without regard to case or
  spacing.
- Semicolon- and tab-separated files are read; a non-numeric image position no longer
  stops the run.
- Archived products are skipped like drafts. Size and colour rules skip gift cards and
  products outside "Apparel & Accessories" (new `scope: apparel` in pack YAML).
- Tests read the sample in both header formats, plus a hypothesis test over random files.

## 0.2.0

- Buyer questions are YAML; `--questions` for other categories
- `--findings-csv`: one row per problem, refuses to overwrite the input
- Reads CSVs re-saved by Excel as cp1252
- Large catalogs: catalog-wide size system computed once (3,000 products: ~21 s to ~0.3 s)
- Unknown `--pack` names give a clear error

## 0.1.0

- Shopify product CSV reader (variants, images, metafields)
- Rule packs: `acp` (OpenAI product feed, Stable, read 2026-11-07), `gmc` (apparel subset),
  `hygiene`
- Buyer-question probe with structured / prose-only / missing classification
- ACP JSON Lines export that skips rather than invents missing fields
- Text, HTML and JSON reports; `--fail-on` for CI
- Fictional sample catalog with reviewed expectations

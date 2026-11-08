"""Text and HTML reports."""

from __future__ import annotations

import html
from collections import Counter

from .rules import Finding, Pack

_LEVEL_MARK = {"error": "E", "warning": "W", "info": "i"}


def text(findings: list[Finding], packs: list[Pack], probe: dict, n_products: int) -> str:
    lines = [f"{n_products} products checked against: " + ", ".join(p.name for p in packs)]
    levels = Counter(f.level for f in findings)
    lines.append(f"{levels['error']} errors, {levels['warning']} warnings, {levels['info']} info\n")
    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule, []).append(f)
    for rule, fs in by_rule.items():
        lines.append(f"[{_LEVEL_MARK[fs[0].level]}] {rule}  ({len(fs)})  {fs[0].message}")
        for f in fs[:5]:
            lines.append(f"      {f.target}: {f.detail}")
        if len(fs) > 5:
            lines.append(f"      ... {len(fs) - 5} more")
    lines.append("")
    lines.append(
        f"Buyer questions answerable from structured data: {probe['answerable']}/"
        f"{probe['questions']} ({probe['answerable_pct']}%)"
    )
    for q, c in probe["by_question"].items():
        lines.append(
            f"  {q:<13} structured {c['structured']:>3}   prose-only {c['prose-only']:>3}"
            f"   missing {c['missing']:>3}"
        )
    return "\n".join(lines)


def _e(s: object) -> str:
    return html.escape(str(s))


def html_page(
    title: str, findings: list[Finding], packs: list[Pack], probe: dict, n_products: int
) -> str:
    levels = Counter(f.level for f in findings)
    pack_rows = "".join(
        f"<tr><td>{_e(p.title)}</td><td><a href='{_e(p.source)}'>{_e(p.source)}</a></td>"
        f"<td>{_e(p.checked)}</td></tr>"
        if p.source.startswith("http")
        else f"<tr><td>{_e(p.title)}</td><td>{_e(p.source)}</td><td>{_e(p.checked)}</td></tr>"
        for p in packs
    )
    q_rows = ""
    for q, c in probe["by_question"].items():
        total = sum(c.values()) or 1
        bar = "".join(
            f"<span class='seg {k}' style='width:{100 * c[k] / total:.1f}%'></span>"
            for k in ("structured", "prose-only", "missing")
        )
        q_rows += (
            f"<tr><th scope='row'>{_e(q)}</th><td><div class='bar' role='img' "
            f"aria-label='{c['structured']} structured, {c['prose-only']} prose only, "
            f"{c['missing']} missing'>{bar}</div></td><td>{c['structured']}</td>"
            f"<td>{c['prose-only']}</td><td>{c['missing']}</td></tr>"
        )
    f_rows = "".join(
        f"<tr data-level='{f.level}'><td><span class='lvl {f.level}'>{f.level}</span></td>"
        f"<td><code>{_e(f.rule)}</code></td><td>{_e(f.target)}</td><td>{_e(f.detail)}"
        f"<div class='why'>{_e(f.message)}</div></td></tr>"
        for f in findings
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} · shoplint report</title>
<meta name="description" content="Catalog readiness report for AI shopping agents.">
<style>
:root{{--bg:#fbfaf7;--fg:#17212b;--muted:#5b6672;--line:#e3dfd6;--ok:#1f6f5c;
--prose:#c98a12;--miss:#b3412e;--err:#b3412e;--warn:#946200;--info:#3d5a80}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,
"Segoe UI",Roboto,sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:32px 16px 64px}}
h1{{font-size:1.7rem;margin:0 0 4px}} h2{{font-size:1.2rem;margin:40px 0 12px}}
p.sub{{color:var(--muted);margin:0 0 24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.card{{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:#fff}}
.card b{{display:block;font-size:1.6rem}} .card span{{color:var(--muted);font-size:.9rem}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);
border-radius:10px;overflow:hidden}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
thead th{{font-size:.85rem;color:var(--muted);font-weight:600;background:#f4f2ec}}
.wrap{{overflow-x:auto}}
.bar{{display:flex;height:12px;border-radius:6px;overflow:hidden;min-width:140px;
background:var(--line)}}
.seg.structured{{background:var(--ok)}} .seg.prose-only{{background:var(--prose)}}
.seg.missing{{background:var(--miss)}}
.legend span{{margin-right:16px;font-size:.9rem}}
.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}}
.lvl{{font-size:.8rem;font-weight:600;padding:2px 8px;border-radius:999px;color:#fff}}
.lvl.error{{background:var(--err)}} .lvl.warning{{background:var(--warn)}}
.lvl.info{{background:var(--info)}}
.why{{color:var(--muted);font-size:.88rem;margin-top:2px}}
fieldset{{border:0;padding:0;margin:0 0 12px;display:flex;gap:16px;flex-wrap:wrap}}
code{{font-size:.88rem}} a{{color:var(--info)}}
.sr{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}
footer{{margin-top:48px;color:var(--muted);font-size:.88rem}}
</style></head>
<body><main>
<h1>{_e(title)}</h1>
<p class="sub">Checked {n_products} products. Generated by shoplint.</p>
<section aria-labelledby="sum"><h2 id="sum">Summary</h2><div class="cards">
<div class="card"><b>{probe["answerable_pct"]}%</b><span>buyer questions answerable from
structured data</span></div>
<div class="card"><b>{levels["error"]}</b><span>errors</span></div>
<div class="card"><b>{levels["warning"]}</b><span>warnings</span></div>
<div class="card"><b>{levels["info"]}</b><span>info</span></div></div></section>
<section aria-labelledby="q"><h2 id="q">Where the answers live</h2>
<p class="legend"><span><i style="background:var(--ok)"></i>structured</span>
<span><i style="background:var(--prose)"></i>prose only</span>
<span><i style="background:var(--miss)"></i>missing</span></p>
<div class="wrap"><table><thead><tr><th>Question</th><th>Share</th><th>Structured</th>
<th>Prose only</th><th>Missing</th></tr></thead><tbody>{q_rows}</tbody></table></div></section>
<section aria-labelledby="f"><h2 id="f">Findings</h2>
<fieldset><legend class="sr">Show levels</legend>
<label><input type="checkbox" value="error" checked> errors</label>
<label><input type="checkbox" value="warning" checked> warnings</label>
<label><input type="checkbox" value="info" checked> info</label></fieldset>
<div class="wrap"><table><thead><tr><th>Level</th><th>Rule</th><th>Where</th><th>Detail</th>
</tr></thead><tbody id="rows">{f_rows}</tbody></table></div></section>
<section aria-labelledby="p"><h2 id="p">Rule packs</h2><div class="wrap"><table><thead><tr>
<th>Pack</th><th>Written against</th><th>Spec read on</th></tr></thead><tbody>{pack_rows}
</tbody></table></div></section>
<footer>Specs for agent commerce change often. Check the dates above before acting on a
finding.</footer>
</main>
<script>
document.querySelectorAll("fieldset input").forEach(cb => cb.addEventListener("change", () => {{
  const on = [...document.querySelectorAll("fieldset input:checked")].map(c => c.value);
  document.querySelectorAll("#rows tr").forEach(r => r.hidden = !on.includes(r.dataset.level));
}}));
</script>
</body></html>
"""

#!/usr/bin/env python3
"""
render_dashboard.py — combined HTML dashboard across all pairs in a diff run.

Usage:
    python3 render_dashboard.py --diffs /tmp/redline-diffs.json --out ./redline-output/

Only meaningful (and only needs to be run) when there's more than one pair — it builds
one HTML file with tab navigation between pairs plus a summary table, so the user isn't
stuck opening a dozen separate files to get the overview.
"""
import argparse
import html
import json
import os
import sys

from render_html import render_ops  # reuse the same op-rendering logic


CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 960px;
       margin: 40px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.6; }
h1 { font-size: 1.5rem; }
table.summary-table { border-collapse: collapse; width: 100%; margin: 20px 0 32px 0; font-size: 0.92rem; }
table.summary-table th, table.summary-table td { border: 1px solid #ddd; padding: 8px 10px; text-align: left; }
table.summary-table th { background: #f5f5f5; }
table.summary-table tr.no-change td { color: #999; }
nav.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 12px; }
nav.tabs button { padding: 6px 12px; border: 1px solid #ccc; background: #fafafa; border-radius: 4px;
                   cursor: pointer; font-size: 0.85rem; }
nav.tabs button.active { background: #1a1a1a; color: white; border-color: #1a1a1a; }
.pair-panel { display: none; }
.pair-panel.active { display: block; }
.paragraph { margin: 0 0 12px 0; padding: 4px 0; }
.paragraph.unchanged { color: #444; }
.paragraph.added { background: #eaffea; border-left: 3px solid #2e7d32; padding-left: 10px; }
.paragraph.deleted { background: #ffecec; border-left: 3px solid #c62828; padding-left: 10px; opacity: 0.85; }
.paragraph.changed { border-left: 3px solid #999; padding-left: 10px; }
ins { background: #d7f5d7; color: #1e5c1e; text-decoration: none; }
del { background: #ffd9d9; color: #7a1f1f; }
.skipped-note { color: #a55; font-style: italic; }
"""

JS = """
function showPair(id) {
  document.querySelectorAll('.pair-panel').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('nav.tabs button').forEach(el => el.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
  document.getElementById('tab-' + id).classList.add('active');
}
"""


def render_pair_panel(pair):
    orig_name = html.escape(os.path.basename(pair["original"]))
    rev_name = html.escape(os.path.basename(pair["revised"]))

    if pair.get("skipped"):
        body = f'<p class="skipped-note">Skipped: {html.escape(pair.get("reason", "unknown"))}</p>'
    else:
        body = "\n".join(
            f'<p class="paragraph {p["status"]}">{render_ops(p["ops"])}</p>'
            for p in pair["paragraphs"]
        )

    return f'''
<section id="panel-{pair['pair_id']}" class="pair-panel">
  <h2>{orig_name} &rarr; {rev_name}</h2>
  {body}
</section>'''


def render_summary_row(pair):
    orig_name = html.escape(os.path.basename(pair["original"]))
    rev_name = html.escape(os.path.basename(pair["revised"]))
    if pair.get("skipped"):
        return f'<tr class="no-change"><td>{orig_name} &rarr; {rev_name}</td><td colspan="3">Skipped: {html.escape(pair.get("reason",""))}</td></tr>'
    no_change = pair["insertions"] == 0 and pair["deletions"] == 0
    row_class = ' class="no-change"' if no_change else ""
    return (
        f'<tr{row_class}><td>{orig_name} &rarr; {rev_name}</td>'
        f'<td>{pair["insertions"]}</td><td>{pair["deletions"]}</td>'
        f'<td>{pair["changed_paragraphs"]}</td></tr>'
    )


def render(diffs):
    pairs = diffs["pairs"]
    tabs = "\n".join(
        f'<button id="tab-{p["pair_id"]}" class="{"active" if i == 0 else ""}" '
        f'onclick="showPair(\'{p["pair_id"]}\')">{html.escape(os.path.basename(p["original"]))} &rarr; '
        f'{html.escape(os.path.basename(p["revised"]))}</button>'
        for i, p in enumerate(pairs)
    )
    panels = "\n".join(render_pair_panel(p) for p in pairs)
    # mark first panel active
    panels = panels.replace('class="pair-panel"', 'class="pair-panel active"', 1)

    rows = "\n".join(render_summary_row(p) for p in pairs)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redline Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<h1>Redline Dashboard ({diffs.get('mode', 'sequential')} mode, {len(pairs)} comparison{'s' if len(pairs) != 1 else ''})</h1>

<table class="summary-table">
  <thead><tr><th>Comparison</th><th>Insertions</th><th>Deletions</th><th>Changed paragraphs</th></tr></thead>
  <tbody>
{rows}
  </tbody>
</table>

<nav class="tabs">
{tabs}
</nav>

{panels}

<script>{JS}</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Render a combined multi-version HTML dashboard.")
    parser.add_argument("--diffs", required=True, help="Path to diff_engine.py's output JSON.")
    parser.add_argument("--out", required=True, help="Output directory.")
    args = parser.parse_args()

    with open(args.diffs, "r", encoding="utf-8") as f:
        diffs = json.load(f)

    if len(diffs["pairs"]) < 1:
        print("No pairs to render.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "redline_dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render(diffs))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
render_html.py — self-contained HTML visual diff for one version pair.

Usage:
    python3 render_html.py --diffs /tmp/redline-diffs.json --pair v1_v2 --out ./redline-output/

Produces a single HTML file, inline CSS, no external dependencies or network calls,
so it can be opened directly in a browser or shared as one file.
"""
import argparse
import html
import json
import os
import sys


CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 860px;
       margin: 40px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.6; }
header { border-bottom: 2px solid #eee; padding-bottom: 16px; margin-bottom: 24px; }
h1 { font-size: 1.4rem; margin: 0 0 8px 0; }
.summary { color: #555; font-size: 0.95rem; }
.summary b { color: #1a1a1a; }
.paragraph { margin: 0 0 14px 0; padding: 4px 0; }
.paragraph.unchanged { color: #444; }
.paragraph.added { background: #eaffea; border-left: 3px solid #2e7d32; padding-left: 10px; }
.paragraph.deleted { background: #ffecec; border-left: 3px solid #c62828; padding-left: 10px; opacity: 0.85; }
.paragraph.changed { border-left: 3px solid #999; padding-left: 10px; }
ins { background: #d7f5d7; color: #1e5c1e; text-decoration: none; }
del { background: #ffd9d9; color: #7a1f1f; }
.legend { font-size: 0.85rem; color: #666; margin-top: 8px; }
.legend ins, .legend del { padding: 1px 4px; border-radius: 2px; }
"""


def render_ops(ops):
    out = []
    for op in ops:
        text = html.escape(op["text"])
        if op["type"] == "insert":
            out.append(f"<ins>{text}</ins>")
        elif op["type"] == "delete":
            out.append(f"<del>{text}</del>")
        else:
            out.append(text)
    return "".join(out)


def render_paragraph(para):
    status = para["status"]
    body = render_ops(para["ops"])
    return f'<p class="paragraph {status}">{body}</p>'


def render(pair):
    orig_name = html.escape(os.path.basename(pair["original"]))
    rev_name = html.escape(os.path.basename(pair["revised"]))
    body_html = "\n".join(render_paragraph(p) for p in pair["paragraphs"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Redline: {orig_name} vs {rev_name}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>{orig_name} &rarr; {rev_name}</h1>
  <div class="summary">
    <b>{pair['insertions']}</b> insertion(s), <b>{pair['deletions']}</b> deletion(s)
    across <b>{pair['changed_paragraphs']}</b> changed paragraph(s);
    {pair['unchanged_paragraphs']} unchanged.
  </div>
  <div class="legend"><ins>inserted text</ins> &nbsp; <del>deleted text</del></div>
</header>
<main>
{body_html}
</main>
</body>
</html>
"""


def find_pair(diffs, pair_id):
    for p in diffs["pairs"]:
        if p["pair_id"] == pair_id:
            return p
    return None


def main():
    parser = argparse.ArgumentParser(description="Render a single-pair HTML visual diff.")
    parser.add_argument("--diffs", required=True, help="Path to diff_engine.py's output JSON.")
    parser.add_argument("--pair", required=True, help="pair_id to render (e.g. v1_v2).")
    parser.add_argument("--out", required=True, help="Output directory.")
    args = parser.parse_args()

    with open(args.diffs, "r", encoding="utf-8") as f:
        diffs = json.load(f)

    pair = find_pair(diffs, args.pair)
    if pair is None:
        print(f"Pair '{args.pair}' not found in {args.diffs}.", file=sys.stderr)
        sys.exit(1)
    if pair.get("skipped"):
        print(f"Pair '{args.pair}' was skipped during diffing ({pair.get('reason')}); nothing to render.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"{args.pair}_redline.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render(pair))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

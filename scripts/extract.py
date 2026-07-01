#!/usr/bin/env python3
"""
extract.py — pull structured, paragraph-level text out of docx/pdf files.

Usage:
    python3 extract.py --files v1.docx,v2.docx,v3.pdf --out /tmp/redline-extract.json [--cache-dir ~/.redline/cache]

Output JSON shape:
{
  "files": [
    {
      "path": "v1.docx",
      "format": "docx",
      "scanned": false,
      "error": null,
      "paragraphs": [
        {"index": 0, "type": "paragraph", "text": "...", "style": "Heading1"},
        {"index": 1, "type": "table_cell", "text": "...", "table": 0, "row": 0, "col": 0}
      ]
    },
    ...
  ]
}

Extraction results are cached on disk keyed by (absolute path, mtime, size) so a file
reused across multiple pairwise comparisons (e.g. v2 in both v1->v2 and v2->v3) is only
ever parsed once per run of the skill.
"""
import argparse
import hashlib
import json
import os
import sys


def cache_key(path):
    st = os.stat(path)
    raw = f"{os.path.abspath(path)}::{st.st_mtime_ns}::{st.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache(cache_dir, key):
    cache_file = os.path.join(cache_dir, f"{key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_cache(cache_dir, key, data):
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{key}.json")
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass  # caching is a perf optimization, never fatal


def extract_docx(path):
    from docx import Document

    doc = Document(path)
    paragraphs = []
    idx = 0

    # Walk the document body in order so paragraphs and tables interleave correctly.
    body = doc.element.body
    from docx.oxml.ns import qn

    def para_text(p_elem):
        from docx.text.paragraph import Paragraph
        return Paragraph(p_elem, doc).text

    def style_name(p_elem):
        from docx.text.paragraph import Paragraph
        p = Paragraph(p_elem, doc)
        try:
            return p.style.name
        except Exception:
            return None

    table_counter = 0
    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            text = para_text(child)
            if text.strip() == "":
                continue
            paragraphs.append({
                "index": idx,
                "type": "paragraph",
                "text": text,
                "style": style_name(child),
            })
            idx += 1
        elif tag == qn("w:tbl"):
            from docx.table import Table
            table = Table(child, doc)
            for r, row in enumerate(table.rows):
                for c, cell in enumerate(row.cells):
                    cell_text = cell.text
                    if cell_text.strip() == "":
                        continue
                    paragraphs.append({
                        "index": idx,
                        "type": "table_cell",
                        "text": cell_text,
                        "table": table_counter,
                        "row": r,
                        "col": c,
                    })
                    idx += 1
            table_counter += 1

    return {"paragraphs": paragraphs, "scanned": False, "error": None}


def extract_pdf(path):
    import pdfplumber

    paragraphs = []
    idx = 0
    total_chars = 0

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            total_chars += len(text.strip())
            if not text.strip():
                continue
            # Split on blank lines as a paragraph heuristic.
            blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
            if len(blocks) <= 1:
                # No double-newlines found (common in pdfplumber output) — fall back
                # to single-newline splitting, but keep short wrapped lines merged.
                blocks = []
                current = []
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        if current:
                            blocks.append(" ".join(current))
                            current = []
                        continue
                    current.append(line)
                if current:
                    blocks.append(" ".join(current))

            for block in blocks:
                paragraphs.append({
                    "index": idx,
                    "type": "paragraph",
                    "text": block,
                    "style": None,
                    "page": page_num + 1,
                })
                idx += 1

            # Extract tables per page too.
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []
            for t_i, table in enumerate(tables):
                for r, row in enumerate(table):
                    for c, cell_text in enumerate(row):
                        cell_text = (cell_text or "").strip()
                        if not cell_text:
                            continue
                        paragraphs.append({
                            "index": idx,
                            "type": "table_cell",
                            "text": cell_text,
                            "table": t_i,
                            "row": r,
                            "col": c,
                            "page": page_num + 1,
                        })
                        idx += 1

    scanned = total_chars == 0
    return {"paragraphs": paragraphs, "scanned": scanned, "error": None}


def extract_one(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            result = extract_docx(path)
            result["format"] = "docx"
        elif ext == ".pdf":
            result = extract_pdf(path)
            result["format"] = "pdf"
        else:
            return {
                "path": path, "format": ext.lstrip("."), "scanned": False,
                "error": f"Unsupported file type: {ext}", "paragraphs": [],
            }
    except Exception as e:
        return {
            "path": path, "format": ext.lstrip("."), "scanned": False,
            "error": f"Extraction failed: {e}", "paragraphs": [],
        }

    result["path"] = path
    return result


def main():
    parser = argparse.ArgumentParser(description="Extract structured text from docx/pdf files.")
    parser.add_argument("--files", required=True, help="Comma-separated list of file paths, in version order.")
    parser.add_argument("--out", required=True, help="Path to write the extraction JSON.")
    parser.add_argument("--cache-dir", default=os.path.expanduser("~/.redline/cache"),
                         help="Directory for per-file extraction cache.")
    parser.add_argument("--no-cache", action="store_true", help="Skip the cache entirely.")
    args = parser.parse_args()

    file_list = [f.strip() for f in args.files.split(",") if f.strip()]
    if not file_list:
        print("No files provided.", file=sys.stderr)
        sys.exit(1)

    results = []
    for path in file_list:
        if not os.path.exists(path):
            results.append({
                "path": path, "format": None, "scanned": False,
                "error": "File not found", "paragraphs": [],
            })
            continue

        key = None if args.no_cache else cache_key(path)
        cached = None if args.no_cache else load_cache(args.cache_dir, key)
        if cached is not None:
            results.append(cached)
            continue

        result = extract_one(path)
        results.append(result)
        if not args.no_cache and result.get("error") is None:
            save_cache(args.cache_dir, key, result)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"files": results}, f, indent=2)

    scanned = [r["path"] for r in results if r.get("scanned")]
    errors = [(r["path"], r["error"]) for r in results if r.get("error")]
    if scanned:
        print(f"WARNING: no extractable text (likely scanned) in: {', '.join(scanned)}", file=sys.stderr)
    if errors:
        for path, err in errors:
            print(f"ERROR extracting {path}: {err}", file=sys.stderr)

    print(f"Extracted {len(results)} file(s) -> {args.out}")


if __name__ == "__main__":
    main()

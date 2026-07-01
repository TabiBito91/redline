#!/usr/bin/env python3
"""
diff_engine.py — word-level diff between extracted documents.

Usage:
    python3 diff_engine.py --extracted /tmp/redline-extract.json --mode sequential --out /tmp/redline-diffs.json
    python3 diff_engine.py --extracted /tmp/redline-extract.json --mode baseline --out /tmp/redline-diffs.json

Modes:
    sequential (default) — diffs v1->v2, v2->v3, v3->v4, ...
    baseline             — diffs v1->v2, v1->v3, v1->v4, ...

Output JSON shape:
{
  "pairs": [
    {
      "pair_id": "v1_v2",
      "original": "v1.docx",
      "revised": "v2.docx",
      "insertions": 12,
      "deletions": 5,
      "changed_paragraphs": 3,
      "unchanged_paragraphs": 20,
      "paragraphs": [
        {
          "status": "changed" | "unchanged" | "added" | "deleted",
          "original_index": 0,
          "revised_index": 0,
          "ops": [{"type": "equal"|"insert"|"delete", "text": "..."}]
        }
      ]
    }
  ]
}
"""
import argparse
import difflib
import json
import os
import re
import sys


WORD_RE = re.compile(r"\S+|\s+")


def tokenize(text):
    """Split into words + whitespace runs so reconstructed text is exact."""
    return WORD_RE.findall(text)


def word_diff(a_text, b_text):
    """Word-level diff between two paragraph strings. Returns list of ops and counts."""
    a_tokens = tokenize(a_text)
    b_tokens = tokenize(b_text)
    sm = difflib.SequenceMatcher(a=a_tokens, b=b_tokens, autojunk=False)
    ops = []
    insertions = 0
    deletions = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append({"type": "equal", "text": "".join(a_tokens[i1:i2])})
        elif tag == "delete":
            seg = "".join(a_tokens[i1:i2])
            ops.append({"type": "delete", "text": seg})
            deletions += len([t for t in a_tokens[i1:i2] if t.strip()])
        elif tag == "insert":
            seg = "".join(b_tokens[j1:j2])
            ops.append({"type": "insert", "text": seg})
            insertions += len([t for t in b_tokens[j1:j2] if t.strip()])
        elif tag == "replace":
            seg_a = "".join(a_tokens[i1:i2])
            seg_b = "".join(b_tokens[j1:j2])
            ops.append({"type": "delete", "text": seg_a})
            ops.append({"type": "insert", "text": seg_b})
            deletions += len([t for t in a_tokens[i1:i2] if t.strip()])
            insertions += len([t for t in b_tokens[j1:j2] if t.strip()])
    return ops, insertions, deletions


def diff_pair(original_doc, revised_doc):
    """Paragraph-level alignment first (to catch whole added/removed paragraphs),
    then word-level diff within matched paragraphs."""
    orig_paras = original_doc.get("paragraphs", [])
    rev_paras = revised_doc.get("paragraphs", [])

    orig_texts = [p["text"] for p in orig_paras]
    rev_texts = [p["text"] for p in rev_paras]

    sm = difflib.SequenceMatcher(a=orig_texts, b=rev_texts, autojunk=False)

    result_paragraphs = []
    total_insertions = 0
    total_deletions = 0
    changed_count = 0
    unchanged_count = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                oi, ri = i1 + offset, j1 + offset
                result_paragraphs.append({
                    "status": "unchanged",
                    "original_index": orig_paras[oi]["index"],
                    "revised_index": rev_paras[ri]["index"],
                    "ops": [{"type": "equal", "text": orig_texts[oi]}],
                })
                unchanged_count += 1
        elif tag == "delete":
            for oi in range(i1, i2):
                result_paragraphs.append({
                    "status": "deleted",
                    "original_index": orig_paras[oi]["index"],
                    "revised_index": None,
                    "ops": [{"type": "delete", "text": orig_texts[oi]}],
                })
                total_deletions += len([t for t in tokenize(orig_texts[oi]) if t.strip()])
                changed_count += 1
        elif tag == "insert":
            for ri in range(j1, j2):
                result_paragraphs.append({
                    "status": "added",
                    "original_index": None,
                    "revised_index": rev_paras[ri]["index"],
                    "ops": [{"type": "insert", "text": rev_texts[ri]}],
                })
                total_insertions += len([t for t in tokenize(rev_texts[ri]) if t.strip()])
                changed_count += 1
        elif tag == "replace":
            # Positional pairing (oi+k <-> ri+k) is naive: if a paragraph was deleted
            # and an unrelated one nearby was edited, blind position-zipping pairs the
            # wrong two paragraphs together and produces a confusing word-diff. Instead,
            # only pair two paragraphs as "changed" if they're actually similar; anything
            # left over is a clean delete or insert.
            import difflib as _difflib

            orig_range = list(range(i1, i2))
            rev_range = list(range(j1, j2))
            SIMILARITY_THRESHOLD = 0.4

            candidates = []
            for oi in orig_range:
                for ri in rev_range:
                    ratio = _difflib.SequenceMatcher(None, orig_texts[oi], rev_texts[ri], autojunk=False).ratio()
                    if ratio >= SIMILARITY_THRESHOLD:
                        candidates.append((ratio, oi, ri))
            candidates.sort(reverse=True)

            matched_orig, matched_rev = set(), set()
            pairs_matched = []
            for ratio, oi, ri in candidates:
                if oi in matched_orig or ri in matched_rev:
                    continue
                matched_orig.add(oi)
                matched_rev.add(ri)
                pairs_matched.append((oi, ri))

            for oi, ri in sorted(pairs_matched):
                ops, ins, dels = word_diff(orig_texts[oi], rev_texts[ri])
                result_paragraphs.append({
                    "status": "changed",
                    "original_index": orig_paras[oi]["index"],
                    "revised_index": rev_paras[ri]["index"],
                    "ops": ops,
                })
                total_insertions += ins
                total_deletions += dels
                changed_count += 1

            for oi in orig_range:
                if oi not in matched_orig:
                    result_paragraphs.append({
                        "status": "deleted",
                        "original_index": orig_paras[oi]["index"],
                        "revised_index": None,
                        "ops": [{"type": "delete", "text": orig_texts[oi]}],
                    })
                    total_deletions += len([t for t in tokenize(orig_texts[oi]) if t.strip()])
                    changed_count += 1

            for ri in rev_range:
                if ri not in matched_rev:
                    result_paragraphs.append({
                        "status": "added",
                        "original_index": None,
                        "revised_index": rev_paras[ri]["index"],
                        "ops": [{"type": "insert", "text": rev_texts[ri]}],
                    })
                    total_insertions += len([t for t in tokenize(rev_texts[ri]) if t.strip()])
                    changed_count += 1

    return {
        "insertions": total_insertions,
        "deletions": total_deletions,
        "changed_paragraphs": changed_count,
        "unchanged_paragraphs": unchanged_count,
        "paragraphs": result_paragraphs,
    }


def build_pairs(files, mode):
    if mode == "baseline":
        return [(0, i) for i in range(1, len(files))]
    # sequential
    return [(i, i + 1) for i in range(len(files) - 1)]


def label(path):
    return os.path.splitext(os.path.basename(path))[0]


def main():
    parser = argparse.ArgumentParser(description="Word-level diff between extracted documents.")
    parser.add_argument("--extracted", required=True, help="Path to extract.py's output JSON.")
    parser.add_argument("--mode", choices=["sequential", "baseline"], default="sequential")
    parser.add_argument("--out", required=True, help="Path to write the diff JSON.")
    args = parser.parse_args()

    with open(args.extracted, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    files = extracted["files"]
    if len(files) < 2:
        print("Need at least 2 files to diff.", file=sys.stderr)
        sys.exit(1)

    usable = [f for f in files if not f.get("error") and not f.get("scanned")]
    if len(usable) < 2:
        broken = [f["path"] for f in files if f.get("error") or f.get("scanned")]
        print(f"Not enough usable documents to diff (unreadable/scanned: {broken}).", file=sys.stderr)
        sys.exit(1)

    pairs_idx = build_pairs(files, args.mode)
    pairs_out = []

    for oi, ri in pairs_idx:
        orig, rev = files[oi], files[ri]
        if orig.get("error") or orig.get("scanned") or rev.get("error") or rev.get("scanned"):
            pairs_out.append({
                "pair_id": f"{label(orig['path'])}_{label(rev['path'])}",
                "original": orig["path"],
                "revised": rev["path"],
                "skipped": True,
                "reason": orig.get("error") or rev.get("error") or "scanned/unreadable document",
            })
            continue

        diff_result = diff_pair(orig, rev)
        pairs_out.append({
            "pair_id": f"{label(orig['path'])}_{label(rev['path'])}",
            "original": orig["path"],
            "revised": rev["path"],
            "skipped": False,
            **diff_result,
        })

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"mode": args.mode, "pairs": pairs_out}, f, indent=2)

    for p in pairs_out:
        if p.get("skipped"):
            print(f"{p['pair_id']}: SKIPPED ({p['reason']})")
        elif p["insertions"] == 0 and p["deletions"] == 0:
            print(f"{p['pair_id']}: no changes")
        else:
            print(f"{p['pair_id']}: +{p['insertions']} / -{p['deletions']} across {p['changed_paragraphs']} paragraph(s)")

    print(f"Diff written -> {args.out}")


if __name__ == "__main__":
    main()

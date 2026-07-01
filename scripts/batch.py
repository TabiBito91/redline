#!/usr/bin/env python3
"""
batch.py — resolve a folder or glob into an ordered list of version files.

Usage:
    python3 batch.py --input "contracts/*.docx" --out /tmp/redline-files.json
    python3 batch.py --folder contracts/ --out /tmp/redline-files.json

Tries to sort files into version order using, in priority:
  1. An explicit version number in the filename (v1, v2, version_3, ...)
  2. A date in the filename (2026-01-15, 2026_01_15, Jan-15-2026, ...)
  3. File modification time (fallback — flagged as "ambiguous" so the caller can confirm)

Output JSON:
{
  "files": ["contracts/v1.docx", "contracts/v2.docx", ...],
  "ambiguous": false,
  "reason": null
}
"""
import argparse
import glob
import json
import os
import re
import sys


VERSION_RE = re.compile(r"[vV]ersion[_\-\s]?(\d+)|[vV](\d+)\b")
DATE_RE = re.compile(
    r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})|"          # 2026-01-15 / 20260115
    r"(\d{2})[-_](\d{2})[-_](\d{4})"             # 01-15-2026
)


def extract_version_number(filename):
    m = VERSION_RE.search(filename)
    if m:
        num = m.group(1) or m.group(2)
        return int(num)
    return None


def extract_date_key(filename):
    m = DATE_RE.search(filename)
    if not m:
        return None
    if m.group(1):
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (int(m.group(6)), int(m.group(4)), int(m.group(5)))


def resolve_files(input_pattern=None, folder=None):
    if input_pattern:
        files = glob.glob(input_pattern)
    elif folder:
        files = [
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in (".docx", ".pdf")
        ]
    else:
        raise ValueError("Provide either --input (glob) or --folder.")
    return [f for f in files if os.path.isfile(f)]


def sort_files(files):
    """Returns (sorted_files, ambiguous, reason)."""
    with_version = [(f, extract_version_number(os.path.basename(f))) for f in files]
    if all(v is not None for _, v in with_version):
        sorted_files = [f for f, v in sorted(with_version, key=lambda x: x[1])]
        return sorted_files, False, None

    with_date = [(f, extract_date_key(os.path.basename(f))) for f in files]
    if all(d is not None for _, d in with_date):
        sorted_files = [f for f, d in sorted(with_date, key=lambda x: x[1])]
        return sorted_files, False, None

    # Fallback: modification time. Flag as ambiguous — ask the caller to confirm order
    # rather than silently trusting mtimes, which are easy to get wrong (e.g. after a
    # git clone or file copy that resets timestamps).
    sorted_files = sorted(files, key=lambda f: os.path.getmtime(f))
    return sorted_files, True, (
        "No clear version number or date found in filenames; fell back to file "
        "modification time. Confirm this order is correct before treating it as ground truth."
    )


def main():
    parser = argparse.ArgumentParser(description="Resolve and order a set of version files.")
    parser.add_argument("--input", help="Glob pattern, e.g. 'contracts/*.docx'.")
    parser.add_argument("--folder", help="Folder to scan for .docx/.pdf files.")
    parser.add_argument("--out", required=True, help="Path to write the resolved file list JSON.")
    args = parser.parse_args()

    if not args.input and not args.folder:
        print("Provide either --input (glob) or --folder.", file=sys.stderr)
        sys.exit(1)

    files = resolve_files(args.input, args.folder)
    if not files:
        print("No matching .docx/.pdf files found.", file=sys.stderr)
        sys.exit(1)

    sorted_files, ambiguous, reason = sort_files(files)

    result = {"files": sorted_files, "ambiguous": ambiguous, "reason": reason}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Resolved {len(sorted_files)} file(s) -> {args.out}")
    for f in sorted_files:
        print(f"  {f}")
    if ambiguous:
        print(f"WARNING: {reason}", file=sys.stderr)


if __name__ == "__main__":
    main()

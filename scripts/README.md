# redline/scripts

The deterministic backbone of the `redline` skill. `.claude/commands/redline.md` orchestrates these —
this file is here so a human (or another agent) can understand, run, or debug them
directly without reading the skill definition first.

## How It Works

1. **`extract.py`** pulls structured, paragraph-level text out of each docx/pdf,
   caching per file so a version reused across multiple comparisons (e.g. v2 in both
   v1→v2 and v2→v3) is only parsed once.
2. **`diff_engine.py`** takes that extracted text and produces a word-level diff for
   each version pair — either sequential (v1→v2→v3) or baseline (v1→v2, v1→v3, ...).
3. **`render_docx.py`** / **`render_html.py`** / **`render_dashboard.py`** turn a diff
   into human-readable output: a marked-up Word doc, a single-pair HTML visual diff,
   or a combined multi-version dashboard.
4. **`batch.py`** resolves a folder or glob into an ordered, version-sorted file list
   so you don't have to name every file individually.
5. **`deliver.py`** optionally sends the summary and output files to Telegram or email.

Nothing here calls out to any network service except `deliver.py`, and only when
explicitly invoked with `--method telegram` or `--method email`.

## Script Reference

### `extract.py`
```
python3 extract.py --files v1.docx,v2.docx,v3.pdf --out /tmp/redline-extract.json [--cache-dir ~/.redline/cache] [--no-cache]
```
Outputs `{"files": [{"path", "format", "scanned", "error", "paragraphs": [...]}]}`.
Flags PDFs with no extractable text as `"scanned": true` — that means OCR would be
needed; the pipeline should not guess at scanned content.

### `diff_engine.py`
```
python3 diff_engine.py --extracted /tmp/redline-extract.json --mode sequential|baseline --out /tmp/redline-diffs.json
```
Outputs `{"mode", "pairs": [{"pair_id", "original", "revised", "insertions", "deletions", "changed_paragraphs", "unchanged_paragraphs", "paragraphs": [...]}]}`.
Paragraph-level alignment runs first (so whole added/deleted paragraphs are caught
cleanly, without getting force-paired against an unrelated nearby paragraph), then a
word-level diff runs within each matched pair. See `examples/expected_diff_summary.md`
for a worked example of why this matters.

### `render_docx.py`
```
python3 render_docx.py --diffs /tmp/redline-diffs.json --pair v1_v2 --out ./redline-output/
```
Deletions: red strikethrough. Insertions: green underline. This is styled-run output,
not native Word Track Changes XML (that's a stretch goal — see the PRD).

### `render_html.py`
```
python3 render_html.py --diffs /tmp/redline-diffs.json --pair v1_v2 --out ./redline-output/
```
One self-contained HTML file per pair, inline CSS, no external dependencies.

### `render_dashboard.py`
```
python3 render_dashboard.py --diffs /tmp/redline-diffs.json --out ./redline-output/
```
Only useful (and only needs to run) when there's more than one pair. One HTML file
with tab navigation between pairs and a summary table.

### `batch.py`
```
python3 batch.py --input "contracts/*.docx" --out /tmp/redline-files.json
python3 batch.py --folder contracts/ --out /tmp/redline-files.json
```
Sorts by version number in the filename first, then by date, then falls back to
modification time — flagging `"ambiguous": true` in that last case so the caller
knows to confirm the order rather than trust it blindly.

### `deliver.py`
```
python3 deliver.py --method telegram --files a.html,b.docx --summary "..." [--chat-id 123456]
python3 deliver.py --method email --to user@example.com --files a.html,b.docx --summary "..."
```
Reads `TELEGRAM_BOT_TOKEN` / `RESEND_API_KEY` from `~/.redline/.env`. Exits non-zero
with a clear message if the required key is missing — callers should treat that as
"delivery failed, fall back to reporting local file paths," not as a silent no-op.

## Requirements

```
pip install python-docx pdfplumber requests --break-system-packages
```

No API keys are needed for extraction, diffing, or rendering. `deliver.py` is the only
script that needs a key, and only for the delivery method you actually use.

## Testing Changes

`tests/` has a small synthetic three-version contract (`sample_v1.docx` →
`sample_v2.docx` → `sample_v3.docx`) with known, deliberate changes at each step, plus
`expected_diff_summary.md` describing what a correct diff should look like. After
changing any script here, re-run the pipeline against these fixtures and check the
output against that file before trusting it on a real document:

```
python3 extract.py --files tests/sample_v1.docx,tests/sample_v2.docx,tests/sample_v3.docx --out /tmp/e.json --no-cache
python3 diff_engine.py --extracted /tmp/e.json --mode sequential --out /tmp/d.json
python3 render_html.py --diffs /tmp/d.json --pair sample_v1_sample_v2 --out /tmp/out/
python3 render_dashboard.py --diffs /tmp/d.json --out /tmp/out/
```

## Privacy

- Extraction, diffing, and rendering are 100% local — no network calls, no API keys.
- `deliver.py` only sends data over the network when explicitly invoked, and only to
  the Telegram Bot API or Resend, using a key you provide yourself.
- Telegram/email keys are stored locally in `~/.redline/.env` and never bundled into
  output files or committed anywhere by these scripts.

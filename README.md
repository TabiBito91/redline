# redline

A Claude Code skill that compares two or more versions of a document and produces tracked-changes output — a marked-up Word doc and a visual HTML diff — so you can see exactly what changed without manually hunting through drafts.

Handles everything from a single v1-vs-v2 comparison up to a full version chain (v1 → v2 → ... → vN) without running it once per pair.

## What it does

- **Redlined Word doc** (`.docx`): deletions in red strikethrough, insertions in blue underline
- **HTML visual diff**: same markup, self-contained file that opens in any browser — no external dependencies
- **Multi-version dashboard**: when comparing 3+ versions, one combined HTML file with tab navigation and a summary table across all transitions
- **Plain-language summary**: which transitions had the most change, what kind of change, and anything worth flagging
- **Optional delivery**: send output files to Telegram or email instead of (or in addition to) local files

## Installation

```bash
git clone https://github.com/TabiBito91/redline.git
cd redline
pip install python-docx pdfplumber requests
```

The `/redline` skill is available immediately in Claude Code once you're inside this directory — no further setup needed for local file output.

## Usage

Invoke via Claude Code:

```
/redline contract_v1.docx contract_v2.docx
```

```
/redline contracts/v1.docx contracts/v2.docx contracts/v3.docx
```

```
/redline contracts/
```

Or just hand Claude two or more versions of a document and ask "what changed" — the skill triggers automatically.

**Comparison modes:**
- **Sequential** (default): v1→v2, v2→v3, v3→v4 — shows incremental change at each step
- **Baseline**: v1→v2, v1→v3, v1→v4 — shows cumulative drift from the original

The skill infers the right mode from how you phrase the request, or asks if it's ambiguous.

## Output

All output files land in a `redline-output/` folder in your working directory:

```
redline-output/
  contract_v1_vs_v2_redline.docx
  contract_v1_vs_v2_redline.html
  contract_v2_vs_v3_redline.docx
  contract_v2_vs_v3_redline.html
  dashboard.html                    ← multi-version only
```

## Supported formats

| Format | Input | Notes |
|--------|-------|-------|
| `.docx` | ✅ | Full paragraph and run-level structure |
| `.pdf` | ✅ | Text-based PDFs; scanned/image-only PDFs require OCR |
| Mixed | ✅ | e.g. original as PDF, revision as DOCX |

## Optional: Telegram or email delivery

On first run the skill asks where you'd like output delivered. Local files is the default and needs nothing extra. To enable Telegram or email, follow the prompts — you'll need a Telegram bot token or a [Resend](https://resend.com) API key. Preferences are saved to `~/.redline/config.json` so you're only asked once.

## Repo structure

```
.claude/commands/redline.md   ← skill definition (Claude Code reads this)
scripts/                       ← deterministic pipeline scripts
  extract.py                    text extraction from docx/pdf
  diff_engine.py                word-level diff logic
  render_docx.py                marked-up Word output
  render_html.py                HTML visual diff (single pair)
  render_dashboard.py           combined multi-version HTML dashboard
  batch.py                      resolve folders/globs into ordered file sets
  deliver.py                    Telegram / email delivery
  tests/                        synthetic 3-version contract for testing
reference/
  redline-skill-PRD.md          original product requirements
```

## Privacy

Extraction, diffing, and rendering run entirely locally — no network calls, no API keys required. `deliver.py` is the only script that touches the network, and only when explicitly invoked with a delivery method you opted into.

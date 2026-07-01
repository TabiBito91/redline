# PRD / Build Prompt: Document Redline Skill for Claude Code

## Prompt to give Claude Code

> Build a Claude Code skill called `redline` that compares two or more versions of a document (Word `.docx` or PDF) — anywhere from 2 to dozens of versions — and produces marked-up "redline" output showing additions, deletions, and moved text, plus an easy-to-read HTML visual diff. It should scale gracefully from a single v1-vs-v2 comparison up to a full version chain (v1→v2→v3→...→vN) without the user having to run it repeatedly by hand. Follow the spec below.

---

## 1. Goal

Let a user hand Claude Code two (or more) versions of a document — contracts, policies, drafts, whatever — and get back:
1. A **redlined document** (Word with tracked changes, or an annotated PDF) they can share with colleagues who expect a familiar "legal redline" look.
2. An **HTML visual diff** that's easier to skim than raw tracked changes: color-coded additions/deletions, clean typography, optionally side-by-side.

## 2. Users & Workflow

**User:** someone reviewing contract revisions, policy updates, or draft edits — wants to quickly see what changed across versions without manually comparing.

**Workflow:**
1. User provides an original file plus one or more revised files (docx and/or pdf, mixed formats OK) — this could be a single revision or a whole chain of versions (v1 through v12, say).
2. User (implicitly or explicitly) picks a comparison mode — see 3.5 below.
3. Claude Code runs the skill, which:
   - Extracts text (and structure where possible) from each doc.
   - Computes a diff for every pair required by the chosen mode.
   - Produces a marked-up Word doc (or PDF) per comparison, with insertions/deletions visually indicated.
   - Produces both per-comparison HTML redlines and one combined HTML "dashboard" summarizing all comparisons together.
4. User gets all outputs plus a plain-language summary (e.g., "v3 introduced the biggest change: a new indemnification clause").

## 3. Core Capabilities

### 3.1 Document ingestion
- **DOCX**: read paragraph/run-level text via `python-docx`, preserving paragraph structure (and ideally headings/lists).
- **PDF**: extract text via `pdfplumber` or `PyMuPDF` (fitz). Note in the output if the PDF is scanned/image-only (no extractable text) and flag that OCR would be needed — don't silently produce garbage output.
- Support comparing across formats (e.g., original as PDF, revision as DOCX).

### 3.2 Diff engine
- Use a word-level (not just line-level) diff — `difflib.SequenceMatcher` on tokenized words is a reasonable baseline; consider `diff-match-patch` for cleaner results on prose.
- Classify changes as insertions, deletions, and (nice-to-have) moved blocks.
- Operate per-paragraph so structure isn't lost, rather than diffing the whole document as one blob.

### 3.3 Marked-up document output
- **DOCX output**: generate a new `.docx` with actual Word tracked-change formatting where feasible, or at minimum strikethrough (deletions, red) + underline (insertions, colored) formatting via `python-docx` run-level styling. State clearly in the skill which approach was implemented, since true "Track Changes" XML is more complex than styled runs.
- **PDF output**: since PDFs aren't natively editable, render redlines as: annotated overlay (strikethrough/highlight using `PyMuPDF` or `reportlab`) or generate a fresh PDF from the redlined HTML/text.

### 3.4 HTML visual diff (the "nice to look at" version)
- Single self-contained HTML file (inline CSS, no external deps) so it can be opened directly in a browser or shared as one file.
- Deletions: red strikethrough. Insertions: green underline/highlight. Unchanged text: normal.
- Include a simple header with filenames being compared and a change summary (e.g., "42 insertions, 17 deletions across 6 paragraphs").
- Stretch: toggle between "inline diff" and "side-by-side" view with a button (plain JS, no frameworks needed).
- **When comparing more than two versions**: also generate one combined dashboard HTML file with a simple nav (tabs, or a dropdown/sidebar) to jump between each version-pair's redline, plus a top-level summary table (version, insertions, deletions, changed sections) so the user isn't stuck opening a dozen separate files to get the overview.

### 3.5 Multi-version comparison (handling many redlines at once)
This is the core new requirement: the skill should handle a large set of versions (v1, v2, v3, ... vN) without the user manually invoking it N times.

- **Comparison modes** (skill should infer the right one from context, or ask if ambiguous):
  - **Sequential ("chain")**: v1→v2, v2→v3, v3→v4, ... — shows incremental change at each step. Default mode when the user says something like "compare v1 through v5."
  - **Baseline**: v1→v2, v1→v3, v1→v4, ... — shows cumulative drift from the original. Useful when v1 is a template/master and the rest are derivatives.
  - **Single pair**: just two files — the original v1 behavior, still fully supported.
  - Let the user's phrasing pick the mode ("what changed at each revision" → sequential; "how far has this drifted from the original" → baseline), and default to sequential if unclear.
- **Batch processing**: accept a folder or glob of files (e.g., `contracts/v*.docx`) rather than requiring every filename spelled out individually. Sort naturally by version number/date in filename, don't rely on OS file-listing order.
- **Performance at scale**: cache extracted text per document (don't re-parse the same file across multiple pairwise diffs), and process comparisons in a simple loop rather than holding every document's full diff in memory at once if the set is large.
- **Combined summary output**: in addition to individual per-pair redlines, produce one rollup — either a combined HTML dashboard (see 3.4) or a short table/markdown summary — showing, per version transition: number of insertions/deletions, which sections changed, and a one-line description of the most significant change. This is what makes a large version set actually usable instead of dumping N separate files on the user.
- **Naming convention for outputs**: `{basename}_v1_vs_v2_redline.{docx,html}`, `{basename}_v2_vs_v3_redline.{docx,html}`, etc., all written to a single output folder per run so they're easy to find together.

### 3.6 Delivery (optional)
- Default delivery is local: output files stay on disk, paths reported in chat/terminal.
- Optionally support sending the summary + output files via **Telegram** (Bot API `sendDocument`/`sendMessage`) or **email** (Resend API with base64 attachments).
- Only prompt for API keys when the user actually asks for Telegram/email delivery — local-only usage needs zero setup.
- Store delivery preference (method, chat ID or email address) in a small local config file so it doesn't need to be re-asked every run.
- If delivery fails (missing key, network issue), fall back to reporting local file paths rather than losing the output.

## 4. Skill File Structure

```
redline/
  SKILL.md              # skill description, triggers, usage instructions
  scripts/
    extract.py           # docx/pdf -> structured text (with caching per file)
    diff_engine.py        # word-level diff logic
    render_docx.py         # build marked-up docx
    render_html.py          # build HTML visual diff (single pair)
    render_dashboard.py      # build combined multi-version HTML dashboard + summary table
    render_pdf.py             # (optional) build annotated pdf
    batch.py                   # resolve file sets (folder/glob), determine comparison mode, orchestrate runs
    deliver.py                   # send summary + output files via Telegram or email
  reference/
    example_output.html       # sample so Claude Code has a style target
```

`SKILL.md` should describe:
- When to trigger (user mentions "redline," "compare documents," "track changes," "show me what changed," or uploads 2+ versions of a doc).
- Required inputs (original + revision path(s)).
- Expected outputs and where they're written.
- Any known limitations (e.g., scanned PDFs, complex tables, images not diffed).

## 5. Example Invocations

**Single pair:**
> "Compare `contract_v1.docx` and `contract_v2.docx` and show me a redline."

Returns `contract_v1_vs_v2_redline.docx` and `.html`, with a short summary of what changed.

**Multi-version chain:**
> "Compare v1 through v6 of this contract and show me what changed at each step."

Expected behavior: skill resolves all six files (by folder or explicit list), runs sequential mode (v1→v2, v2→v3, ... v5→v6), and returns:
- One redline docx + html per version transition (5 pairs)
- One combined dashboard HTML with navigation between transitions and a summary table
- A short natural-language summary in chat, e.g., "Most changes happened between v3 and v4 (a new termination clause was added); v5→v6 was minor wording only."

**Baseline drift:**
> "How much has v8 drifted from the original template?"

Expected behavior: skill runs baseline mode (v1→v8 directly, or v1→v2...v1→v8 if multiple intermediate versions are relevant) and reports cumulative drift.

## 6. Edge Cases to Handle

- Documents with tables — diff cell-by-cell rather than failing or ignoring tables entirely.
- Scanned/image-only PDFs — detect and clearly tell the user OCR is needed rather than returning an empty diff.
- Ambiguous version ordering — if filenames don't sort cleanly (no clear v1/v2/v3 pattern or dates), ask the user for the intended order rather than guessing.
- A version renumbering gap (e.g., v3 is missing from the folder) — proceed with the versions present and note the gap in the summary, don't error out.
- Very large documents or long version chains (10+ versions) — chunk/cache processing so it doesn't choke on 100+ page contracts or dozens of pairwise diffs; avoid redundant re-extraction of the same file.
- Identical documents — should cleanly report "no changes" for that pair rather than erroring, and continue processing the rest of the chain.
- Delivery failure (missing/invalid Telegram token or Resend key, network issue) — fall back to reporting local file paths rather than losing the output silently.

## 7. Success Criteria

- Given two versions of a real-world contract, the skill correctly identifies word-level insertions/deletions with no missed paragraphs.
- Given a chain of 6+ versions, the skill produces correct pairwise redlines for every transition and a working combined dashboard, without requiring the user to invoke it once per pair.
- The DOCX output opens cleanly in Word and visually reads as a redline.
- The HTML output (both single-pair and dashboard) opens in a browser with no missing styles/broken layout, no external network calls.
- Skill handles a docx-vs-pdf comparison without erroring.
- When delivery is set to Telegram or email, the summary and output files actually arrive in the target chat/inbox; local-only usage never prompts for a key.

## 8. Stretch Goals (not required for v1)

- True Word "Track Changes" XML (so Word's built-in accept/reject-changes UI works, not just static styling).
- Side-by-side HTML view toggle.
- Change summary stats (word count changed, % modified) per transition, aggregated across the whole chain.
- Visual "heat map" of which document sections changed most across the full version history.

---

**Suggested libraries:** `python-docx`, `pdfplumber` or `PyMuPDF`, `diff-match-patch` (or `difflib`), no heavy frameworks needed for HTML (vanilla CSS/JS is fine and keeps output self-contained).

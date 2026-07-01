# Expected Diff Summary — sample_v1 → sample_v2 → sample_v3

These three files are a synthetic three-clause service agreement with deliberate,
known changes at each step. Use them to sanity-check the scripts after any change:
run `extract.py` → `diff_engine.py` → `render_docx.py`/`render_html.py` and confirm
the output roughly matches what's described below before trusting the pipeline on a
real document.

## v1 → v2

- **Changed**: payment amount, `$5,000.` → `$6,500.`
- **Added**: a new indemnification clause (Contractor indemnifies Acme Corp against
  claims from negligence)
- **Changed**: table cell, milestone due date `March 2026` → `April 2026`
- Expected: ~2 changed paragraphs, 1 added paragraph, 1 changed table cell, 0 deletions
  of whole paragraphs.

## v2 → v3

- **Changed**: consulting period, `twelve months` → `eighteen months`
- **Changed**: indemnification clause extended to add `or willful misconduct`
- **Deleted**: the termination clause (`Either party may terminate this Agreement
  with 30 days written notice.`) — this is the important one to check: the deleted
  termination clause should **not** get paired up with the edited indemnification
  clause as a false "changed" pair. If you see the termination clause's text mixed
  into a word-diff with indemnification wording, the paragraph-alignment logic in
  `diff_engine.py` has regressed — it should recognize these as two unrelated
  paragraphs (one deleted, one edited) rather than force-pairing them by position.
- Expected: 2 changed paragraphs, 1 deleted paragraph, 0 added paragraphs.

## What "good" output looks like

- `render_docx.py` output should show deletions in red strikethrough and insertions
  in green underline, with unchanged text left plain.
- `render_html.py` output should visually separate `deleted`, `added`, and `changed`
  paragraphs (see the CSS classes), with word-level `<ins>`/`<del>` spans inside
  `changed` paragraphs.
- `render_dashboard.py` should show both pairs as separate tabs with a summary table
  up top showing insertion/deletion counts per pair.

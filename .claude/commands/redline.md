---
name: redline
description: Compares two or more versions of a document (docx or pdf) and produces marked-up redlines plus a clean visual HTML diff — including full version chains (v1 through v10+), not just single pairs. Can also deliver the results by Telegram or email instead of leaving them as local files. Use whenever the user wants to compare document versions, see what changed between drafts/contracts/policies, generate tracked-changes-style output, or invokes "/redline". Also trigger when the user hands over multiple versions of the same document and asks "what changed," "how does this compare," or similar — even without the word "redline." Works with local output only, no setup required; Telegram/email delivery is optional and only needs a key if the user asks for it.
---

# Redline: Compare Document Versions, Not Just List Changes

You are a document comparison assistant. Your job is to turn a set of document versions into a clear, trustworthy account of what changed — grounded entirely in deterministic diff output, never in your own read of the documents.

Philosophy: the diff scripts are the source of truth for *what* changed. Your job is explaining *what it means* — which changes matter, where they cluster, what shifted between versions — not re-deriving the diff by eyeballing text yourself. Two people (or two runs of an LLM) reading the same paragraph can disagree about subtle wording changes; a script comparing tokens cannot.

No API keys or setup are required for the core comparison workflow. Delivery is local (file paths in the terminal) by default; Telegram or email delivery is optional and only needs a key if the user asks for it.

## Anatomy

```
scripts/
  extract.py            docx/pdf -> structured text, cached per file
  diff_engine.py         word-level diff between extracted docs
  render_docx.py          build a marked-up docx (strikethrough/underline)
  render_html.py           build a single-pair HTML visual diff
  render_dashboard.py       build a combined multi-version HTML dashboard
  batch.py                    resolve a folder/glob into an ordered file set
  deliver.py                    send output files via Telegram or email
```

See `scripts/README.md` for what each script does and its exact CLI arguments — the steps below tell you when to call them, that file tells you how.

## Delivery Preferences

Check `~/.redline/config.json` for a saved `delivery` preference. If it doesn't exist yet, the first time this skill runs, ask the user:

"Where would you like the redline output delivered? Local files (I'll just tell you the paths) is the default and needs nothing extra. I can also send the docx/html directly to Telegram or email if you'd prefer."

- **Local** (default): no config needed, skip straight to Step 7 behavior described below.
- **Telegram**: guide the user through the same setup `follow-builders` uses —
  1. Open Telegram, message `@BotFather`, send `/newbot`, choose a name and a username ending in "bot."
  2. BotFather returns a token — save it.
  3. Open a chat with the new bot and send it any message (required so the bot can message back).
  4. Get the chat ID: `curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result'][0]['message']['chat']['id'])"`
  5. Save the token to `.env` (see below) and the chat ID to `config.json`.
- **Email**: ask for the email address, then have the user create a free Resend API key at https://resend.com (Dashboard → API Keys), and save it to `.env`.

If the user chose Telegram or email, create `.env`:

```
mkdir -p ~/.redline
cat > ~/.redline/.env << 'ENVEOF'
# Telegram bot token (only if using Telegram delivery)
# TELEGRAM_BOT_TOKEN=paste_your_token_here

# Resend API key (only if using email delivery)
# RESEND_API_KEY=paste_your_key_here
ENVEOF
```

Uncomment only the line they need and have them paste the key in. Don't ask for a key at all if they chose local delivery — that path needs nothing.

## Language Preference

Check `~/.redline/config.json` for a saved `language` preference. If it doesn't exist yet, ask the user (this can be asked in the same first-run turn as delivery preference, no need for a separate interruption):

"What language would you like your redline summaries in — English, Chinese, or both side by side?"

- **`en`** (default): summary and any chat-facing text in English.
- **`zh`**: summary and chat-facing text in Chinese.
- **`bilingual`**: interleave English and Chinese, same pattern as `follow-builders` — one paragraph in English, the Chinese translation directly below it, then the next paragraph. Don't output all English first and all Chinese after.

This setting only applies to your own commentary — the natural-language summary from Step 6 and anything you say in chat or in a delivered message. It does **not** translate the actual redlined content inside the rendered docx/html outputs; those preserve the original document's language exactly, since translating the tracked changes themselves would misrepresent what the source documents actually say.

Write the choice to `~/.redline/config.json` alongside delivery, so the file ends up looking like:

```json
{
  "language": "en | zh | bilingual",
  "delivery": {
    "method": "local | telegram | email",
    "chatId": "<only if telegram>",
    "email": "<only if email>"
  }
}
```

## Step 1: Resolve the Input Set

Figure out which files are being compared:
- Explicit filenames the user gave you.
- A folder or glob (e.g., "everything in `contracts/`") — run `batch.py` to resolve and naturally sort by version number or modification date. Don't rely on raw OS listing order.
- If the version order isn't obvious from filenames or dates (no clear v1/v2 pattern, no dates), ask the user for the intended order rather than guessing — getting this wrong silently produces a diff that means nothing.

Docx and pdf can be mixed freely in the same set.

## Step 2: Determine Comparison Mode

Two versions is the simple case — just diff them. For three or more, pick a mode:

- **Sequential** (default): v1→v2, v2→v3, v3→v4, ... — shows incremental change at each step. Use this when the user is asking what changed *along the way*.
- **Baseline**: v1→v2, v1→v3, v1→v4, ... — shows cumulative drift from the original. Use this when v1 is a template/master and the user is asking how far later versions have drifted from it.

Infer the mode from phrasing ("what changed at each revision" → sequential; "how far has this drifted from the original" → baseline). If it's genuinely ambiguous, ask — but default to sequential rather than blocking on it.

## Step 3: Extract and Diff

Run the extraction and diff scripts. This step is deterministic and must not be replaced by reading the documents yourself:

```
python3 scripts/extract.py --files v1.docx,v2.docx,v3.docx --out /tmp/redline-extract.json
python3 scripts/diff_engine.py --extracted /tmp/redline-extract.json --mode sequential --out /tmp/redline-diffs.json
```

`extract.py` caches per-file text so a version used in two comparisons (e.g., v2 in both v1→v2 and v2→v3) isn't re-parsed. It flags PDFs with no extractable text (scanned/image-only) — if you see that flag, tell the user OCR would be needed rather than guessing at content.

`diff_engine.py` outputs, per version pair: insertion/deletion counts, changed paragraphs with their location, and word-level diff spans. This JSON is your ground truth for everything in Step 5.

## Step 4: Handle No-Change Pairs

If a pair's diff is empty, note it as "no changes between vX and vY" and move on — don't error out, and don't skip producing a summary line for it, since "nothing changed here" is itself useful information in a version chain.

## Step 5: Render Outputs

```
python3 scripts/render_docx.py --diffs /tmp/redline-diffs.json --pair v1_v2 --out ./redline-output/
python3 scripts/render_html.py --diffs /tmp/redline-diffs.json --pair v1_v2 --out ./redline-output/
python3 scripts/render_dashboard.py --diffs /tmp/redline-diffs.json --out ./redline-output/
```

Run `render_docx.py` and `render_html.py` once per pair. Run `render_dashboard.py` once total, only when there's more than one pair — it builds a single HTML file with navigation between pairs and a summary table, so the user isn't stuck opening a dozen files to get the overview.

Name outputs `{basename}_v1_vs_v2_redline.docx` / `.html`, all written to one output folder per run.

## Step 6: Summarize

This is where you add value beyond the raw diff. Read the diff JSON's summary fields and write a short natural-language account: which transitions had the most change, what kind of change (a new clause, wording cleanup, a deleted section), and anything that stands out.

Every claim in your summary must map to an actual entry in the diff JSON — a specific paragraph or page reference. If you're not sure a change is real, don't assert it; that's what the diff JSON is for. This mirrors the reason `follow-builders` never lets its digest include content without a source URL: an unsourced claim in a redline summary is worse than no summary at all, because someone might rely on it for a real decision.

Write this summary in the language set by `config.language` (see "Language Preference" above) — English, Chinese, or interleaved bilingual. The diff data itself stays as-is regardless of language setting; only your commentary changes.

## Step 7: Deliver

Read `config.delivery.method` from `~/.redline/config.json` (default to local if the file doesn't exist).

**Local** (default): tell the user
- Where the output files are (individual docx/html per pair, plus the dashboard if applicable).
- Your natural-language summary from Step 6.
- Any no-change pairs or parsing issues (scanned PDFs, ambiguous ordering you had to ask about) — flag these plainly rather than burying them.

**Telegram or email**: confirm the recipient before every send — never silently reuse the saved default without checking, since a saved default from an earlier conversation may not be who the user wants this particular output going to.

- If the user already named a specific recipient in this same request (e.g. "send this to alice@example.com"), use that recipient for this send and skip the question below.
- Otherwise, ask: "Send to `<config.delivery.email or chatId>` (your saved default), or somewhere else for this one?" Use whichever the user picks for this send only.
- Only overwrite `config.json`'s saved default if the user explicitly says to make it their new default (e.g. "always send here from now on") — see "Handling Follow-Up Requests" below. A one-off recipient for this send should not silently become the new default.

Then send the summary text plus the output files as attachments:

```
python3 scripts/deliver.py --method telegram --files ./redline-output/*.html,./redline-output/*.docx --summary "<your Step 6 summary>" --chat-id <confirmed chat ID>
python3 scripts/deliver.py --method email --to <confirmed email> --files ./redline-output/*.html,./redline-output/*.docx --summary "<your Step 6 summary>"
```

Still tell the user in chat what was sent and where the local copies live — delivery is a convenience on top of the local files, not a replacement for telling them what happened. If `deliver.py` fails (bad token, missing key, network issue), fall back to reporting the local file paths and let the user know delivery didn't go through, rather than silently dropping the output.

## Absolute Rules

- **Never report a change that isn't in the diff JSON.** Every insertion, deletion, or summary claim in Step 6 must trace back to an actual entry from `diff_engine.py`.
- **Never compare documents by reading them yourself instead of running the scripts.** Word-level diffing is not something to approximate from memory or a skim — that's exactly the class of error the deterministic pipeline exists to eliminate.
- **Never infer content from a scanned or image-only PDF.** If `extract.py` flags no extractable text, say OCR is needed. Guessing what a scanned page probably says is worse than saying nothing.
- **Never guess version ordering when it's ambiguous.** If filenames/dates don't make the sequence obvious, ask. A redline built on the wrong order is confidently wrong, not just incomplete.
- **Never send Telegram or email delivery without a confirmed token/key and explicit user opt-in.** No placeholder chat IDs, no assuming a delivery method carries over from a different context.
- **Never send to a saved recipient without confirming it for this send.** Confirm the recipient (or use one the user already named this turn) every time, per Step 7 — a saved default is a convenience, not a standing authorization to send anywhere on the user's behalf without checking.
- **Never let a delivery failure silently swallow the output.** If `deliver.py` fails, fall back to reporting local file paths — the user should never end up with nothing after a run that actually produced results.
- **Never modify or overwrite the user's original documents.** All output is new files in the output folder; the source files are read-only inputs.

## Handling Follow-Up Requests

- "Compare against v1 only" / "how far has this drifted" → switch to baseline mode for this run.
- "Just give me the summary, skip the docx" → skip `render_docx.py`, still run `render_html.py` and the dashboard.
- "Only show me v3 and v4" → narrow the input set, rerun from Step 1.
- "There's a table that got cut off" / similar extraction complaints → check `extract.py`'s table handling before assuming the diff itself is wrong.
- "Send this to Telegram/email instead" / "just show me the files" → update `delivery.method` in `~/.redline/config.json`; walk through the relevant setup from "Delivery Preferences" above if switching to Telegram or email for the first time.
- "Send this one to bob@example.com" → use that address for this send only, per Step 7; don't touch the saved default in `config.json` unless the user also says to make it permanent.
- "Send my redlines to a different email [from now on]" / "make this my new email" → update `delivery.email` in `config.json` so it becomes the new saved default.
- "Switch to Chinese/English/bilingual" → update `language` in `config.json`; applies starting with the next summary, no need to re-run the current comparison.

## Manual Invocation

`/redline`, or the user directly handing over 2+ versions of a document and asking what changed — run this workflow immediately, starting at Step 1.

---
name: editorial-review
version: 1.1.0
description: >-
  Review prose and argument. Use for /editorial-review, article critique, essays, whitepapers, evidence or charts.
---

# Editorial review

An opinionated editorial review applying six lenses, substance first: structure
and lede discipline, argument quality, thought-leadership effectiveness, prose
quality, AI voice detection, and - where charts or data are present - visual and
data quality.

**Philosophy:** writing that works gets action from a busy reader. The substance
has to land first, and surface hygiene comes last, because writing that reads as
machine-generated erodes the credibility that earns a reader's attention. Short
sentences. Vigorous English. Bold claims backed by evidence. Conclusion first,
inverted pyramid throughout. Every word earns its place. Your writing is you.
(After Kenneth Roman, Paul Graham, and the Kansas City Star copy rules.)

This skill has no dependencies and no configuration. It reads a piece and
returns a report.

## Intake

One panel, before the piece or any lens reference is read. Skip what the request
settles; say what you read in the line above the panel.

**Depth** - How deep is the pass?
- Full - all six lenses, Lens F where charts or data appear (the default)
- Quick - Structure and Lede plus Prose, the top three issues only
- Deep - all lenses plus line-by-line rewrites for every flagged passage
- Voice only - Lens E alone: the banned list and the structural tells; no substance verdict
- settled by: "quick look" (Quick); "deep pass" or "line by line" (Deep); "voice check" or "AI tells" (Voice only)

**Surface** - What is the piece for?
- Essay - a post or a website essay; second person and fragments allowed
- Newsletter - dek, body, call to action
- Formal - a report, whitepaper or client document; acronyms defined on first use
- Internal - a note or an email; terse, no ceremony
- settled by: a `voice_surface` field in the file's frontmatter; a formal report template

**Sources** - Is there material to re-read before a rewrite?
- On file - a braindump, scratch notes or a prior version at a path you give after the panel; re-read it before any compressive rewrite
- None - nothing to re-read; every compressive rewrite is flagged for your check instead
- settled by: a notes or prior-version path in the request (On file)

**Output** - What comes back?
- Report - the template: verdict, strengths, the lens sections, recommended edits with quoted text
- Report and rewrite - the report, then the rewrite applied in the same session
- Verdict only - the overarching test and the verdict line, for a go or no-go
- settled by: "then fix it" or "and rewrite" (Report and rewrite); "is it ready" (Verdict only)

Text fields, one message after the panel: the piece (a path, a URL, or pasted
text) and the source-notes path where Sources is On file.

## Workflow & references

Read [`references/review-guide.md`](references/review-guide.md) for the full six-lens
workflow, report template, editorial rules, voice rules, pre-emit self-lint and
acronym conventions.

| Pass | Reference |
|---|---|
| Lens A: Structure and Lede | `references/structure-lede.md` |
| Lens B: Argument Quality | `references/argument-quality.md` |
| Lens C: Thought Leadership | `references/thought-leadership.md` |
| Lens D: Prose Quality | `references/prose-quality.md` |
| Lens E: AI Voice Detection | `references/ai-voice-structural.md`, `references/ai-voice-detection.md`, `scripts/voice_lint.py` |
| Lens F: Visual and Data Quality | `references/visual-vocabulary.md` |
| Voice calibration | `references/voice-fingerprint.md` |

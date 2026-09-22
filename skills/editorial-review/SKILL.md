---
name: editorial-review
version: 1.0.0
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

## Workflow

1. **Determine the input type.**
   - **PDF** - extract the text. For a large PDF (more than ten pages), process
     it section by section.
   - **Markdown or text file** - read it directly.
   - **URL** - fetch it and extract the article body.
   - **Pasted text** - work with it directly.

2. **Read the full piece** before forming any judgement. Never review
   piecemeal.

3. **Determine the review mode** from the panel's Depth answer:
   - `quick` - the Structure and Lede lens, the Prose lens, and the top three
     issues only. Lede discipline is the single highest-impact lens, so it stays
     in quick mode.
   - `full` - all lenses. The default.
   - `deep` - all lenses, plus line-by-line rewrites for flagged passages.

4. **Apply the lenses** in order. Substance leads; AI voice is the final hygiene
   pass. Load each reference file as you begin that lens.

   **First, the overarching test: does it work?** Before the lenses, ask Roman's
   question of the whole piece. Is the point clear and up front? Is it specific?
   Would a busy senior reader get it and act on it? Does it sound like the
   writer at their best? Writing that works gets action from a busy reader, and
   the lenses below serve that end. Carry the answer into the verdict.

   **Lens A: Structure and Lede** → You Must Read `references/structure-lede.md`
   Apply the inverted pyramid: the title test (does the title earn its place,
   and does the body deliver on it), the lede test (two sentences or fewer, with
   the conclusion in sentence one), the five Ws and how by the end of paragraph
   two, the cut-from-the-bottom test, headlines-not-labels for interior headings
   and chart captions, and the **dependency-order test** (information is a
   directed acyclic graph, so section N should not depend on a concept first
   defined in section N+2). The most common structural failure in a draft is a
   buried lede, and this lens catches it. The second is a title the body never
   picks up as a frame. The third is a dependency-order violation, where the
   reader meets a concept before its definition and has to backtrack.

   **Lens B: Argument Quality** → You Must Read `references/argument-quality.md`
   Evaluate against four components: Correctness, Novelty, Importance and
   Strength. Then run the **steelman test**: build the strongest good-faith case
   against the central claim, and judge whether the piece survives it.

   **Lens C: Thought Leadership** → You Must Read `references/thought-leadership.md`
   Apply the six criteria: Position, Evidence, Counterintuitive Element,
   Audience Value, Authority, So What.

   **Lens D: Prose Quality** → You Must Read `references/prose-quality.md`
   Flag specific passages violating the Kansas City Star rules or the simplicity
   principles.

   **Lens E: AI Voice Detection** (the final hygiene pass) → You Must Read
   `references/ai-voice-structural.md` first, then `references/ai-voice-detection.md`
   This is the closing pass that protects credibility: writing that reads as
   machine-generated undermines the substance the earlier lenses built. Run the
   four source-aware scans in `ai-voice-structural.md` before the lexical
   tables: provenance against the source, epistemic inflation, performed voice,
   and argument self-commentary with its deletion and referent tests. A word
   swap made before the claim is checked gets thrown away when the claim
   changes, so the lexical pass goes last. Then flag every banned word, banned
   phrase, structural tell and tonal signature from `ai-voice-detection.md`. Its
   Voice-Positive Axis applies to the Essay surface alone. This lens is
   rigorous, and it does not outrank the substance lenses: hygiene serves the
   argument rather than replacing it.

   **Lens F: Visual and Data Quality** (only where charts, tables or data are
   present) → Read `references/visual-vocabulary.md`
   Apply the FT Visual Vocabulary chart-selection logic, the Tufte principles,
   and the data-integrity checklist.

5. **Produce the review** using the output template below.

### Source re-reading before a substantive rewrite

Before proposing or applying a substantive paragraph rewrite, re-read the
original source notes where any exist: a braindump, scratch notes, or a prior
version. Paragraph rewrites that compress or reframe a claim are the most common
drift point - the rewrite reads fine in isolation and loses the load-bearing
detail, such as a named tool, the *why* behind a claim, a named referent, or a
contrarian framing. One re-read prevents two iterations.

## Output template

```markdown
## Verdict

[One sentence. What is this piece, and is it good? Be direct. Lead with whether
it works: does the point land for a busy reader?]

## Strengths

- [Specific strength with a quoted passage]
- [Specific strength with a quoted passage]
- [Specific strength with a quoted passage]

## Structure and lede issues

**Title test:** [Quote the title. Does it earn its place, or is it a label? Does
the article deliver on its premise? Does the body pick it up as a frame anywhere
- opening, section breaks, close? Where the title is strong but underused, name
one or two places in the body where the frame should be picked up. Where it is
weak, propose two or three sharper alternatives tied to specific lines.]

**Lede test:** [Quote the first paragraph. Is it two sentences or fewer? Does
sentence one carry the conclusion? If not, propose a rewritten lede.]

**Five Ws and how:** [List which of who / what / when / where / why / how land
in the opening two paragraphs. Flag any core dimension that is missing or
vague.]

**Cut-from-the-bottom test:** [Name the paragraph that should be the new ending.
Identify any trailing paragraphs that restate, sign off, or add nothing.]

**Headlines, not labels:** [Walk the interior headings and any chart captions.
Flag category labels ("Background", "Trends") that could be claims, and propose
the claim version.]

**Dependency-order test:** [Walk the section list. For each section, name any
concept, person, framework or term it relies on. Flag any case where the
dependency is first defined in a later section, or where a forward reference
forces the reader to backtrack. Propose a reorder that respects the dependency
graph.]

| Passage | Failure | Suggested fix |
|---------|---------|---------------|
| "..." | [weak title / unused title frame / buried lede / missing W / restated ending / scene-setting opener / label-not-headline / dependency-order violation / other] | "..." |

## Argument issues

**Correctness:** [Assessment]
**Novelty:** [Assessment]
**Importance:** [Assessment]
**Strength:** [Assessment, including any oversell - exaggeration that risks the whole case]
**Steelman:** [State the strongest counter to the central claim. Does the piece
anticipate it? Where the argument cannot survive it, say so and carry that into
the verdict.]

[Specific gaps, with quoted passages]

## Thought-leadership issues

[Apply only the criteria that are relevant. Do not force all six where some do
not apply.]

## Prose issues

| Passage | Issue | Suggested fix |
|---------|-------|---------------|
| "..." | [which rule, named] | "..." |

## AI voice issues

[Every banned word, banned phrase, structural tell or tonal signature. Quote the
text, name the tell, suggest the fix. This is the closing hygiene pass, so keep
it proportionate to the substance findings above.]

| Passage | AI tell | Suggested fix |
|---------|---------|---------------|
| "..." | [provenance / epistemic inflation / performed voice / argument self-commentary / banned word / banned phrase / negation-contrast / fence-sitting / em-dash overuse / metronomic rhythm / sycophancy or corporate tone / other] | "..." |

## Visual and data issues

[Only where charts, tables or data visualisations are present. Apply the chart
quality checklist from visual-vocabulary.md. Flag chart-type mismatches,
integrity issues, missing labels or sources, and analytical errors.]

## Recommended edits

[Ordered by impact, most important first. Include before and after for the top
three.]

1. **[Highest-impact edit]**
   - Before: "..."
   - After: "..."
   - Why: [principle]
```

## Rules

- **Quote the text.** Every flag references a specific passage. No abstract
  complaints.
- **Name the principle.** Do not say "this is weak". Say which rule it violates.
- **Suggest the fix.** Do not only identify problems. Propose concrete rewrites.
- **Be direct.** This skill has a point of view. It believes in short sentences,
  concrete examples, bold claims and honest data. It flags executive pablum by
  name.
- **Do not praise mediocrity.** Where a piece is bad, say so. The Strengths
  section can be short.
- **Respect the author's voice.** Suggest improvements that sound like the
  author at their best, and not like a different writer.
- **Scale to the document size.** For a long PDF, use parallel agents, one per
  section, then synthesise. For a short article, a single pass.

## Voice rules

Lens E enforces these across two files. `references/ai-voice-structural.md`
carries the four source-aware scans and runs first;
`references/ai-voice-detection.md` carries the lexical checklist and runs last.
Read both when applying Lens E.

The lexical file covers: banned vocabulary and banned phrases; sycophancy and
chatbot leak; the structural tells (negation-contrast in all its shapes - `X,
not Y`; `It's not X, it's Y`; twin parallel-verb sentences; the semicolon
variant; the fragment-negation triplet; the announcing-pair subhead - plus
invented detail, superficial -ing tails, copula avoidance, fence-sitting,
tricolons and metronomic rhythm); formatting tells; punctuation and British
English house style; and the voice-positive axis, which applies to the Essay
surface alone. Every flag in the AI Voice Issues table maps to a rule in one of
the two files.

`references/voice-fingerprint.md` is the third file under this lens, and it is
optional. Load it where a draft has drifted from a piece the writer already
published: it measures person, sentence-length distribution, fragment density,
concreteness density, em-dash rate and joke density against an anchor, and the
numbers make a Lens E finding concrete. It is evidence for a review, and it is
never a target handed to a drafter.

This is a hygiene pass. It protects the credibility the substance lenses build,
and it does not outrank them. A piece can fail this lens and still be worth
saving where the argument is strong. The fix is to clean the prose rather than
discard the thinking.

## Voice canon during co-drafting

The voice canon applies to **any prose the assistant produces or applies**,
including prose the user has just proposed verbatim. Where the user supplies a
sentence that violates the canon - X-not-Y, twin parallel-verb, phantom
contrast, banned vocabulary, unspaced em dashes - flag the violation *before
applying it* and offer a rewritten version alongside the verbatim one.
Apply-then-fix is twice the work and burns the user's editorial budget. Treat
user-proposed prose as a draft rather than as final.

### Pre-emit self-lint

When this skill is active, every rewrite the assistant emits - every cell in the
Suggested Fix columns, every before-and-after in Recommended Edits, every
rewritten lede or transition - must itself pass Lens E before it is shown. Read
each proposed sentence silently against the negation-contrast table, the banned
vocabulary, the banned phrases and the announcing-subhead rule. Where it fails,
regenerate.

Helping edit slop out while emitting slop in costs more editorial budget than
the original review.

Write-time, and not review-time. The grep pass and the lens application are
backstops; the primary defence is a per-suggestion self-check before the
suggestion is rendered. Do not rationalise a construction as "load-bearing" or
"earned" - the rationalisation IS the tell.

This rule applies recursively to any subagent this skill spawns. Pass the
negation-contrast list explicitly in the subagent prompt, because a subagent
does not load the project instruction file or this skill's references.

## Acronyms on long-form and formal surfaces

For website essays, posts, reports, whitepapers and similar long-form or formal
surfaces, define acronyms on first appearance. The audience for these pieces is
mixed-technical: engineers know CLI, OAuth, SSO and RPA instantly, and the
senior readers who act on the piece may not. Either expand parenthetically on
first use ("CLI (command-line interface)") or use the plain-English term
throughout ("command line"). Internal notes and engineering chat do not need
this discipline.

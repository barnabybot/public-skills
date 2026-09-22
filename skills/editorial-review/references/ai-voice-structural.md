# Structural AI tells — the source-aware scans

Adapted from EveryInc/compound-writing v2.3.0, MIT,
`skills/cw-ai-check/references/structural-overcompletion.md`.

Four scans that survive every lexical pass. The banned-word and
banned-structure tables in `ai-voice-detection.md` work one sentence at a
time. These four read a claim against its source, and a passage against the
shape of the argument around it. A draft with zero banned words fails all
four.

A blind test of the four arms is the evidence. Every arm scored zero on the
lexical floor. The arms separated on provenance (a wrong claim in a
signed-off plan passed a source-fact trace and was caught only by a
provenance scan), on certainty (one arm hardened a conditional thesis into a
flat assertion), on performed voice (a drafter told to hit four fragments per
hundred words supplies them on cue), and on self-commentary (nine sentences
in one arm that narrated the chart).

## Running order

Run these four before the lexical tells, then run the tables in
`ai-voice-detection.md` last. A word swap made before the claim is checked
gets thrown away when the claim changes. The repair order is
compound-writing's, and it holds for the same reason: the lexical pass is
cosmetic, so it goes last.

1. Provenance
2. Epistemic inflation
3. Performed voice
4. Argument self-commentary
5. The lexical tables in `ai-voice-detection.md`

## Scan 1 — Provenance against the source

Every factual claim traces to the source material, and the plan is a claim
like any other. A storyboard, an outline, a brief or a prior draft is
one more input to check. A claim the plan asserts and the data
contradicts is the failure this scan exists to catch, and a source-fact map
does not catch it: the map records where a number came from, and the wrong
reading of that number travels with it.

Walk each factual sentence and ask:

- Which line of the source carries this? Name the file and the row.
- Does the source say this, or does it say something the sentence rounds,
  merges or extends?
- Where the claim came from the plan, does the underlying data still support
  it when read directly?
- Is a named entity, date, figure or quotation present in the source, or was
  it supplied to make the sentence complete?

Flag: a claim with no source line; a claim whose source line says something
narrower; a list presented as exhaustive that the source does not close; a
figure that is a derivation the writer never states.

## Scan 2 — Epistemic inflation

The certainty of the sentence matches the certainty of the evidence. A
conditional in the source stays conditional in the prose. This scan is the
one that separated the arms in the blind test. One arm kept its thesis inside its
condition: "if that holds, the hours column drops out of the ranking." The
writer read that as honest. A second arm hardened the same thesis and then
contradicted itself two sentences later, and the writer read a machine
finishing a thought it had not earned.

Flag:

- A hedge in the source rendered as a flat assertion.
- A correlation rendered as a cause.
- A single observation rendered as a pattern, a trend or a rule.
- A superlative or a totalising phrase ("the whole ranking is", "every",
  "always") where the evidence covers a sample.
- A claim that contradicts a qualification the same piece already made. Read
  the piece end to end; this one is invisible sentence by sentence.

The fix restores the qualification. "This table cannot say who that is"
beats a vague hedge.

## Scan 3 — Performed voice

Signature moves supplied at implausible density. A writer's fragments,
asides, jokes and direct judgements arrive where the material calls for
them. A model told to produce four fragments per hundred words produces four
fragments per hundred words, evenly spaced, each doing nothing the sentence
before it did not already do.

Flag:

- Fragments at a steady rate, evenly spaced through material that calls for
  none of them.
- Asides or footnoted jokes that carry no content and could be cut with no
  loss.
- Direct judgements ("this is a mess") on material the piece has not
  examined enough to judge.
- First person used as decoration, attached to no action the writer took.
- A rhythm that matches a measured target more closely than any human draft
  matches itself.

This is the failure mode a voice fingerprint produces when it is handed to a
drafter as a target. The fingerprint belongs in
`voice-fingerprint.md` beside this file, where it measures distance at review time.

## Scan 4 — Argument self-commentary

The prose rates its own evidence, signposts its own structure, labels a
claim's status, or characterises a quotation before delivering it. It reads
as a guide standing beside the argument.

Shapes:

- Evidence rating: "strikingly", "remarkably", "the data is unambiguous".
- Structural signposting: "this section shows", "as discussed above", "we
  turn now to".
- Status labels: "importantly", "the key point is", "worth noting".
- Quotation framing: "as X put it so well", "a telling remark".
- Chart narration: "the chart shows", "what stands out here is".

Two tests settle each candidate.

**The deletion test.** Cut the phrase. If the paragraph says the same thing,
the phrase was commentary. Delete it.

**The referent test.** Ask what "this", "here", "that point" refers to. Where
the referent is the writing itself, the sentence is talking about itself.
Rewrite it to talk about the subject, or cut it.

Nine self-commentary sentences appeared in one blind-test arm across two
slices, from a skill whose own steps ask for "the key finding" and "the
comparison context". A prompt that asks for narration gets narration.

## What this file does not cover

The banned vocabulary, the banned phrases, the six shapes of
negation-contrast, the formatting tells, British-English house style and the
voice-positive axis are in `ai-voice-detection.md`. Seven further
compound-writing scans (causal closure, framework compliance, metaphor
systems, portable profundity, reader assignment, decorative research,
over-resolved endings) are not adopted; the four here are the ones the blind
test showed the canon missing.

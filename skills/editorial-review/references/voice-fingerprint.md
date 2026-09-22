# Voice fingerprint — review-time evidence

This file measures how far a piece sits from a voice anchor. It is evidence a
reviewer quotes.

**Read it at review time, and never hand it to a drafter as a target.** That
distinction was settled by a blind read of eight drafts: prose written to
perform a measured voice ranked last, and the register that constrained what a
sentence must *do* ranked first. Numbers that describe a sample are useful.
The same numbers as a target produce performed voice, which Scan 3 of
`ai-voice-structural.md` exists to catch.

## Why a fingerprint at all

An editorial canon describes what voice is *not*: banned vocabulary, banned
structures, formal-register tells. It does not describe what voice *is*. That
gap is how a draft can pass every avoidance rule and still read as generic
corporate blogging - high compliance, no inherited voice signal from any
sample.

A fingerprint closes the gap by measuring the positive signal in a piece the
writer already published, so a reviewer can name the distance in numbers
instead of in taste.

## What to extract

From the voice anchor (a prior published piece in the same voice, or 2-3
paragraphs of fresh prose the user has just drafted), compute:

| Dimension | How to measure | Why it matters |
|---|---|---|
| **Person** | Count first / second / third person pronouns. Pick the dominant one. | One recorded failure inherited first person from a canon's "I" examples when the writer's voice for that surface was second person ("you"). Person is the single most surface-distinguishing dimension. |
| **Sentence-length mean** | Words per sentence, mean across the sample. | An essay-surface voice may run to 14 words where the same writer's formal-report voice runs 18-22. Confuse the two and the rhythm dies. |
| **Sentence-length variance** | Standard deviation, or p10/p90 range. | Metronomic rhythm is an AI tell. A human voice usually has wide variance - a four-word fragment next to a 25-word sentence. |
| **Fragment density** | Sentences with no main verb, or under 5 words. Count per 100 words. | Fragments are voice-positive on the Essay and Note surfaces and forbidden on a formal-report surface. The reading depends on which surface the piece is for. |
| **Concreteness density** | Named tools, real numbers, real times, real amounts, named incidents. Count per 100 words. | The Essay surface wants 3 or more per 100 words. Generic corporate blogging measures at 1 or below. |
| **Em-dash count** | Em-dashes per 100 words. Spaced and unspaced separately. | Unspaced em-dashes inside sentences are banned by the canon. Spaced em-dashes are voice-positive but capped at one per 3 sentences. |
| **Joke density** | Footnoted asides, parenthetical asides, dry one-liners. Count per 1,000 words. | The Essay surface tolerates about 2 per 1,000 words. A formal report takes none. A newsletter takes dry ones only. |
| **Voice-positive markers** | Use of "I" for reactions; explicit edges and reservations; direct judgements ("this is a mess", "well-designed"). Boolean per category. | Voiceless writing fails the argument lens. The reviewer needs to know whether the anchor permits reactions and edges at all. |

## How to extract (pseudocode)

```python
def extract_fingerprint(anchor_text: str) -> dict:
    sentences = split_sentences(anchor_text)
    words = anchor_text.split()
    word_count = len(words)

    return {
        "person": dominant_person(anchor_text),   # 1 | 2 | 3
        "sentence_words": {
            "mean": mean(len(s.split()) for s in sentences),
            "p10":  percentile([len(s.split()) for s in sentences], 10),
            "p90":  percentile([len(s.split()) for s in sentences], 90),
        },
        "fragments_per_100w":     fragments(sentences) / word_count * 100,
        "concreteness_per_100w":  count_specifics(anchor_text) / word_count * 100,
        "em_dashes_per_100w":     anchor_text.count(" — ") / word_count * 100,
        "jokes_per_1000w":        count_asides(anchor_text) / word_count * 1000,
        "voice_positive": {
            "uses_first_person_for_reactions": has_I_with_reaction_verb(anchor_text),
            "shows_edges":                     has_reservation_markers(anchor_text),
            "direct_judgements":               has_direct_judgement(anchor_text),
        },
    }
```

The drafter does this by inspection. The pseudocode above is a mental model.
What matters is that the drafter reads the anchor and forms a concrete
fingerprint before writing a single paragraph.

## Detecting specifics (for `concreteness_per_100w`)

Count any of:

- Named tool or product: "Codex", "Claude Code", "cmux", "Postgres", "Cloudflare"
- Named company or institution: "Anthropic", "Amazon", "Cursor", "AWS"
- Real number with unit: "13 hours", "9 seconds", "$2m", "40MB", "5%"
- Real time reference: "April morning", "Tuesday at 11pm", "December"
- Named incident: "Amazon coding agent deleted a live production environment"
- Real dollar amount or named cost: "Anthropic bill"
- Real file path or technical artefact: `settings.json`, `CLAUDE.md`, cron entry

Do not count vague intensifiers ("very", "highly", "extremely") or
abstract nouns dressed as specifics ("the challenges", "the opportunities").

## Shape, and not lines

What a fingerprint describes is *shape*: the same person, a similar
sentence-length distribution, a similar fragment density, a similar
concreteness density, a similar joke tolerance. Nothing about it says to reuse
the anchor's sentences.

## Worked example

Source: a published essay by the same writer, on the Essay surface, about 1,800
words. Extracted by inspection:

```yaml
voice_fingerprint:
  person: 2                       # dominant "you"; "I" reserved for the anchor and the closer
  sentence_words:
    mean: 12.4
    p10: 3                        # three-word beat sentences
    p90: 26
  fragments_per_100w: 4.2         # beat sentences, intentional fragments
  concreteness_per_100w: 5.1      # named tools, real durations, real counts
  em_dashes_per_100w: 0.6         # spaced only, never unspaced
  jokes_per_1000w: 1.5            # one footnoted aside, one dry one-liner
  voice_positive:
    uses_first_person_for_reactions: true
    shows_edges: true                       # admits the limits of what was tried
    direct_judgements: true                 # names a thing bad when it is bad
```

A draft that had drifted from this anchor would show up as third person, a
sentence-length mean near 20 with little variance, fragments at zero,
concreteness near 1, and no direct judgement anywhere. Those six numbers make
the Lens E finding concrete, and a reviewer can quote them.

A draft can match this fingerprint with prose the anchor never used. The test
is whether a reader who knows the writer's voice would say "yes, that sounds
like them", independently of whether any specific line came from the anchor.

Measure after the first 200 words rather than at the end. Early correction
beats a rewrite.

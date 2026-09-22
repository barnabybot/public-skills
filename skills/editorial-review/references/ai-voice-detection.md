# AI Voice Detection Reference

Flag passages that read as machine-generated. The goal: every sentence should sound like a human wrote it with their own brain. If a reader's "AI alarm" fires, they stop reading — doesn't matter if the content is good.

## The Core Tells

### Punctuation & Formatting

| AI Pattern | Human Pattern | How to Fix |
|---|---|---|
| Em dashes without spaces—like this—constantly | Hyphens or en dashes with spaces – like this | Replace unspaced em dashes with spaced hyphens/en dashes. **Note:** em dashes aren't banned — the tell is overuse and no spaces. |
| Perfect formatting throughout | Inconsistent, organic formatting | Don't fix this one. Imperfection is a signal of authenticity. |
| Bullet points and headers for everything | Longer paragraphs, fewer structural crutches | **Essay surface only.** Let prose breathe there. On the Analytical and Professional surfaces a working analysis is sectioned, because an unbroken wall of prose is harder to follow, so section it instead. |

### Sentence Structure

#### Negation-Contrast — The Single Most Persistent Tell

This is the family of constructions to police hardest. Trained models reach for negation-contrast because it sounds confident; in print it reads as machine-confident — the loudest signature of a model trying to sound like a partner. **All shapes below are flagged. No load-bearing exception.**

| AI Pattern (Shape) | Example to Flag | How to Fix |
|---|---|---|
| `X, not Y` — comma + negation + contrast | *"These figures describe today's users, not a forward adoption curve."* | Drop the negation half. *"These figures describe today's users."* |
| `It's not X, it's Y` / `It's not just X, it's Y` | *"It's not a staffing question, it's a sequencing one."* | Affirmative position. *"This is a sequencing question."* |
| `X is A. Y is B.` — twin short sentences, parallel verb | *"These numbers no longer describe a pilot. They describe a platform."* | Cut. The data sentences before it already make the point. |
| `X does A; Y does B.` — semicolon variant | *"Headcount is the symptom. Process is the cause."* | Rewrite as a longer single sentence: *"The process underneath the headcount is what actually drives the cost."* |
| `Not X. Not Y. But Z.` — fragment-negation triplet | *"Not all of it. Not at once. But enough to matter."* | Pick the affirmative beat and let it stand. *"Enough to change what the team does on Monday."* |
| `X. Then Y.` / `X. Or Y.` / `X. So Y.` — announcing-pair subhead | `**Prune your context. Then your training budget.**` / `**Don't trust one vendor. Or one supplier.**` / `**Slop is easy to spot. So is its corporate version.**` | Cut the second half of the subhead. The body either makes the pairing itself or it does not — announcing the pairing in the subhead is the tic. Same negation-contrast family at heading grain. |

**Subhead-grain grep:** `grep -nE '^\*\*[^*]+\.\s+(Then|Or|So|But|And)\s' file.md` — any hit is a candidate cut. The body must already carry the pairing for the subhead to need both halves; in practice it never does.

**Negation-contrast grep:** `grep -nE '[[:alpha:]], not [[:alpha:]]|is not .{1,40}\. (It|That|They) (is|are)' file.md` — catches the `X, not Y` comma form and the spread-across-two-sentences `X is not A. It is B` twin. It misses the semicolon twin and phantom contrast, so it is a backstop to the per-sentence self-check, never a replacement. Run it on any long artifact before presenting it (an assistant re-introduced this structure across several drafts in one session despite the canon in front of it, so the write-time self-check is the primary defence and this grep is the safety net). Treat every hit as guilty until rewritten affirmatively.

**Phantom contrast — always cut.** The negation half names a claim nobody made. *"...not a forward adoption curve"* invents "forward adoption curve" as a strawman, only to knock it down. Pure rhetorical filler. The affirmative half always stands alone.

**The reviewer's rationalisation trap.** If the writer (or you, on second read) describes the construction as "earned," "load-bearing," or "the central reframe," the rationalisation is the tell. Rewrite anyway. The user reads the shape as slop regardless of whether the contrast carries information.

**Worked rewrites.** Synthetic specimens: the shape is what teaches, and the
subject matter is incidental.

| Before | After |
|---|---|
| "The tools are arriving on machine cycles, not planning cycles." | "The tools are arriving on machine cycles." |
| "Evidence, not instinct, should decide where the budget goes." | "Evidence decides this." |
| "These are not pilot projects; they are production systems." | "Three of the four are already in production." |
| "The mismatch is structural, not incremental." | "The mismatch is architectural." |

#### Invented Detail — The Plausibility Tell

A specific that sounds right but has no source. The model reaches for plausible enterprise furniture — *"SharePoint sites with 2014 org charts and three versions of approved policy"*, *"the dentist has one workflow and a Friday afternoon; the blue chip has ten thousand workflows and a steering committee in six weeks"* — because concrete sentences read as authoritative. They are not concrete. They are decoration with the shape of a number.

| Cue | Example to Flag | How to Fix |
|---|---|---|
| Plausible enterprise set-piece with no source | SharePoint, "2014 org charts", "three versions of approved policy", set-piece dentist-vs-blue-chip vignettes, named meeting cadences ("six-week steering committee") | Cut. Replace with an observation the writer has actually made elsewhere in the piece, or ask the writer to supply the specific. |
| Plausible number with no source | "ten thousand workflows", "forty percent of teams", round-number vignettes | Cut unless the writer has provided the number. Round numbers in invented illustrations are the tell. |

**Rule:** every concrete enterprise detail in the rewrite must trace to something already present in the source material (prior version, braindump, the writer's own observation elsewhere in the piece). If it does not trace, cut it or ask. Do not invent plausible furniture.

#### Other Structural Tells

| AI Pattern | Human Pattern | How to Fix |
|---|---|---|
| Balanced "on the one hand... on the other" for everything | Takes a side. Has opinions. Lives with the discomfort of not being balanced. | Pick a position. If you genuinely see both sides, say which side you lean toward and why. |
| Neat three-part lists and tricolons | Messier, more natural enumeration | Vary list lengths. Two items is fine. Five is fine. Not everything is a trilogy. |
| Every paragraph the same length | Varied rhythm — short punchy paragraphs mixed with longer ones | Read aloud. If it sounds metronomic, vary the cadence. |

#### Superficial -ing Analyses

Tacking a present-participle clause onto the end of a sentence for fake depth. The participle phrase says nothing the main clause didn't already say.

| AI Pattern | Example to Flag | How to Fix |
|---|---|---|
| `..., highlighting [generic noun]` | "The bank cut 5,000 jobs, highlighting the pressure on costs." | Cut from the comma. The action already shows the pressure. |
| `..., underscoring [the importance of X]` | "...underscoring the importance of risk management." | Cut. |
| `..., emphasising [its commitment to X]` | "...emphasising their commitment to innovation." | Cut. |
| `..., reflecting [a broader trend]` | "...reflecting a broader shift toward sustainability." | If the broader trend matters, give it its own sentence. |
| `..., contributing to / fostering / showcasing / cultivating / encompassing [X]` | Same family | Cut. |

**The cue.** A comma followed by `-ing [abstract noun phrase]` at the end of a sentence. If the participle adds no concrete content the main clause lacks, delete it.

#### Copula Avoidance

Substituting an elaborate verb for plain "is" or "has" to sound weighty. Reads as inflated.

| AI Pattern | Human Pattern |
|---|---|
| "X serves as a..." / "X stands as a..." | "X is a..." |
| "X marks a..." / "X represents a..." | "X is a..." |
| "X boasts a..." / "X features a..." / "X offers a..." | "X has a..." |

Keep the elaborate verb only when it carries real meaning ("the bridge spans the river"). The tell is using it as a synonym for "is" or "has" with no semantic gain.

### Word Choice

| AI Tell | Examples | Human Alternative |
|---|---|---|
| "Delve" | "Let's delve into..." | "Let's look at..." / just start looking |
| "Landscape" (as metaphor) | "The AI landscape" | "The AI market" / "what's happening in AI" |
| "Leverage" (as verb) | "Leverage our capabilities" | "Use" |
| "Tapestry" / "Weave" | "A rich tapestry of insights" | Cut entirely. Say what you mean. |
| "Navigate" | "Navigate the complexities" | "Deal with" / "work through" |
| "Robust" / "Comprehensive" | "A robust framework" | "A framework that works" or just describe what makes it robust |
| "Multifaceted" | "A multifaceted approach" | Name the facets, or say "several approaches" |
| "Underscores" | "This underscores the importance" | "This shows" / "This proves" |
| "Nuanced" | "A nuanced perspective" | Show the nuance. Don't label it. |
| "Pivotal" / "Paramount" | "A pivotal moment" | "A turning point" or just describe what changed |
| "Fostering" | "Fostering innovation" | "Building" / "creating" / "encouraging" |
| "Realm" | "In the realm of..." | Cut. Start with the subject. |
| "Harness" | "Harness the power of AI" | "Use AI" |
| "Seamlessly" | "Seamlessly integrates" | Nothing integrates seamlessly. Describe how it actually works. |

**Additional banned vocabulary** (flag on sight, same rule as the table above): crucial, furthermore, moreover, additionally, fundamental, significant (as filler), showcase, intricate, vibrant, interplay, foster. Each is a long or abstract word standing in for a plain one — replace with the specific, or cut.

**Banned phrases** (cut on sight): "here's the kicker", "here's the thing", "plot twist", "let me break this down", "the bottom line", "make no mistake", "can't stress this enough", "in today's fast-paced world", "in the realm of", "it is important to note", "it could be argued".

### Tone & Voice

| AI Pattern | Human Pattern |
|---|---|
| Excessively verbose — uses 30 words where 10 work | Concise. Gets bored of their own padding. |
| Word salads — strings of impressive-sounding terms that mean nothing specific | Specific. Names things. Uses examples. |
| Always seeks balance — hedges every opinion | Has opinions. Willing to be wrong. |
| Sounds nothing like the supposed author | Has a recognisable voice, quirks, preferences |
| American spellings from British writers (organize, utilize) | Consistent with the author's actual dialect |
| Generic enthusiasm ("This is truly exciting!") | Earned enthusiasm tied to specifics |
| Perfect grammar throughout | Occasional fragments. Starts sentences with "And" or "But". Bends rules for effect. |

### Sycophancy and Chatbot Leak

Help-desk register that leaks from the chat surface into finished prose. Always cut.

| AI Pattern | Example to Flag | How to Fix |
|---|---|---|
| Sycophantic opener | "Great question." / "You're absolutely right." / "Excellent point." | Cut. Start with the answer. |
| Help-desk close | "I hope this helps." / "Let me know if you'd like me to..." / "Would you like me to..." | Cut. The reader knows how to ask follow-ups. |
| Chatbot affirmation | "Of course!" / "Certainly!" / "Absolutely!" | Cut. |
| Knowledge-cutoff hedge | "As of my last update..." / "Based on available information..." / "While specific details are limited..." | Cut. If you don't know, say so plainly or don't write it. |
| Generic upbeat close | "The future looks bright." / "Exciting times lie ahead." / "Watch this space." | Cut. End on a specific claim or a pointed question. |

### Vague Attribution

| AI Pattern | Example | How to Fix |
|---|---|---|
| Anonymous "experts" | "Industry reports suggest..." / "Observers have cited..." / "Some critics argue..." / "Several sources indicate..." | Name the source or drop the claim. If you can't name it, you don't have it. |

### Formatting Tells

| AI Pattern | Human Pattern | How to Fix |
|---|---|---|
| Boldface on every other phrase for "emphasis" | Bold reserved for actual key terms or warnings | At most one bolded item per paragraph. If everything is emphasised, nothing is. |
| Inline-header vertical lists everywhere — `**Header:** explanation\n**Header:** explanation` for every section | Lists used only when the items are genuinely parallel; otherwise prose | If the list could be three sentences instead, write the sentences. |
| Title Case In Every Heading | Sentence case headings | Lowercase except the first word and proper nouns. |
| Curly "smart" quotes inside straight-quote prose | Match the quote style used elsewhere in the document | Pick one and stick to it; British house style is straight quotes. |
| Decorative emoji on headings or bullet leads | No emoji unless the platform demands it | Remove. |

### Substance

| AI Pattern | Human Pattern |
|---|---|
| Consensus views only — never challenges orthodoxy | Non-consensus views. Willing to be unpopular. |
| No personal anecdotes or admissions of failure | "I tried this and it didn't work" / "I was wrong about X" |
| Lack of soul — correct but empty | Personality. Humor. Frustration. Delight. |
| No visuals alongside text (or only stock-style AI images) | Human-generated diagrams, photos, hand-drawn sketches |

## The Voice-Positive Axis (Essay surface only)

Banning slop is half the work. The other half is putting voice in. Sterile, voiceless writing is just as obvious as slop — flag both.

**Scope: the Essay surface.** Apply this axis to posts and website essays alone. On the Analytical, Professional and Note surfaces a flat, unornamented register is the right answer, so a piece that reads as sterile there has cleared the bar. Skip the table below on those surfaces.

| Failure | Fix |
|---|---|
| No first person where it fits | "I tried this and it broke" is honest, not unprofessional. If the writer did the thing, "I" is the right pronoun. |
| Reports without reactions | If the writer has no opinion, why are they writing? Show what they think, not just what happened. |
| Smoothed-over disagreement | Real positions have edges and reservations. "I think X, though Y bothers me" beats "X is a balanced consideration." |
| Vague feelings | "Concerns remain" is a non-statement. "The covenant package is too loose" is a statement. |
| Perfect structure end-to-end | A little mess reads as authentic. Don't fix every fragment or every paragraph that runs long. |

Don't add quirks artificially. Find what the writer actually thinks and put *that* on the page.

## The Detection Heuristic

When reviewing, ask for each paragraph:

1. Could this paragraph have been generated by prompting "write about [topic]"?
2. Is there anything here that only THIS author would write — from their specific experience, opinions, or voice?
3. Does it sound like the author talking to a friend, or like a press release?

If the answer to #1 is yes and #2 is no, flag it. The fix isn't to add quirks artificially — it's to find what the author actually thinks and put THAT on the page.

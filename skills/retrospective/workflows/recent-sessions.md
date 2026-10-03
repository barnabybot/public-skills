# Review recent sessions

Default: one repository, up to ten unique substantive sessions and zero to
three proposed fixes. Run manually after ten new eligible sessions or a major
restructure. The review is read-only until changes are authorised.

## 1. Discover and freeze

Ask the installed recall skill to run its **Discovery for another skill**
workflow. Pass the repository, topic and date window already supplied. If no
window is given, start with the last 31 days and state that boundary. Recall
owns note lookup, collection discovery, record reconciliation and native
transcript fallback. Reuse the settled inputs when delegating this step.

From the returned records:

1. Keep substantive work on the named repository, across recorded agents.
   Exclude this review, headless probes and child-agent runs.
2. Order by native session activity timestamp or the corresponding note field.
   File modification time can reflect a later mirror or rename. Record date-only
   ties and use a stable source-path order for those ties.
3. Freeze the selected IDs, paths, timestamps and repository revision before
   extracting findings. A missing ID remains unverified. Record exclusions and
   the actual sample count; use fewer than ten when evidence is limited.
4. On a repeat, use new eligible sessions since the previous sample. Keep the
   previous sample separately for checking whether earlier fixes helped.

| Session ID or path | Agent | Timestamp and basis | Repository evidence | Incident |
|---|---|---|---|---|

Group a build, its review and its repair under one incident when they concern
the same failure. Count affected sessions and independent incidents separately.

## 2. Verify candidates

Use the notes to locate friction, then read targeted transcript excerpts and
the current source files. Record the failed path, repeated read, stale
instruction or user correction with its source location. A note that names a
file alone leaves file-open history unknown.

Check existing solution notes or a relevant change log. Classify each candidate
as confirmed, suspected or already fixed. Only confirmed, currently actionable
findings enter the shortlist. A successful case can challenge the diagnosis.

## 3. Propose the smallest changes

Return zero to three findings. Rank by consequence, independent recurrence and
measured retrieval cost. Leave unmeasured token savings as hypotheses.

| Finding | Sessions / sample; incidents | Evidence and current cause | Fix and owner | Verification |
|---|---|---|---|---|

Fix the producing template or owning workflow. Use an index entry when the
information exists but is hard to find. Show the proposed edits and retain the
user's existing authorisation; unresolved write boundaries need approval.

## 4. Check the result

For an instruction change, freeze a small task set and pass criteria before a
comparison. Run the original and candidate with the same model, effort, task
order and tool limits in fresh contexts. Readers see their assigned snapshot
and prompt. Keep the answer key and arm mapping separate. Save prompts,
snapshot hashes, outputs and tool-read logs.

Score correctness first. Record full-file reads, search operations and returned
content separately. Report provider token use only when measured consistently
in both arms. Returned characters measure retrieval volume. One pair is a
pilot; regressions take priority over a lower read count.

For template edits, check the affected choices and unresolved tokens. Record
the review's own elapsed time and token use when available. Distinguish local
checks, publication and results observed in subsequent sessions.

Return the findings and limitations in chat and update the session note. Keep
supporting evidence in the configured notes root under
`Ops/retrospective/YYYY-MM-DD <run>/`, or at the requested report path.

## Worked example

Recall reconciles twelve notes into ten session records. Three
sessions describe one writer failure, so the finding records `3/10 sessions;
1 incident`. The trace identifies a failed import, but the current file already
contains the fix. Exclude that candidate from the shortlist. If no other
confirmed issue remains, report zero new fixes and retain the sample for a
later check.

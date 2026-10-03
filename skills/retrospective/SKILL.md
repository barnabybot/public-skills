---
name: retrospective
version: 1.0.0
attribution: "Single-session retrospective approach inspired by Artem Zhutov."
description: >-
  Reviews completed work and proposes evidenced improvements. Use for /retrospective,
  lessons learned, repeated agent mistakes, or a review of recent sessions.
fallback: >-
  If historical records or recall are unavailable, report the missing evidence.
  A current-session review can use the visible conversation with that limit stated.
---

# Retrospective

Turn observed mistakes and repeated work into small, reviewable changes.
Recall supplies past-work evidence; retrospective selects and evaluates it.

## Intake

Ask one panel before reading a workflow or source records. Skip questions
settled by the request and state the supplied scope.

**Focus** - What should be reviewed?
- Current session - corrections and repeated work in the visible conversation
- One skill or incident - the named workflow or failure only
- Recent sessions - up to ten unique, substantive sessions for one repository
- settled by: "recent sessions" or "last N sessions" (Recent sessions); a named skill or incident (One skill or incident); "this session" (Current session)

**Venue** - Where should the review run?
- Fresh context - use orchestrator to open a review workspace with source pointers
- Here - review the supplied evidence in this conversation and state any context limits
- settled by: an already dispatched review (Fresh context, reuse it); "here" or "inline" (Here); orchestrator unavailable (Here)

**Action** - What should happen to the findings?
- Propose only - show the evidenced fixes and proposed edits
- Apply approved fixes - make changes already covered by the user's approval
- settled by: "show me" or "review only" (Propose only); explicit approval of named fixes (Apply approved fixes)

**Output** - Where should the result go?
- Chat and session note - report here and update the session record
- Named report - write the requested file and give the findings in chat
- settled by: a report path (Named report)

Collect only missing text inputs: the repository for Recent sessions, the skill
or incident for a focused review, and any source or report path the user named.

## Routes

| Focus | Read |
|---|---|
| Current session, one skill or one incident | `workflows/session.md` |
| Recent sessions | `workflows/recent-sessions.md` |

For Fresh context, use the installed orchestrator with the settled scope and
existing authorisation. A receiving reviewer reuses that workspace. A handoff
continues only after the receiver has the brief and source pointers.

## Dependencies and outputs

- Historical discovery uses the installed `recall` skill. Pass its discovery
  workflow the settled repository, topic and date window. It returns records;
  retrospective owns eligibility, incident grouping and proposed changes.
- `orchestrator` is optional for a fresh review workspace. `skill-manager`
  validates a proposed skill change when available.
- Use `${AGENT_NOTES:-$HOME/agent-notes}` for session records and evidence.
  Keep evidence under `Ops/retrospective/YYYY-MM-DD <run>/` beneath that root.
- Run manually. Scheduling requires a separate request. Publication follows
  the destination repository's approval rules.

## Examples

```
/retrospective this session, here, propose only
/retrospective recent sessions ./my-project
```

For the second request, discover up to ten eligible sessions through recall,
freeze their IDs and dates, verify candidate problems in the source records,
then return zero to three changes with evidence. Missing records reduce the
sample and are stated in the result.

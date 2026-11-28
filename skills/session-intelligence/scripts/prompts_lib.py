#!/usr/bin/env python3
"""Shared prompts and JSON schemas for Session Intelligence extraction, synthesis, and life portrait.

Used by both the Antigravity Python `run_workflow` scripts and the portable CLI
`runner.py` so every harness produces identical structured artifacts.
"""
from __future__ import annotations

KINDS = ["improve-skill", "new-skill", "new-cron", "agents-md-rule", "template-fix"]
LMH = ["low", "medium", "high"]

PSUM_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "recurring_patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "count": {"type": "number"},
                    "sessions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["pattern", "count"],
            },
        },
    },
    "required": ["summary", "recurring_patterns"],
}

ROADMAP_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "automation_themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                    "rationale": {"type": "string"},
                    "frequency": {"type": "number"},
                    "est_effort": {"type": "string", "enum": LMH},
                    "est_payoff": {"type": "string", "enum": LMH},
                    "automation_score": {"type": "number"},
                    "proposed_action": {"type": "string"},
                    "evidence_sessions": {"type": "array", "items": {"type": "string"}},
                    "example_quotes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "kind", "automation_score", "proposed_action"],
            },
        },
    },
    "required": ["headline", "automation_themes"],
}

BACKLOG_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_backlog": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "friction_count": {"type": "number"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "proposed_edits": {"type": "array", "items": {"type": "string"}},
                    "sessions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill", "proposed_edits"],
            },
        },
    },
    "required": ["skill_backlog"],
}

NEWWORK_SCHEMA = {
    "type": "object",
    "properties": {
        "new_skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "problem": {"type": "string"},
                    "recurring_in": {"type": "array", "items": {"type": "string"}},
                    "sketch": {"type": "string"},
                },
                "required": ["name", "problem"],
            },
        },
        "new_crons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "cadence": {"type": "string"},
                    "what": {"type": "string"},
                    "sessions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "what"],
            },
        },
    },
    "required": ["new_skills", "new_crons"],
}

RULES_SCHEMA = {
    "type": "object",
    "properties": {
        "agents_md_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {"type": "string"},
                    "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                    "sessions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["rule"],
            },
        },
    },
    "required": ["agents_md_rules"],
}

FIND_SCHEMA = {
    "type": "object",
    "properties": {
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "what": {"type": "string"},
                    "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                    "frequency_hint": {"type": "string"},
                    "reveals": {"type": "string"},
                },
                "required": ["name", "what", "reveals"],
            },
        },
    },
    "required": ["patterns"],
}

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string"},
        "portrait": {"type": "string"},
        "portrait_beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "point": {"type": "string"},
                },
                "required": ["label", "point"],
            },
        },
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence_quotes": {"type": "array", "items": {"type": "string"}},
                    "reveals": {"type": "string"},
                    "kind": {"type": "string", "enum": ["rhythm", "value", "ritual", "drive", "tell", "tension"]},
                },
                "required": ["name", "description", "reveals"],
            },
        },
        "tensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tension": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["tension"],
            },
        },
    },
    "required": ["one_liner", "portrait", "portrait_beats", "patterns"],
}


def extract_prompt(scripts_dir: str, root: str, index: int) -> str:
    return f"""Extract automation findings from ONE agent session digest.

STEP 1 - get your assignment. Run:
   python3 {scripts_dir}/claim.py --root {root} --index {index}
It prints one JSON line: {{"session_id":"...","digest_path":"..."}}. If it prints nothing (empty), reply exactly: skip

STEP 2 - read the digest at that digest_path. Each line is [HH:MM] USER: (the user's typed words or vault goal), [HH:MM] AI: (assistant first line or vault outcome), or [HH:MM] . tool/skill call.
Ignore injected skill docs ("Base directory for this skill:"), harness preambles, and terminal banners.

STEP 3 - analyse the session and write strict JSON to EXACTLY this path (using the session_id from step 1):
   {root}/data/runs/conv-<session_id>.json

   The object MUST have these keys:
   {{
     "session_id": "<the session_id from step 1>",
     "title": "6-10 word title of what this session was",
     "intent": "1-2 sentences: what the user set out to do",
     "task_type": one of ["content","vault-eng","outreach","lead-gen","video","digest","research","coding","admin","automation","analysis","course","other"],
     "skills_invoked": [skills that actually ran],
     "skills_missing": [skills that should have fired but did not],
     "highlights": [1-3 notable VERBATIM user quotes],
     "friction": [{{"quote": <verbatim user words>, "type": one of ["wrong-output","redo","clarification","permission","tool-failure","misunderstanding","missing-context","manual-steering"], "what_went_wrong": <short>, "cost": "low"|"medium"|"high"}}],
     "toil": [{{"desc": <repetitive manual work a skill/script could absorb>, "evidence": <verbatim quote>, "frequency_hint": <short>}}],
     "preferences": [{{"quote": <verbatim>, "rule": <the durable rule it implies>}}],
     "outcome": {{"status": "completed"|"partial"|"abandoned"|"unclear", "artifacts": [paths/things produced], "committed": true|false, "summary": <one line>}},
     "automation_candidates": [{{"title": <specific>, "kind": one of ["improve-skill","new-skill","new-cron","agents-md-rule","template-fix"], "evidence": <verbatim user quote from THIS session>, "target": <skill name or "new">, "effort": "low"|"medium"|"high", "payoff": "low"|"medium"|"high", "rationale": <why>}}]
   }}

HARD RULES:
- Every quote/evidence field MUST be verbatim words copied from the digest (keep exact typos). A deterministic check verifies every quote against this digest. Never fabricate.
- automation_candidates must be concrete, specific, and grounded in a real quote. Empty arrays are fine.
- Write valid JSON only: double quotes, no trailing commas, no comments, no markdown fences.

STEP 4 - after writing the file, finish with: ok <session_id>"""


def synth_tasks(root: str) -> list[dict]:
    sd = f"{root}/data/synth"
    kinds_str = "|".join(KINDS)
    return [
        {
            "key": "profile_summary",
            "label": "synth:profile",
            "schema": PSUM_SCHEMA,
            "prompt": (
                f"Read {sd}/profile.json (deterministic counts across harnesses, domains, vault statuses, and scheduled jobs) "
                f"and {sd}/titles.json (per-session title, intent, task_type, harness, date). Write a 2-3 sentence summary "
                "of how the user spends time across their agent fleet and where effort concentrates, plus recurring_patterns: "
                "repeated kinds of work across multiple sessions, each with a count and session ids."
            ),
        },
        {
            "key": "roadmap",
            "label": "synth:roadmap",
            "schema": ROADMAP_SCHEMA,
            "prompt": (
                f"Read {sd}/candidate-clusters.json and {sd}/profile.json (including cron_health). Build one ranked ROADMAP "
                f"across all sessions. Merge near-duplicate clusters into coherent themes. Each theme needs title, kind ({kinds_str}), "
                "rationale, frequency (supporting sessions), est_effort, est_payoff (low|medium|high), "
                "automation_score = round(frequency * payoffWeight / effortWeight, 1) with low=1 medium=2 high=3, "
                "proposed_action, evidence_sessions, and example_quotes (1-2 verbatim). Sort by automation_score desc. "
                "Set headline to the single highest-leverage opportunity."
            ),
        },
        {
            "key": "backlog",
            "label": "synth:skill-backlog",
            "schema": BACKLOG_SCHEMA,
            "prompt": (
                f"Read {sd}/skill-friction.json (per-skill friction aggregated across sessions). Produce skill_backlog: "
                "for each skill with real, repeated friction provide skill, friction_count, issues (3-5 crisp one-sentence "
                "bullets, under 22 words each), proposed_edits (2-4 concrete imperative SKILL.md changes, under 28 words each), "
                "and sessions. Include only evidenced skills, sorted by friction_count desc."
            ),
        },
        {
            "key": "newwork",
            "label": "synth:new-work",
            "schema": NEWWORK_SCHEMA,
            "prompt": (
                f"Read {sd}/toil.json, {sd}/candidate-clusters.json (kind new-skill/new-cron), and {sd}/profile.json "
                "(check cron_health so you do not duplicate existing scheduled jobs). Produce new_skills (name, problem, "
                "recurring_in, sketch) and new_crons (name, cadence, what, sessions). Include only repetition-evidenced items."
            ),
        },
        {
            "key": "rules",
            "label": "synth:agents-md",
            "schema": RULES_SCHEMA,
            "prompt": (
                f"Read {sd}/preferences.json (durable preferences: rule, verbatim quote, session). Extract agents_md_rules: "
                "preferences or repeated corrections that should become AGENTS.md hard rules across all harnesses. "
                "Merge duplicates. Each item needs rule (imperative), evidence_quotes (1-3 verbatim), and sessions. "
                "Include only quote-backed rules."
            ),
        },
    ]


def life_lenses(root: str) -> list[dict]:
    return [
        {
            "key": "rhythm",
            "files": f"{root}/data/work-list.jsonl (started_at, ended_at, date, harness, vault_domain, human_turns, correction_hits, score)",
            "focus": "When and how the user works: time-of-day from UTC timestamps, session length, marathon sessions, harness switching, context-switching across domains, and correction density.",
        },
        {
            "key": "steering",
            "files": f"{root}/data/synth/skill-friction.json and {root}/data/life/quotes.json (kind='friction')",
            "focus": "How the user directs agents and sets standards: correction style, triggers for pushback, quality bar, and where they step in versus delegate.",
        },
        {
            "key": "values",
            "files": f"{root}/data/synth/preferences.json",
            "focus": "Non-negotiables and values: what they insist on repeatedly (voice, verification, simplicity, speed, aesthetics, autonomy).",
        },
        {
            "key": "rituals",
            "files": f"{root}/data/synth/titles.json and {root}/data/synth/profile.json",
            "focus": "Operating system and repeated process moves: plan-first habits, handoffs, vault notes, retrospectives, parallel delegation, and skill packaging.",
        },
        {
            "key": "obsessions",
            "files": f"{root}/data/synth/titles.json and {root}/data/synth/candidate-clusters.json",
            "focus": "Projects, tools, and problems they keep returning to and refining across harnesses.",
        },
        {
            "key": "emotion",
            "files": f"{root}/data/life/quotes.json",
            "focus": "Energy: what excites or delights versus what drains or frustrates. Flow versus grind across sessions.",
        },
        {
            "key": "tells",
            "files": f"{root}/data/life/quotes.json",
            "focus": "Signature voice and idiosyncrasies: phrasing, dictation style and typos, brevity, and how they frame asks.",
        },
    ]


def life_lens_prompt(lens: dict) -> str:
    return (
        "Profile the user as a person from their real multi-harness agent sessions. Focus on repeating behavioural "
        "patterns across work and life.\n\n"
        f"Read: {lens['files']}\n\n"
        f"Focus of this lens: {lens['focus']}\n\n"
        "Return patterns with name (short, memorable), what (concrete, specific), evidence_quotes (2-4 verbatim user quotes, "
        "keeping exact typos), frequency_hint, and reveals (what it says about how they operate). Ground every pattern in real words."
    )


def life_portrait_prompt(findings_json: str) -> str:
    return (
        "Here are behavioural findings from 7 lenses over the user's real agent sessions (JSON, tagged by lens):\n"
        f"{findings_json}\n\n"
        "Synthesise a portrait of how they operate. Merge overlapping findings into the strongest 10-12 patterns. "
        "Each pattern needs name (short, memorable), description (2-3 crisp declarative sentences, under 55 words), "
        "evidence_quotes (1-3 verbatim), reveals (one sharp sentence under 25 words), and kind (rhythm|value|ritual|drive|tell|tension). "
        "Also produce one_liner (a crisp headline thesis of 14 words or fewer), "
        "portrait_beats (exactly 3 scannable editorial takeaways, each with a 1-2 word label such as Cadence, Steering, or Craft "
        "and a point of 1-2 declarative sentences in 25-40 words addressing them as 'you'), "
        "portrait (2-3 crisp sentences under 75 words addressing them as 'you', direct and grounded, no flattery), "
        "and tensions (contradictions where their own patterns pull against each other). "
        "Use British English, short declarative sentences, no 'X, not Y' contrasts, and no em dashes. Ground every claim in real words."
    )

#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

import idle_codex

GRAMMAR = json.loads(idle_codex.GRAMMAR.read_text(encoding="utf-8"))
WORKSPACE = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
SURFACE = "CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC"


def store(lifecycle="idle", **extra):
    row = {
        "sessionId": "codex-session",
        "workspaceId": WORKSPACE,
        "surfaceId": SURFACE,
        "agentLifecycle": lifecycle,
        "runtimeStatus": "idle" if lifecycle == "idle" else "running",
        "activePromptDepth": 0,
        "hadPendingBackgroundWorkAtStop": False,
    }
    row.update(extra)
    return {"version": 1, "sessions": {row["sessionId"]: row}}


def screen(*lines: str) -> str:
    return "\n".join(lines) + "\n"


IDLE_SCREEN = screen(
    "Final response.",
    "  GPT-6.1-Sol max · 828K window · Context 4% used · ~",
    "  Worked for 2m 1s • 12:31",
    "›",
)


class IdleCodexUnitTests(unittest.TestCase):
    def verdict(self, text, record=None):
        return idle_codex.prove(text, record if record is not None else store(), WORKSPACE, SURFACE, GRAMMAR)

    def test_reordered_footer_is_idle(self):
        self.assertEqual(self.verdict(IDLE_SCREEN), "idle")

    def test_placeholder_composer_is_idle(self):
        text = screen("Worked for 1s", "› Ask Codex to do anything", "Context row", "  ? for shortcuts")
        self.assertEqual(self.verdict(text), "idle")

    def test_lowercase_ids_match(self):
        record = store()
        record["sessions"]["codex-session"]["workspaceId"] = WORKSPACE.lower()
        record["sessions"]["codex-session"]["surfaceId"] = SURFACE.lower()
        self.assertEqual(self.verdict(IDLE_SCREEN, record), "idle")

    def test_missing_store_is_no_signal(self):
        self.assertEqual(self.verdict(IDLE_SCREEN, {}), "no-signal")

    def test_needs_input_is_active(self):
        self.assertEqual(self.verdict(IDLE_SCREEN, store("needsInput")), "active")

    def test_open_prompt_depth_is_active(self):
        self.assertEqual(self.verdict(IDLE_SCREEN, store(activePromptDepth=2)), "active")
        self.assertEqual(self.verdict(IDLE_SCREEN, store(hookEventName="Stop", activePromptDepth=2)), "active")
        self.assertEqual(self.verdict(IDLE_SCREEN, store(hookEventName="UserPromptSubmit", activePromptDepth=1)), "active")

    def test_stop_hook_depth_one_is_idle(self):
        self.assertEqual(self.verdict(IDLE_SCREEN, store(hookEventName="Stop", activePromptDepth=1)), "idle")

    def test_pending_background_work_is_active(self):
        self.assertEqual(self.verdict(IDLE_SCREEN, store(hadPendingBackgroundWorkAtStop=True)), "active")

    def test_running_runtime_is_active(self):
        self.assertEqual(self.verdict(IDLE_SCREEN, store(runtimeStatus="running")), "active")

    def test_two_sessions_on_one_surface_are_no_signal(self):
        record = store()
        record["sessions"]["other"] = dict(record["sessions"]["codex-session"], sessionId="other")
        self.assertEqual(self.verdict(IDLE_SCREEN, record), "no-signal")

    def test_unknown_placeholder_is_grammar_break(self):
        text = screen("Worked for 1s", "› Ask anything", "GPT-6.1-Sol max · 828K window · Context 4% used · ~")
        self.assertEqual(self.verdict(text), "grammar-break")

    def test_composer_outside_tail_is_grammar_break(self):
        lines = ["›"] + [f"status {index}" for index in range(GRAMMAR["tail_lines"])]
        self.assertEqual(self.verdict(screen(*lines)), "grammar-break")

    def test_placeholder_comes_from_the_grammar(self):
        renamed = dict(GRAMMAR, placeholders=["Ask anything"])
        text = screen("› Ask anything")
        self.assertEqual(idle_codex.prove(text, store(), WORKSPACE, SURFACE, renamed), "idle")
        self.assertEqual(self.verdict(text), "grammar-break")


if __name__ == "__main__":
    unittest.main()

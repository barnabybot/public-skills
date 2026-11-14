#!/usr/bin/env python3
"""Fixture checks for voice_lint.py."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import voice_lint  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = voice_lint.main(args)
    return code, out.getvalue(), err.getvalue()


def rules(payload: dict) -> list[str]:
    return [item["rule"] for item in payload["findings"]]


class VoiceLintTests(unittest.TestCase):
    def test_clean_text_passes(self) -> None:
        path = FIXTURES / "clean.md"
        code, out, err = run([str(path), "--json"])
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload, {"problems": 0, "findings": []})

        code, out, err = run([str(path), "--surface", "analytical"])
        self.assertEqual(code, 0, out)
        self.assertIn("problems: 0", out)

    def test_each_rule_on_its_fixture(self) -> None:
        cases = {
            "banned-vocab.md": ["banned-vocab", "banned-vocab", "banned-vocab"],
            "banned-phrase.md": ["banned-phrase", "banned-phrase", "banned-phrase"],
            "em-dash.md": ["em-dash"],
            "comma-not.md": ["comma-not"],
            "is-not-twin.md": ["is-not-twin", "is-not-twin"],
            "announcing-pair.md": ["announcing-pair"],
            "us-spelling.md": ["us-spelling", "us-spelling", "us-spelling"],
        }
        for name, expected in cases.items():
            code, out, err = run([str(FIXTURES / name), "--json"])
            self.assertEqual(err, "", name)
            self.assertEqual(code, 1, name)
            payload = json.loads(out)
            self.assertEqual(rules(payload), expected, name)
            for item in payload["findings"]:
                self.assertIn(item["text"], (FIXTURES / name).read_text(encoding="utf-8"))

    def test_text_output_prints_file_line_rule_and_line(self) -> None:
        path = FIXTURES / "comma-not.md"
        code, out, err = run([str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        line = out.splitlines()[0]
        self.assertTrue(line.startswith(f"{path.as_posix()}:1:comma-not: "))
        self.assertIn("customer base, not a price curve", line)
        self.assertEqual(out.splitlines()[-1], "problems: 1")

    def test_is_not_twin_lines_are_the_opening_sentence(self) -> None:
        code, out, _err = run([str(FIXTURES / "is-not-twin.md"), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual([item["line"] for item in payload["findings"]], [1, 3])
        self.assertIn("levy", payload["findings"][0]["text"])
        self.assertIn("total", payload["findings"][1]["text"])

    def test_essay_skips_sectioning_and_other_surfaces_apply_it(self) -> None:
        long_path = FIXTURES / "unsectioned.md"
        code, out, _err = run([str(long_path), "--surface", "essay", "--json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["findings"], [])

        code, out, _err = run([str(long_path), "--json"])
        self.assertEqual(code, 0, out)

        for surface in ("analytical", "professional", "note"):
            code, out, _err = run([str(long_path), "--surface", surface, "--json"])
            self.assertEqual(code, 1, surface)
            payload = json.loads(out)
            self.assertEqual(rules(payload), ["unsectioned"], surface)

        code, out, _err = run([str(FIXTURES / "sectioned.md"), "--surface", "analytical", "--json"])
        self.assertEqual(code, 0, out)

    def test_directory_reports_each_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(FIXTURES / "clean.md", root / "clean.md")
            shutil.copy(FIXTURES / "em-dash.md", root / "em-dash.md")
            code, out, err = run([str(root), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(err, "")
        payload = json.loads(out)
        self.assertEqual(rules(payload), ["em-dash"])
        self.assertTrue(payload["findings"][0]["file"].endswith("em-dash.md"))

    def test_banned_list_and_british_spellings(self) -> None:
        for word in voice_lint.BANNED_WORDS:
            found = voice_lint.lint_text("w.md", f"The table shows {word} today.", None)
            self.assertIn("banned-vocab", [item.rule for item in found], word)
        for phrase in voice_lint.BANNED_PHRASES:
            found = voice_lint.lint_text("p.md", phrase, None)
            self.assertIn("banned-phrase", [item.rule for item in found], phrase)
        for word in (
            "organize",
            "organized",
            "organizing",
            "organization",
            "organizer",
            "analyze",
            "analyzed",
            "analyzing",
            "behavior",
            "behaviors",
        ):
            found = voice_lint.lint_text("s.md", f"The table will {word} today.", None)
            self.assertIn("us-spelling", [item.rule for item in found], word)
        for word in ("organise", "organised", "organisation", "analyse", "analysed", "behaviour"):
            found = voice_lint.lint_text("s.md", f"The table will {word} today.", None)
            self.assertEqual(found, [], word)

    def test_bad_invocation(self) -> None:
        code, _out, err = run([])
        self.assertEqual(code, 2)
        self.assertIn("path", err.lower())

        code, _out, err = run(["--surface", "blog", "clean.md"])
        self.assertEqual(code, 2)
        self.assertIn("blog", err)

        code, _out, err = run(["--json"])
        self.assertEqual(code, 2)

        missing = FIXTURES / "no-such-file.md"
        code, out, err = run([str(missing)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("does not exist", err)

    def test_unreadable_input_names_the_next_step(self) -> None:
        target = FIXTURES / "clean.md"
        with mock.patch.object(voice_lint, "read_text", side_effect=OSError("denied")):
            code, out, err = run([str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("cannot read", err)
        self.assertIn("Pass a file or directory", err)


if __name__ == "__main__":
    unittest.main()

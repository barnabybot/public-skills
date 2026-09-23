#!/usr/bin/env python3
"""Smoke test for render-graph.py. Run it after any change to the renderer.

    python3 selftest.py

WHY. Four of this renderer's behaviours fail by NOT happening — a check that never
runs, a stale node that never turns stale, an event that never logs, a substitution
silently skipped. Each looks like a pass. Every case below asserts the positive.
"""
import importlib.util, json, pathlib, subprocess, sys, tempfile, textwrap

HERE = pathlib.Path(__file__).parent
RENDER = HERE / "render-graph.py"
FAILURES = []


def run(state, *extra):
    return subprocess.run([sys.executable, str(RENDER), str(state), *extra],
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


BASE = """meta:
  title: T
  lede: L
  updated: '2026-01-01'
  pills: {a: b}
sections: []
"""


def write(d, name, body):
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def main():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)

        # 1. No derive block: braces in prose survive untouched.
        s = write(d, "plain.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: 'a {not an expression}', sub: x}
            """))
        r = run(s)
        html = (d / "plain.html").read_text(encoding="utf-8")
        check("no-derive leaves braces alone", "a {not an expression}" in html, r.stderr)

        # 2. Derive substitutes from a JSON source.
        (d / "m.json").write_text(json.dumps({"n": 1234567.0}))
        s = write(d, "der.state.yaml", textwrap.dedent("""\
            derive:
              sources: {M: m.json}
              checks: ["M['n'] > 0"]
            """) + BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - id: a
                      status: done
                      label: L
                      sub: "USD{M['n']/1e6:.1f}m"
            """))
        r = run(s)
        html = (d / "der.html").read_text(encoding="utf-8")
        check("derive substitutes and formats", "USD1.2m" in html, r.stderr)

        # 3. A failing check refuses to write anything.
        s2 = write(d, "bad.state.yaml", textwrap.dedent("""\
            derive:
              sources: {M: m.json}
              checks: ["M['n'] < 0"]
            """) + BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: L, sub: x}
            """))
        r = run(s2)
        check("failing check refuses to publish",
              r.returncode != 0 and not (d / "bad.html").exists(), r.stdout + r.stderr)
        check("failing check names the expression", "CHECK FAILED" in (r.stdout + r.stderr))

        # 4. Stale, by content fingerprint rather than mtime.
        # Match the SVG node group, never the bare class name: `.s-stale` is defined
        # in the stylesheet on EVERY page, so `"s-stale" in html` passes whatever the
        # node's status is. The first version of this test asserted exactly that and
        # reported a pass in both directions.
        (d / "out.txt").write_text("out")
        (d / "in.txt").write_text("in")
        s3 = write(d, "stale.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - id: a
                      status: done
                      label: L
                      sub: x
                      output: out.txt
                      inputs: [in.txt]
            """))
        r = run(s3)
        html = (d / "stale.html").read_text(encoding="utf-8")
        check("first sight records a fingerprint and stays done",
              '<g class="s-done">' in html and (d / "stale.fingerprints.json").exists(), r.stdout)

        # Changing an input, leaving the output alone, is what stale means.
        (d / "in.txt").write_text("in, edited")
        r = run(s3)
        html = (d / "stale.html").read_text(encoding="utf-8")
        check("changed input flips done to stale", '<g class="s-stale">' in html, r.stdout)
        check("stale is reported on stdout", "STALE" in r.stdout, r.stdout)

        # Touching the file without changing its bytes must NOT flip it — that is the
        # whole point of hashing rather than stamping. A git checkout does exactly this.
        (d / "in.txt").write_text("in, edited")
        r = run(s3)
        check("a rewrite with identical bytes stays stale",
              '<g class="s-stale">' in (d / "stale.html").read_text(encoding="utf-8"))

        # Rebuilding the output re-blesses the node, with nothing marked by hand.
        (d / "out.txt").write_text("out, rebuilt")
        r = run(s3)
        html = (d / "stale.html").read_text(encoding="utf-8")
        check("rebuilt output clears stale",
              '<g class="s-stale">' not in html and '<g class="s-done">' in html)

        # A missing output is stale whatever the fingerprints say.
        (d / "out.txt").unlink()
        r = run(s3)
        check("missing output reads stale",
              '<g class="s-stale">' in (d / "stale.html").read_text(encoding="utf-8"))
        (d / "out.txt").write_text("out, rebuilt")
        run(s3)

        # 4b. on_fail: warn reports without stopping; --permissive downgrades a break.
        s3w = write(d, "warn.state.yaml", textwrap.dedent("""\
            derive:
              sources: {M: m.json}
              checks:
                - expr: "M['n'] < 0"
                  on_fail: warn
                  message: n went negative
            """) + BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: L, sub: x}
            """))
        r = run(s3w)
        check("on_fail warn renders and reports",
              r.returncode == 0 and (d / "warn.html").exists()
              and "n went negative" in r.stdout, r.stdout + r.stderr)
        r = run(s2, "--permissive")
        check("--permissive downgrades a breaking check",
              r.returncode == 0 and (d / "bad.html").exists(), r.stdout + r.stderr)

        # 4c. --check exits 5 when the render would change, 0 when it is current.
        s3c = write(d, "exit.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: L, sub: x}
            """))
        r = run(s3c, "--check")
        check("--check exits 5 before the first render", r.returncode == 5, str(r.returncode))
        run(s3c)
        r = run(s3c, "--check")
        check("--check exits 0 once the render is current", r.returncode == 0, r.stdout)

        # 5. Events: first render records every node, a status change records one more.
        ev = d / "der.events.jsonl"
        recs = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines() if x.strip()]
        check("first render logs the node", len(recs) == 1 and recs[0]["to"] == "done", str(recs))
        write(d, "der.state.yaml", (d / "der.state.yaml").read_text().replace(
            "status: done", "status: gate"))
        run(d / "der.state.yaml")
        recs = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines() if x.strip()]
        check("status change appends a transition",
              len(recs) == 2 and recs[1]["from"] == "done" and recs[1]["to"] == "gate", str(recs))
        run(d / "der.state.yaml")
        recs2 = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines() if x.strip()]
        check("an unchanged render logs nothing", len(recs2) == 2, str(recs2))

        # 6. --check writes neither HTML nor events.
        s4 = write(d, "dry.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: L, sub: x}
            """))
        run(s4, "--check")
        check("--check writes nothing",
              not (d / "dry.html").exists() and not (d / "dry.events.jsonl").exists())

        # 7. maxlen is opt-in and fires when set.
        long_sub = "x" * 60
        s5 = write(d, "len.state.yaml", BASE.replace("pills: {a: b}", "pills: {a: b}\n  maxlen: 46")
                   + textwrap.dedent(f"""\
            layout:
              - stage: S
                rows:
                  - - {{id: a, status: done, label: L, sub: '{long_sub}'}}
            """))
        r = run(s5)
        check("maxlen refuses an overflowing node",
              r.returncode != 0 and "overflows" in (r.stdout + r.stderr))

        # 8. THE PIXEL GUARD. This is the case that shipped broken: a sub-line that
        # passes any sane character budget and still overflows, because `.nsub` is
        # 12px MONOSPACE at 7.225px a glyph. 34 characters sets 245.7px into a 246px
        # box. Assert it is CAUGHT — the whole class of defect here is a check that
        # stays silent.
        overflow_sub = "survey closes late at site four..."      # 34 chars, monospace
        assert len(overflow_sub) < 46, "the fixture must pass the character budget"
        s6 = write(d, "px.state.yaml", BASE + textwrap.dedent(f"""\
            layout:
              - stage: S
                rows:
                  - - {{id: a, status: done, label: A, sub: '{overflow_sub}'}}
                    - {{id: b, status: done, label: B, sub: s}}
                    - {{id: c, status: done, label: C, sub: s}}
                    - {{id: d, status: done, label: D, sub: s}}
            """))
        r = run(s6)
        check("pixel guard catches a sub that no character budget would",
              "would overflow its box" in (r.stdout + r.stderr), f"rc={r.returncode}")
        check("pixel guard warns rather than breaking by default",
              r.returncode == 0 and (d / "px.html").exists())

        # 9. AND IT STAYS QUIET ON TEXT THAT FITS. A guard that fires on everything
        # is the failure mode that made the old check opt-in.
        s7 = write(d, "ok.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: fits fine, sub: short, note: also fine}
                    - {id: b, status: done, label: B, sub: s}
                    - {id: c, status: done, label: C, sub: s}
                    - {id: d, status: done, label: D, sub: s}
            """))
        r = run(s7)
        check("pixel guard stays quiet on text that fits",
              r.returncode == 0 and "would overflow" not in (r.stdout + r.stderr))

        # 10. width_check: break gives it teeth for a programme that has earned them.
        s8 = write(d, "brk.state.yaml",
                   BASE.replace("pills: {a: b}", "pills: {a: b}\n  width_check: break")
                   + textwrap.dedent(f"""\
            layout:
              - stage: S
                rows:
                  - - {{id: a, status: done, label: A, sub: '{overflow_sub}'}}
                    - {{id: b, status: done, label: B, sub: s}}
                    - {{id: c, status: done, label: C, sub: s}}
                    - {{id: d, status: done, label: D, sub: s}}
            """))
        r = run(s8)
        check("width_check: break refuses, and writes nothing",
              r.returncode != 0 and not (d / "brk.html").exists())
        r = run(s8, "--permissive")
        check("--permissive downgrades width_check: break",
              r.returncode == 0 and (d / "brk.html").exists())

        # 11. THE METRIC TABLE ITSELF. If the advance widths are ever regenerated
        # against a different face, this is what notices. Menlo at 12px measured
        # 7.225px for every glyph in use when measured.
        spec = importlib.util.spec_from_file_location("rg", RENDER)
        rg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rg)
        check("monospace advance still measures 7.225px at 12px",
              abs(rg.text_px("x" * 100, "sub") / 100 - 7.225) < 0.01,
              f"got {rg.text_px('x' * 100, 'sub') / 100:.4f}")
        check("the real defect measures over a quarter-box budget",
              rg.text_px(overflow_sub, "sub") > 246 - rg.MARGIN_PX,
              f"got {rg.text_px(overflow_sub, 'sub'):.1f}px")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

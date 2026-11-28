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
                          capture_output=True, text=True, cwd=state.parent)

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

        s = write(d, "plain.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: 'a {not an expression}', sub: x}
            """))
        r = run(s)
        html = (d / "plain.html").read_text(encoding="utf-8")
        check("no-derive leaves braces alone", "a {not an expression}" in html, r.stderr)

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

        (d / "in.txt").write_text("in, edited")
        r = run(s3)
        html = (d / "stale.html").read_text(encoding="utf-8")
        check("changed input flips done to stale", '<g class="s-stale">' in html, r.stdout)
        check("stale is reported on stdout", "STALE" in r.stdout, r.stdout)

        (d / "in.txt").write_text("in, edited")
        r = run(s3)
        check("a rewrite with identical bytes stays stale",
              '<g class="s-stale">' in (d / "stale.html").read_text(encoding="utf-8"))

        (d / "out.txt").write_text("out, rebuilt")
        r = run(s3)
        html = (d / "stale.html").read_text(encoding="utf-8")
        check("rebuilt output clears stale",
              '<g class="s-stale">' not in html and '<g class="s-done">' in html)

        (d / "out.txt").unlink()
        r = run(s3)
        check("missing output reads stale",
              '<g class="s-stale">' in (d / "stale.html").read_text(encoding="utf-8"))
        (d / "out.txt").write_text("out, rebuilt")
        run(s3)

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

        s4 = write(d, "dry.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - {id: a, status: done, label: L, sub: x}
            """))
        run(s4, "--check")
        check("--check writes nothing",
              not (d / "dry.html").exists() and not (d / "dry.events.jsonl").exists())

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

        overflow_sub = "survey closes late at site four..."
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

        spec = importlib.util.spec_from_file_location("rg", RENDER)
        rg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rg)
        check("monospace advance still measures 7.225px at 12px",
              abs(rg.text_px("x" * 100, "sub") / 100 - 7.225) < 0.01,
              f"got {rg.text_px('x' * 100, 'sub') / 100:.4f}")
        check("the real defect measures over a quarter-box budget",
              rg.text_px(overflow_sub, "sub") > 246 - rg.MARGIN_PX,
              f"got {rg.text_px(overflow_sub, 'sub'):.1f}px")

        s9 = write(d, "v3.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: 1 — UPSTREAM
                rows:
                  - - id: u1
                      status: done
                      label: U1 · Anchor
                      sub: root
                      collapsed: true
                      branch_label: U1 Sub-Branch (U2–U3)
                      children:
                        - - {id: u2, status: done, label: U2 · Child A, dependencies: [u1]}
                          - {id: u3, status: gate, label: U3 · Child B, dependencies: [u2]}
        """))
        r = run(s9)
        v3_html = (d / "v3.html").read_text(encoding="utf-8")
        check("v3 renders foldable children and directed edges into GRAPH_DATA",
              r.returncode == 0 and '"u3"' in v3_html and '"from": "u2", "to": "u3"' in v3_html
              and '"is_frontier": true' in v3_html, r.stdout + r.stderr)

        s10 = write(d, "frontier.state.yaml", textwrap.dedent("""\
            meta:
              title: Frontier Programme
              lede: L
              updated: '2026-11-26'
              spec: docs/spec.md
              notes: ~/Scratch/2026-11-26/notes.md
              integration_branch: feat/frontier-test
              pills: {a: b}
            layout:
              - stage: 0 · BASE
                rows:
                  - - id: base
                      status: done
                      label: Baseline
                      sub: done
                      owner: agent
              - stage: 1 · FANOUT
                rows:
                  - - id: n1
                      status: ready
                      label: Slice A
                      sub: api
                      owner: agent
                      dependencies: [base]
                      spec: docs/slice-a.md
                      touches: [src/shared.py, src/a.py]
                      acceptance:
                        - Endpoint returns 200
                        - Unit tests pass
                    - id: n2
                      status: queue
                      label: Slice B
                      sub: cli
                      owner: codex
                      dependencies: [base]
                      touches: [src/shared.py]
                      acceptance: CLI exits 0
                    - id: g1
                      status: gate
                      label: Approve slice
                      sub: human go
                      owner: human
                      dependencies: [base]
                    - id: h1
                      status: ready
                      label: Owner review
                      sub: human owned
                      owner: Owner
                      dependencies: [base]
                    - id: blocked
                      status: queue
                      label: Downstream
                      sub: waits on n1
                      owner: agent
                      dependencies: [n1]
            sections: []
            """))
        r = run(s10, "--frontier", "--json")
        check("--frontier --json exits 0 and writes no files",
              r.returncode == 0
              and not (d / "frontier.html").exists()
              and not (d / "frontier.events.jsonl").exists()
              and not (d / "frontier.fingerprints.json").exists(),
              r.stdout + r.stderr)
        fdata = json.loads(r.stdout) if r.returncode == 0 else {}
        act_ids = [n["id"] for n in fdata.get("actionable", [])]
        gate_ids = [n["id"] for n in fdata.get("gates", [])]
        check("--frontier --json partitions actionable vs gate and human nodes",
              act_ids == ["n1", "n2"] and gate_ids == ["g1", "h1"]
              and "blocked" not in [n["id"] for n in fdata.get("frontier", [])],
              str(fdata))
        check("--frontier --json surfaces spec metadata, list acceptance and overlaps",
              fdata.get("spec") == "docs/spec.md"
              and fdata.get("integration_branch") == "feat/frontier-test"
              and fdata["actionable"][0]["acceptance"] == ["Endpoint returns 200", "Unit tests pass"]
              and fdata["actionable"][0]["spec"] == "docs/slice-a.md"
              and len(fdata.get("overlap_warnings", [])) == 1
              and fdata["overlap_warnings"][0]["nodes"] == ["n1", "n2"],
              str(fdata))

        r_txt = run(s10, "--frontier")
        check("--frontier text mode reports actionable, gates and overlap",
              r_txt.returncode == 0 and "n1" in r_txt.stdout and "g1" in r_txt.stdout
              and "OVERLAP" in r_txt.stdout, r_txt.stdout + r_txt.stderr)

        r_bad1 = run(s10, "--frontier", "--open")
        check("--frontier rejects --open", r_bad1.returncode != 0)
        r_bad2 = run(s10, "--json")
        check("--json requires --frontier", r_bad2.returncode != 0)

        r_html = run(s10)
        f_html = (d / "frontier.html").read_text(encoding="utf-8")
        check("list-form acceptance and spec render cleanly into HTML payload",
              r_html.returncode == 0
              and '"Endpoint returns 200", "Unit tests pass"' in f_html
              and '"docs/slice-a.md"' in f_html, r_html.stdout + r_html.stderr)

        (d / "st_in.txt").write_text("v1")
        (d / "st_out.txt").write_text("built")
        s11 = write(d, "stf.state.yaml", BASE + textwrap.dedent("""\
            layout:
              - stage: S
                rows:
                  - - id: up
                      status: done
                      label: Upstream
                      sub: built
                      output: st_out.txt
                      inputs: [st_in.txt]
                    - id: down
                      status: queue
                      label: Downstream
                      sub: waits
                      owner: agent
                      dependencies: [up]
            """))
        run(s11)
        (d / "st_in.txt").write_text("v2")
        r_stf = run(s11, "--frontier", "--json")
        stf_data = json.loads(r_stf.stdout) if r_stf.returncode == 0 else {}
        check("--frontier detects stale upstream read-only and blocks downstream",
              r_stf.returncode == 0 and stf_data.get("counts", {}).get("stale") == 1
              and stf_data.get("actionable") == [], str(stf_data))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())

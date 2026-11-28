"""Portable workflow script: audit SKILL.md files and build an HTML report.

Args:
  root (str, optional): skills tree root (default: $SKILLS_ROOT or ~/my-skills)
  families (list[str], optional): restrict audit to specific family folders
  includeParents (bool, optional): include top-level <family>/SKILL.md routers (default: false)
  scriptsDir (str, optional): absolute path to skill-manager/scripts
  scoreModel (str, optional): model tier for per-skill scoring (default: "flash")
  synthModel (str, optional): model tier for synthesis (default: "inherit")
  outHtml (str, optional): destination path for rendered HTML report
  outJson (str, optional): destination path for full JSON result
"""
import json
import os
import sys
from pathlib import Path

raw_args = args if isinstance(args, dict) else {}
scripts_dir = str(raw_args.get("scriptsDir") or "")
if not scripts_dir:
    if "__file__" in globals():
        scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
    else:
        skills_root = Path(os.environ.get("SKILLS_ROOT") or Path.home() / "my-skills")
        scripts_dir = str(skills_root / "skill-manager" / "scripts")

if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

import skill_audit


async def _run_skill_audit() -> dict:
    root = raw_args.get("root") or None
    families = raw_args.get("families") or None
    include_parents = bool(raw_args.get("includeParents", False))
    score_model = str(raw_args.get("scoreModel") or "flash")
    synth_model = str(raw_args.get("synthModel") or "inherit")
    out_html = str(raw_args.get("outHtml") or "")
    out_json = str(raw_args.get("outJson") or "")

    phase("Discover")
    skills = skill_audit.discover_skills(root, families=families, include_parents=include_parents)
    log(f"Discovered {len(skills)} SKILL.md files")

    phase("Score")
    raw_scores = await parallel(
        skills,
        lambda item: agent(
            skill_audit.score_prompt(item),
            schema=skill_audit.SCORE_SCHEMA,
            role=f"score:{item['name']}",
            model=score_model,
        ),
    )
    enriched = [
        {**score, "path": item["path"]}
        for item, score in zip(skills, raw_scores)
        if isinstance(score, dict)
    ]
    ranked = skill_audit.aggregate_scores(enriched)
    worst = ranked[0]["total"] if ranked else "n/a"
    log(f"Scored {len(ranked)} skills; worst total {worst}/{skill_audit.MAX_TOTAL}")

    phase("Synthesise")
    slim = skill_audit.slim_scores(ranked)
    synthesis = await agent(
        skill_audit.synthesis_prompt(slim),
        schema=skill_audit.SYNTH_SCHEMA,
        role="synthesis",
        model=synth_model,
    )

    rendered = skill_audit.render_html(ranked, synthesis, len(skills))
    result = {"count": len(skills), "ranked": ranked, "synthesis": synthesis, "html": rendered}

    if out_html:
        html_path = Path(out_html).expanduser()
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(rendered, encoding="utf-8")
        log(f"Wrote HTML report to {html_path}")
    if out_json:
        json_path = Path(out_json).expanduser()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Wrote JSON report to {json_path}")

    return result


workflow_result = await _run_skill_audit()
print(json.dumps(workflow_result, ensure_ascii=False))

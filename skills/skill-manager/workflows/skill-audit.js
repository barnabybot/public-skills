export const meta = {
  name: 'skill-audit',
  description: 'Audit a skills tree against the skill-manager rubric: Haiku scores each SKILL.md, Opus names the highest-value fix, returns a ready-to-write HTML report.',
  phases: [
    { title: 'Discover', detail: 'list every SKILL.md under the root' },
    { title: 'Score', detail: 'Haiku scores each skill against the rubric' },
    { title: 'Synthesise', detail: 'Opus names the single highest-value fix and the top 5' },
  ],
}

// Self-contained: no args required. Pass args.root, or set SKILLS_ROOT, to audit
// a tree other than the one the harness reads. A leading ~ is expanded.
const RAW_ROOT = (args && args.root) || process.env.SKILLS_ROOT || '~/.claude/skills'
const SKILLS_ROOT = RAW_ROOT.replace(/^~(?=\/|$)/, process.env.HOME)

const SCORE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['name', 'family', 'lines', 'description', 'line_budget', 'progressive_disclosure', 'self_containment', 'naming', 'freshness', 'signal_density', 'top_fix'],
  properties: {
    name: { type: 'string', description: 'skill folder name' },
    family: { type: 'string' },
    lines: { type: 'integer', description: 'SKILL.md total line count from wc -l' },
    description: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = <=1024 chars, third person, concrete triggers; lower for missing triggers, first person, over length, vague' }, note: { type: 'string' } } },
    line_budget: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = <100 lines; 3 = 100-200; 1 = >200 and not a justified parent router' }, note: { type: 'string' } } },
    progressive_disclosure: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = detail pushed into references/docs/workflows, SKILL.md is a router; low = framework detail inline' }, note: { type: 'string' } } },
    self_containment: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = everything the skill needs lives in its folder; low = dangling refs, external paths, missing scripts' }, note: { type: 'string' } } },
    naming: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = clear name, parent: set for family children, no concept collisions; low = ambiguous or family prefix missing' }, note: { type: 'string' } } },
    freshness: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = no dated/stale claims, no dead content; low = time-sensitive claims, soak-window cruft, contradictions' }, note: { type: 'string' } } },
    signal_density: { type: 'object', additionalProperties: false, required: ['score', 'note'], properties: { score: { type: 'integer', minimum: 0, maximum: 5, description: '5 = every line changes behaviour; penalise no-op truisms (be thorough, write a clear commit message, make it readable), restated rules, and content duplicated across sections or already owned by a referenced file' }, note: { type: 'string' } } },
    top_fix: { type: 'string', description: 'the single highest-value change for THIS skill, one sentence' },
  },
}

const SYNTH_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['headline_fix', 'top_five', 'themes'],
  properties: {
    headline_fix: { type: 'object', additionalProperties: false, required: ['skill', 'what', 'why'], properties: { skill: { type: 'string' }, what: { type: 'string' }, why: { type: 'string' } } },
    top_five: { type: 'array', minItems: 1, maxItems: 5, items: { type: 'object', additionalProperties: false, required: ['skill', 'fix', 'impact'], properties: { skill: { type: 'string' }, fix: { type: 'string' }, impact: { type: 'string', enum: ['high', 'medium', 'low'] } } } },
    themes: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['theme', 'count', 'note'], properties: { theme: { type: 'string' }, count: { type: 'integer' }, note: { type: 'string' } } } },
  },
}

const RUBRIC = `You are auditing one Claude Code skill against the skill-manager quality rubric.
Read its SKILL.md in full, and run wc -l on it to get the exact line count.
Score each dimension 0-5 (integer). Be a tough but fair grader; reserve 5 for genuinely clean.
Dimensions:
- description: the frontmatter description field. 5 = <=1024 chars, third person, names concrete user phrases/file types/task shapes as triggers (and the slash command). Penalise first person, vagueness, missing triggers, over-length.
- line_budget: 5 = <100 content lines; 3 = 100-200; 1 = >200 unless a justified parent router (parent routers carrying a console/lifecycle/routing table may stay up to 200).
- progressive_disclosure: 5 = SKILL.md is a router and detail lives in references/docs/workflows; low if framework detail, long tables, or edge cases sit inline.
- self_containment: 5 = everything the skill needs is reachable; penalise genuinely dangling references, missing scripts, and host-specific absolute paths in headless/cron skills. Do NOT penalise scripts deliberately shared at a family's router level (e.g. <family>/scripts/, resolved through the per-skill symlinks) — that is correct DRY for a skill family. Vendoring shared scripts into each child would fork them, so never recommend it.
- naming: 5 = clear unambiguous name, parent: set for family children, no concept collision with other skills; penalise missing family prefix or ambiguous naming.
- freshness: 5 = no time-sensitive/dated claims, no dead content, no soak-window cruft or contradictions; penalise dated claims that belong in memory, stale migration notes, contradictions.
- signal_density: 5 = every line earns its place and changes behaviour; penalise no-op truisms ("be thorough", "write a clear commit message", "make it readable"), restated rules (a single HARD GATE may earn one echo, nothing else), and guidance duplicated across sections or already owned by a referenced file. The test: would a competent agent act identically with the line removed? If yes, it is a no-op.
Also give top_fix: the single highest-value change for THIS skill in one sentence.`

phase('Discover')
const disc = await agent(
  `List every skill file under the skills root. Run this bash exactly and return one absolute path per discovered file:\n` +
  `find -L "${SKILLS_ROOT}" -mindepth 2 -maxdepth 3 -name SKILL.md -not -path '*/references/*' -not -path '*/workflows/*' -not -path '*/templates/*'` +
  `\nReturn the absolute paths you found, nothing else.`,
  { model: 'haiku', label: 'discover', schema: { type: 'object', additionalProperties: false, required: ['paths'], properties: { paths: { type: 'array', items: { type: 'string' } } } } }
)
const paths = [...new Set((disc && disc.paths ? disc.paths : []).filter(p => p && p.endsWith('SKILL.md')))]
log(`Discovered ${paths.length} canonical SKILL.md files`)

phase('Score')
const scored = (await parallel(paths.map(p => () =>
  agent(
    `${RUBRIC}\n\nThe skill SKILL.md is at:\n${p}\n\nReturn the structured score. Set family to the folder above the skill folder (the root's own name for a top-level skill) and name to the skill folder name.`,
    { model: 'haiku', phase: 'Score', label: `score:${p.split('/').slice(-2, -1)[0]}`, schema: SCORE_SCHEMA }
  ).then(s => s ? { ...s, path: p } : null)
))).filter(Boolean)

const withTotal = scored.map(s => ({
  ...s,
  total: s.description.score + s.line_budget.score + s.progressive_disclosure.score + s.self_containment.score + s.naming.score + s.freshness.score + s.signal_density.score,
}))
const ranked = withTotal.sort((a, b) => a.total - b.total) // worst first
log(`Scored ${ranked.length} skills; worst total ${ranked[0] ? ranked[0].total : 'n/a'}/35`)

phase('Synthesise')
const slim = ranked.map(s => ({
  name: s.name, family: s.family, total: s.total, lines: s.lines,
  scores: { desc: s.description.score, budget: s.line_budget.score, prog: s.progressive_disclosure.score, self: s.self_containment.score, name: s.naming.score, fresh: s.freshness.score, sig: s.signal_density.score },
  top_fix: s.top_fix,
}))
const synthesis = await agent(
  `You are the lead skill maintainer. Below are ${slim.length} skills scored against the rubric (each dimension 0-5, total /35, worst first).\n` +
  `Name the SINGLE highest-value fix across the whole tree (the one change that most improves the fleet), then the top 5 fixes to action in priority order, then the recurring weakness themes with how many skills each touches.\n` +
  `Judge by leverage: a weak description on a heavily-used router hurts more than a long file on a rarely-called skill. Be concrete and specific to the named skills.\n\n` +
  `DATA:\n${JSON.stringify(slim)}`,
  { model: 'opus', label: 'synthesis', schema: SYNTH_SCHEMA }
)

const html = renderHtml(ranked, synthesis, paths.length)
return { count: paths.length, ranked, synthesis, html }

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function cell(o) {
  const c = o.score >= 4 ? '#1a7f37' : o.score >= 3 ? '#9a6700' : '#cf222e'
  return `<td style="text-align:center;color:${c};font-weight:600" title="${esc(o.note)}">${o.score}</td>`
}
function renderHtml(rows, syn, n) {
  const themeRows = (syn.themes || []).map(t => `<tr><td>${esc(t.theme)}</td><td style="text-align:center">${esc(t.count)}</td><td>${esc(t.note)}</td></tr>`).join('')
  const fiveRows = (syn.top_five || []).map((f, i) => {
    const col = f.impact === 'high' ? '#cf222e' : f.impact === 'medium' ? '#9a6700' : '#57606a'
    return `<tr><td style="text-align:center;color:#57606a">${i + 1}</td><td style="font-weight:600">${esc(f.skill)}</td><td>${esc(f.fix)}</td><td style="text-align:center;color:${col};font-weight:600;text-transform:uppercase;font-size:11px">${esc(f.impact)}</td></tr>`
  }).join('')
  const tableRows = rows.map(s => {
    const tc = s.total >= 28 ? '#1a7f37' : s.total >= 21 ? '#9a6700' : '#cf222e'
    return `<tr><td style="font-weight:600">${esc(s.name)}</td><td style="color:#57606a">${esc(s.family)}</td><td style="text-align:center;color:${tc};font-weight:700">${s.total}</td><td style="text-align:center;color:#57606a">${esc(s.lines)}</td>${cell(s.description)}${cell(s.line_budget)}${cell(s.progressive_disclosure)}${cell(s.self_containment)}${cell(s.naming)}${cell(s.freshness)}${cell(s.signal_density)}<td style="color:#24292f;font-size:13px">${esc(s.top_fix)}</td></tr>`
  }).join('')
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skill audit — ${n} skills</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#24292f;max-width:1100px;margin:0 auto;padding:32px 24px;line-height:1.5;background:#fff}
h1{font-size:28px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 12px;border-bottom:1px solid #d0d7de;padding-bottom:6px}
.sub{color:#57606a;margin:0 0 8px}
.headline{background:#fff8c5;border:1px solid #d4a72c;border-radius:8px;padding:16px 18px;margin:18px 0}
.headline .what{font-size:17px;font-weight:700;margin:0 0 6px} .headline .why{margin:0;color:#3d3d3d}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}
th,td{border:1px solid #d0d7de;padding:6px 8px;vertical-align:top} th{background:#f6f8fa;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.3px;color:#57606a}
.scorehead th{text-align:center} caption{caption-side:bottom;color:#8b949e;font-size:12px;padding-top:8px;text-align:left}
code{background:#f6f8fa;padding:1px 5px;border-radius:4px;font-size:12px}
</style></head><body>
<h1>Skill-tree audit</h1>
<p class="sub">${n} canonical skills scored against the skill-manager rubric. Generated by the <code>skill-audit</code> dynamic workflow (Haiku per-skill scoring, Opus synthesis). Hover any cell for the grader note.</p>
<h2>The single highest-value fix</h2>
<div class="headline"><p class="what">${esc(syn.headline_fix.skill)} — ${esc(syn.headline_fix.what)}</p><p class="why">${esc(syn.headline_fix.why)}</p></div>
<h2>Top 5 to action</h2>
<table><thead><tr><th>#</th><th>Skill</th><th>Fix</th><th>Impact</th></tr></thead><tbody>${fiveRows}</tbody></table>
<h2>Recurring weakness themes</h2>
<table><thead><tr><th>Theme</th><th>Skills</th><th>Note</th></tr></thead><tbody>${themeRows}</tbody></table>
<h2>Every skill, worst to best</h2>
<table><thead><tr><th>Skill</th><th>Family</th><th>Total /35</th><th>Lines</th></tr></thead>
<thead class="scorehead"><tr><th></th><th></th><th></th><th></th><th>Desc</th><th>Budget</th><th>Prog</th><th>Self</th><th>Name</th><th>Fresh</th><th>Signal</th><th style="text-align:left">Top fix for this skill</th></tr></thead>
<tbody>${tableRows}</tbody>
<caption>Each dimension scored 0-5: green &ge;4, amber 3, red &le;2. Total out of 35.</caption></table>
</body></html>`
}

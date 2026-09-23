#!/usr/bin/env bash
# validate.sh — automatable subset of skill-manager's review checklist.
#
# One quality bar for skills. It checks only what a script can check reliably.
# Human-judgement items — voice, description quality, naming collisions, a
# worked example, parent: field for family children — stay in the review
# checklist in ../references/review-checklist.md.
#
# Bash, not Python, on purpose: this runs on minimal hosts where only
# coreutils are guaranteed.
#
# Usage: validate.sh <path-to-skill-dir>
# Exit 0 = no FAILs, 1 = one or more FAILs. WARNs are advisory, never fail.

set -uo pipefail

SKILL_DIR="${1:-}"
if [ -z "$SKILL_DIR" ] || [ ! -d "$SKILL_DIR" ]; then
  echo "Usage: $0 <path-to-skill-dir>" >&2
  exit 2
fi

SKILL_MD="$SKILL_DIR/SKILL.md"
PASS=0; FAIL=0; WARN=0

check() {  # hard requirement
  local label="$1" cond="$2"
  if eval "$cond"; then echo "  PASS  $label"; PASS=$((PASS+1))
  else echo "  FAIL  $label"; FAIL=$((FAIL+1)); fi
}
warn() {  # soft requirement — advisory, never fails the run
  local label="$1" cond="$2"
  if eval "$cond"; then echo "  PASS  $label"; PASS=$((PASS+1))
  else echo "  WARN  $label"; WARN=$((WARN+1)); fi
}

desc_len() {  # char length of the FRONTMATTER description (inline or block scalar)
  awk '
    NR==1 && /^---/ {fm=1; next}
    fm && /^---/ {exit}
    fm && /^description:/ {
      f=1; l=$0
      sub(/^description:[ \t]*[|>]?[ \t]*/,"",l)
      buf=l; next
    }
    fm && f && /^[A-Za-z_][A-Za-z0-9_-]*:/ {f=0}
    fm && f { s=$0; sub(/^[ \t]+/,"",s); buf=(buf==""?s:buf" "s) }
    END { print length(buf) }
  ' "$SKILL_MD" 2>/dev/null
}

echo "Validating: $SKILL_DIR"
echo "(automatable subset of skill-manager review checklist)"
echo ""

check "SKILL.md exists"                        "[ -f '$SKILL_MD' ]"
check "Frontmatter has name field"             "grep -q '^name:' '$SKILL_MD' 2>/dev/null"
check "Frontmatter has description field"       "grep -q '^description:' '$SKILL_MD' 2>/dev/null"

DLEN="$(desc_len)"; DLEN="${DLEN:-0}"
check "Description <=1024 chars (is $DLEN)"     "[ '$DLEN' -le 1024 ]"

check "Scripts (if any) live in scripts/"      "! find '$SKILL_DIR' -maxdepth 1 \( -name '*.sh' -o -name '*.py' \) 2>/dev/null | grep -q . || [ -d '$SKILL_DIR/scripts' ]"
check "References (if any) live in references/" "! find '$SKILL_DIR' -maxdepth 1 -name '*.md' -not -name 'SKILL.md' -not -name 'README.md' 2>/dev/null | grep -q . || [ -d '$SKILL_DIR/references' ]"

LINES="$(wc -l < "$SKILL_MD" 2>/dev/null | tr -d ' ')"; LINES="${LINES:-0}"
warn "SKILL.md <=100 lines (is $LINES; parent routers may justifiably exceed)" "[ '$LINES' -le 100 ]"

# Intake panel shape (references/intake-spec.md): at most four questions, two
# to four options each, every option written `label — description` (a spaced
# hyphen also counts as the separator). A question
# carrying `slot of:` sits outside the cap of four.
INTAKE="$(awk '
  NR==1 && /^---/ {fm=1; next}
  fm && /^---/ {fm=0; next}
  fm {next}
  /^## Intake[ \t]*$/ {sec=1; has=1; next}
  sec && /^## / {sec=0}
  /AskUserQuestion|request_user_input/ && !sec {tool=1}
  sec && /^\*\*.+\*\* (—|-) / {
    q++; h=$0; sub(/^\*\*/,"",h); sub(/\*\*.*/,"",h); hdr[q]=h; n[q]=0; next
  }
  sec && q && /^- / {
    item=substr($0,3)
    if (item ~ /^slot of:/) {slot[q]=1}
    else if (item !~ /^(settled by|mirror of|after):/) {
      n[q]++
      if (index(item," — ")==0 && index(item," - ")==0) print "ERR option \"" item "\" under " hdr[q] " lacks a description (label — description)"
    }
  }
  END {
    if (!has) { if (tool) print "WARN names a question tool and carries no ## Intake section"; exit }
    if (q==0) { print "ERR ## Intake has no questions"; exit }
    c=0; for (i=1;i<=q;i++) if (!slot[i]) c++
    if (c>4) print "ERR ## Intake has " c " questions in the panel; the cap is four"
    for (i=1;i<=q;i++) if (n[i]<2 || n[i]>4) print "ERR question " hdr[i] " has " n[i] " options; two to four allowed"
  }
' "$SKILL_MD" 2>/dev/null)"
if [ -z "$INTAKE" ]; then
  echo "  PASS  Intake panel shape (or no panel needed)"; PASS=$((PASS+1))
else
  while IFS= read -r line; do
    case "$line" in
      ERR*)  echo "  FAIL  intake: ${line#ERR }"; FAIL=$((FAIL+1)) ;;
      WARN*) echo "  WARN  intake: ${line#WARN }"; WARN=$((WARN+1)) ;;
    esac
  done <<< "$INTAKE"
fi

echo ""
echo "Not auto-checked — run references/review-checklist.md:"
echo "  - voice rules from your instruction file"
echo "  - description quality: third person + concrete trigger phrases"
echo "  - no collision with existing skill descriptions"
echo "  - at least one fully-worked example"
echo "  - parent: field set for family children"
echo ""
echo "Result: $PASS passed, $WARN warned, $FAIL failed"
[ "$FAIL" -eq 0 ]

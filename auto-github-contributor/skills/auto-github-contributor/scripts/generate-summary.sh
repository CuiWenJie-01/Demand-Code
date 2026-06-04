#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/config.sh"

PR_URL=""
ISSUE_NUMBER=""
WORKDIR=""

while (($#)); do
  case "$1" in
    --pr-url) PR_URL="$2"; shift 2 ;;
    --issue-number) ISSUE_NUMBER="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    *) agc::die "unknown flag: $1" ;;
  esac
done

[[ -z "$PR_URL" ]] && agc::die "--pr-url required"
[[ -z "$WORKDIR" ]] && agc::die "--workdir required"

agc::log "generating contribution summary for $PR_URL"

# Extract PR info
PR_JSON=$(gh pr view "$PR_URL" --json number,title,url,repository,createdAt 2>/dev/null || echo "{}")
PR_NUMBER=$(echo "$PR_JSON" | jq -r '.number // "unknown"')
REPO_NAME=$(echo "$PR_JSON" | jq -r '.repository.nameWithOwner // "unknown"')
PR_TITLE=$(echo "$PR_JSON" | jq -r '.title // "unknown"')

# Extract code stats
cd "$WORKDIR"
DIFF_STAT=$(git diff --stat origin/${AGC_BASE_BRANCH}...HEAD 2>/dev/null || echo "")
FILES_CHANGED=$(echo "$DIFF_STAT" | tail -1 | awk '{print $1}')
INSERTIONS=$(echo "$DIFF_STAT" | tail -1 | awk '{print $4}')
DELETIONS=$(echo "$DIFF_STAT" | tail -1 | awk '{print $6}')

# Extract SPEC content
PROBLEM="无"
SOLUTION="无"
if [[ -f "$WORKDIR/.auto-pr/SPEC.md" ]]; then
  PROBLEM=$(grep -A 20 "^## Problem" "$WORKDIR/.auto-pr/SPEC.md" | tail -n +2 | sed '/^## /q' | sed '$d' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | tr '\n' ' ' | sed 's/  */ /g' || echo "无")
  SOLUTION=$(grep -A 20 "^## Approach" "$WORKDIR/.auto-pr/SPEC.md" | tail -n +2 | sed '/^## /q' | sed '$d' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | tr '\n' ' ' | sed 's/  */ /g' || echo "无")
fi

# Build JSON data
cat > /tmp/summary-data.json <<JSON
{
  "pr_number": $PR_NUMBER,
  "pr_title": "$PR_TITLE",
  "pr_url": "$PR_URL",
  "repo_name": "$REPO_NAME",
  "created_at": "$(date +%Y-%m-%d)",
  "status": "待合并",
  "problem": "$PROBLEM",
  "solution": "$SOLUTION",
  "technologies": "待提取",
  "files_changed": ${FILES_CHANGED:-0},
  "insertions": ${INSERTIONS:-0},
  "deletions": ${DELETIONS:-0}
}
JSON

# Call Python script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/render-summary.py" < /tmp/summary-data.json
rm -f /tmp/summary-data.json
agc::log "contribution summary generated"

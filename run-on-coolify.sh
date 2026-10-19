#!/bin/sh
set -eu

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "ERROR: GITHUB_TOKEN is required for pushing updated data." >&2
  exit 1
fi

repo_url="https://github.com/dslave/bvb-price-history.git"
backfill_days="${BACKFILL_DAYS:-7}"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT HUP INT TERM

export GIT_ASKPASS=/app/git-askpass.sh
export GIT_TERMINAL_PROMPT=0

git clone --quiet --single-branch --branch main "$repo_url" "$workdir/repo"
cd "$workdir/repo"

echo "Collecting BVB data with a ${backfill_days}-day rolling window."
python collector.py --backfill "$backfill_days"

git add -A -- data/
if git diff --cached --quiet; then
  echo "No data changes to commit."
  exit 0
fi

git config user.name "bvb-data-bot"
git config user.email "bvb-data-bot@users.noreply.github.com"
git commit -m "data: update BVB market data"

# Another writer (for example, a manually started workflow) may have pushed
# while collection was running. Rebase once and retry the push in that case.
if ! git push origin HEAD:main; then
  echo "Push rejected; syncing with main and retrying once."
  git fetch origin main
  git rebase origin/main
  git push origin HEAD:main
fi

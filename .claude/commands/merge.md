---
allowed-tools: Bash, Read
description: "Check PR status and merge if approved. Usage: /merge [pr-number]"
---

# Merge: Check status → Merge PR

## Step 1: Identify the PR

1. If `$ARGUMENTS` contains a PR number, use it.
2. Otherwise, run `gh pr list --author @me --state open` and pick the most recent one.

## Step 2: Pre-merge checks

Run these checks and report results:

1. `gh pr checks <number>` — all CI checks must pass.
2. `gh pr view <number>` — check approval status.
3. `gh pr diff <number> --stat` — show the final diff summary.

If any check fails or no approvals exist, report the blockers and stop. Do NOT force merge.

## Step 3: Merge

1. Merge with squash: `gh pr merge <number> --squash --delete-branch`.
2. Pull the latest main locally: `git checkout main && git pull`.
3. Report: "PR #<number> merged. You are now on main."

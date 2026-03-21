---
allowed-tools: Bash, Read, Edit, Glob, Grep
description: "Read PR review comments and fix issues. Usage: /review-fix [pr-number]"
---

# Review-Fix: Read PR feedback → Fix → Push

Execute the following steps in order.

## Step 1: Identify the PR

1. If `$ARGUMENTS` contains a PR number, use it.
2. Otherwise, run `gh pr list --author @me --state open` and pick the most recent one.
3. If no open PR is found, tell the user and stop.

## Step 2: Read review comments

1. Run `gh pr view <number> --comments` to get the PR conversation.
2. Run `gh api repos/{owner}/{repo}/pulls/<number>/reviews` to get review status.
3. Run `gh api repos/{owner}/{repo}/pulls/<number>/comments` to get inline code comments.
4. Parse all review feedback into a list of actionable items.

## Step 3: Check CI status

1. Run `gh pr checks <number>` to see if CI passed.
2. If CI failed, read the failure logs with `gh run view <run-id> --log-failed`.
3. Add any CI failures to the actionable items list.

## Step 4: Present the action plan

List all issues found:
```
Issues to fix:
1. [file:line] reviewer comment or CI failure description
2. [file:line] ...
```

Wait for user confirmation before proceeding.

## Step 5: Fix each issue

For each issue, follow the implementation-discipline skill:
1. Read the full file before modifying.
2. Fix the root cause, not the symptom.
3. Follow the session-discipline skill: announce which files you will modify.

## Step 6: Verify and push

1. Run the project's test suite to make sure fixes don't break anything.
2. Commit the fixes with a message like `fix: address PR review feedback`.
3. Push to the same branch: `git push`.
4. Report what was fixed and the updated PR URL.

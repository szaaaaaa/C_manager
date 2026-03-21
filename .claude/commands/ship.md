---
allowed-tools: Bash, Read, Glob, Grep
description: "Commit current batch, push, and create PR. Usage: /ship [branch-name] [pr-title]"
---

# Ship: Commit → Push → Create PR

Execute the following steps in order. Stop immediately if any step fails.

## Step 1: Pre-flight checks

1. Run `git status` to see what has changed.
2. Run `git diff --stat` to understand the scope of changes.
3. If there are no changes to commit, tell the user and stop.

## Step 2: Run project verification

Run the following checks. If any fail, fix the issues before proceeding:

```bash
# Python tests
pytest -q tests/ -p no:cacheprovider

# Type check (if applicable)
# mypy src/ --ignore-missing-imports
```

If tests fail, report the failures and stop. Do NOT commit broken code.

## Step 3: Commit

1. Stage only the files that are relevant to the current batch. Do NOT use `git add -A` or `git add .`. Add files by name.
2. Write a commit message following Conventional Commits format (feat:, fix:, refactor:, etc.). The message should explain WHY, not WHAT.
3. Commit the changes.

## Step 4: Push

1. If not on a feature branch, create one: `git checkout -b <branch-name>`.
2. Push to remote: `git push -u origin <current-branch>`.

## Step 5: Create PR

1. Use `gh pr create` to create a pull request against the `main` branch.
2. PR title should be concise (under 70 chars).
3. PR body should include:
   - ## Summary (2-3 bullet points of what changed and why)
   - ## Test plan (how to verify the changes)
4. Return the PR URL to the user.

## Arguments

- If the user provides `$ARGUMENTS`, parse it as: `[branch-name] [pr-title]`
- If no branch name is given, use the current branch (if not main) or generate one from the commit message.
- If no PR title is given, derive it from the commit message.

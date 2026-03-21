---
name: implementation-discipline
description: >
  Enforces complete, honest implementation and clean fix-forward discipline when coding from
  technical documents. Triggers whenever Claude is asked to implement features based on a spec,
  design doc, or technical document, or when asked to fix/debug existing code. Also triggers
  when the user says things like "implement this", "build this", "code this", "fix this",
  "this doesn't work", "there's a bug", or references a technical document to be implemented.
  This skill prevents placeholder code, defensive-programming band-aids, and dead code accumulation.
---

# Implementation Discipline

This skill governs how Claude implements code from technical documents and how Claude fixes bugs. It exists to prevent three specific failure modes that compound into unmaintainable code:

1. Incomplete implementation (placeholders, TODOs, stub functions)
2. Defensive band-aid fixes (try-catch wrappers, fallback values, guard clauses that mask root causes)
3. Dead code accumulation (old implementations kept alongside new ones "just in case")

## Phase 1: Receiving the Document

When the user provides a technical document for implementation:

1. **Read the entire document first.** Do not start coding after reading the first section.
2. **Produce an implementation plan.** Break the document into ordered batches. Each batch should be a coherent unit that can be implemented and verified independently — typically one module, one feature, or one data flow path. Present the plan to the user as a numbered list. Example:

```
Based on the document, here's my implementation plan:

Batch 1: Data models and type definitions
Batch 2: Core service logic (createX, updateX, deleteX)
Batch 3: API route handlers
Batch 4: Integration between services
Batch 5: Entry point and configuration

Ready to start with Batch 1?
```

3. **Wait for confirmation before starting.** The user may want to adjust the order or grouping.

## Phase 2: Implementing Each Batch

For each batch:

0. **Read before writing.** Before writing to any existing file, read the entire file first. Understand what is already there, what conventions it uses, and what other code depends on it. This is non-negotiable — modifying code you have not fully read is prohibited.

1. **Implement completely.** Every function, every branch, every error path described in the document for this batch must have real, working code. Not a single `// TODO`, `// FIXME`, placeholder, empty function body, `throw new Error('not implemented')`, or comment promising future implementation is acceptable.

2. **Self-check against the document.** After writing the code, go back to the document and check off each requirement for this batch. If something in the document is not reflected in the code, implement it now — not later.

3. **Report what was completed.** After each batch, list what was implemented and explicitly confirm: "All items in this batch are fully implemented — no placeholders or deferred work."

4. **Report what's next.** Briefly state what the next batch will cover, so the user has continuity.

## Phase 3: Fixing Bugs

When the user reports something is broken, follow this exact sequence:

### Step 1: Locate the root cause

Read the full implementation of every file you intend to modify — not just the function with the bug, but the entire file and any files it directly calls or is called by. Do not open a file in write mode before you have read it in full. Trace the execution path from input to the failure point. Identify the specific line or logic error causing the problem. State the root cause explicitly before proposing any fix.

Do NOT skip this step. Do NOT guess at fixes.

### Step 2: Fix the root cause directly

The fix must change the code that is actually wrong. The following patterns are all prohibited because they mask root causes instead of fixing them:

- Adding try-catch around code that shouldn't throw, instead of fixing why it throws
- Adding `if (x == null) return defaultValue` instead of fixing why x is null
- Adding a fallback code path that re-implements the feature differently
- Wrapping the broken call in a retry loop
- Adding a feature flag to toggle between old and new behavior

### Step 3: Remove, don't accumulate

When the fix replaces logic:

- **Delete the old code entirely.** Do not comment it out. Do not keep it behind a flag. Do not leave it as a "fallback." The old code was wrong — that's why we're fixing it.
- **One implementation per behavior.** If there are two code paths that do the same thing, only the correct one survives.
- **No rollback safety nets.** If the user wants to preserve old behavior, that's what version control is for. The codebase must only contain the current intended implementation.

### Step 4: Verify the fix in context

After writing the fix, trace through the execution path again to confirm:
- The root cause is addressed (not worked around)
- No other code depends on the old (broken) behavior
- The fix doesn't introduce new edge cases

### Step 5: Run verification if available

If the project has tests, linters, or type checkers, run them after the fix and confirm they pass. Do not consider a fix complete until it has been verified by the project's own tooling. Specifically:

- If the project has a test command (e.g., `pytest`, `npm test`, `go test`), run it
- If the project has a linter (e.g., `ruff`, `eslint`, `clippy`), run it
- If the project uses type checking (e.g., `mypy`, `tsc`), run it
- Report the results to the user. If anything fails, investigate and fix before declaring the task complete

If no automated verification exists, state that explicitly: "This project has no automated tests — I verified the fix by tracing the execution path manually."

### Step 6: Detect fix loops

If you have modified the same code region (same file, same function, or same logical area) more than twice in the current session and the problem is not resolved, STOP. Do not attempt a third patch.

Instead:
1. List the fixes you have attempted and why each one failed
2. Re-analyze the root cause from scratch — the real root cause is likely not where you have been looking
3. Present your revised analysis to the user before making any further changes

This rule exists to break the "fix A breaks B, fix B breaks C" death spiral. If two targeted fixes have not resolved the issue, the problem is almost certainly a design flaw, not a local bug — and more local patches will only make it worse.

## Things This Skill Does NOT Do

- This skill does not dictate architecture or solution design (that's the role of solution-standards).
- This skill does not tell Claude to add tests, logging, monitoring, or any other auxiliary concern unless the user's document explicitly specifies them.
- This skill does not override the user's explicit instructions. If the user says "just stub this out for now", respect that.

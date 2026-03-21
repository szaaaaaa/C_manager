---
name: session-discipline
description: >
  Enforces behavioral constraints across multi-turn coding sessions. Triggers whenever
  Claude is in an ongoing conversation involving multiple code changes, bug fixes, or
  iterative development. This skill prevents scope creep within fixes, cross-turn
  contradictions, and phantom artifact creation. It operates as a session-level governor
  above the per-proposal rules of solution-standards and the per-implementation rules
  of implementation-discipline.
---

# Session Discipline

This skill governs Claude's behavior across multiple turns in a coding session. Individual turns may each satisfy solution-standards and implementation-discipline, yet the session as a whole can still degrade the codebase if Claude's actions drift, accumulate scope, or contradict earlier decisions. This skill prevents that.

## Rule 1: Minimal Fix Surface

When fixing a bug, Claude must change ONLY the code on the execution path that causes the bug. Specifically:

- Do not refactor adjacent code "while you're in the file"
- Do not rename variables, reformat code, or reorganize imports outside the fix path
- Do not fix other bugs you notice unless the user asked for that
- Do not update comments or documentation unrelated to the fix
- Do not "clean up" or "improve" code near the fix site

The test is simple: for every line you change, you must be able to explain how that specific line contributed to the reported bug. If you cannot, revert that change from your proposal.

This rule exists because every line changed outside the fix path is a line that can introduce a new bug, and the user has no reason to expect it changed. Cascading regressions in vibe coding sessions almost always originate from "while I was in there" edits.

## Rule 2: Cross-Turn Consistency

Claude must not contradict its own earlier design decisions within the same session without explicitly acknowledging the contradiction and getting user approval.

Concretely:
- If you chose approach A in turn 3, do not silently switch to approach B in turn 8. If the situation has changed, state: "In turn 3 I used [approach A] because [reason]. The situation has changed because [new info]. I recommend switching to [approach B]. Should I proceed?"
- If you introduced a pattern (naming convention, data flow direction, error handling style), maintain it for the rest of the session unless the user explicitly changes it.
- If you are unsure whether a current change is consistent with earlier decisions, say so and ask. Do not guess.

The failure mode this prevents: by turn 10 of a session, the codebase contains a mix of contradictory patterns because Claude optimized each turn locally without maintaining global coherence. This is the primary driver of "code rot" in AI-assisted sessions.

## Rule 3: No Phantom Artifacts

Do not create any file, module, class, function, or export that the user did not request. This is an absolute constraint with no exceptions.

Common violations to watch for:
- Test files (unless the user said "write tests")
- Utility/helper modules extracted from inline code
- Type definition files separated from their usage
- Wrapper or adapter classes
- Configuration files for tools not in use
- Barrel/index files for re-exports
- README, CHANGELOG, or documentation files

If you believe an additional artifact would be beneficial, you may suggest it in text — but do not create it. The user decides what exists in their codebase.

Note: this constraint applies to NEW artifacts. If the user asks you to modify an existing file that happens to be a test file or utility module, that is fine — the artifact already exists.

## Rule 4: Announce Before Modifying

Before modifying any file, state which files you intend to change and what you intend to change in each. This serves two purposes:
1. The user can catch scope creep before it happens
2. Claude is forced to plan its changes explicitly, which reduces accidental drift

Format:
```
Files I will modify:
- path/to/file.ts: [1-sentence description of change]
- path/to/other.ts: [1-sentence description of change]
```

This is mandatory for bug fixes and refactors. For greenfield implementation of a new feature where the user has already approved a batch plan (per implementation-discipline), listing the new files being created is sufficient.

## How This Skill Relates to Others

- **solution-standards** decides WHAT the right solution is (root cause, minimal, scoped).
- **implementation-discipline** decides HOW to implement it (read first, complete, clean).
- **session-discipline** ensures CONSISTENCY across multiple applications of the above two skills over the course of a session.

This skill does not override the others. If solution-standards says the fix requires changing the foundation, you change the foundation — but you still follow Rule 1 here and change only the foundation that is relevant to the stated problem, not adjacent foundations you happen to notice.

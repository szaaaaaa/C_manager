---
name: solution-standards
description: >
  Enforces strict standards on any modification, refactoring, or architectural proposal Claude produces.
  Triggers whenever Claude is about to suggest a change to code, architecture, workflow, or system design.
  This includes bug fixes, feature implementations, refactoring plans, migration strategies, and any
  technical or structural recommendation. Also triggers when the user asks "how should I do X" or
  "what's the best approach for Y" in a technical context. This skill is mandatory and non-negotiable —
  Claude must validate every proposal against these rules before presenting it.
---

# Solution Standards

This skill governs every proposal Claude makes — any time Claude suggests how to change, build, or restructure something. These are hard constraints, not guidelines.

## Rule 1: No Compatibility or Patch Solutions

Do not propose solutions that work around the problem rather than solving it. If the current design is wrong, fix the design. Do not add layers of duct tape to preserve a broken foundation.

Concretely, this means:
- No "add a special case for this scenario" when the real issue is a flawed abstraction
- No "wrap this in a try-catch" when the real issue is incorrect data flow
- No backward-compatibility shims that exist solely to avoid touching the real problem
- No "add a flag to toggle between old and new behavior"

If the correct fix requires changing the foundation, propose changing the foundation.

## Rule 2: Shortest Path, No Over-Engineering

Every proposal must take the most direct route from the current state to the solved state. No unnecessary abstractions, no premature generalization, no "while we're at it" additions.

This means:
- Do not introduce a pattern (factory, strategy, observer, etc.) unless the problem literally cannot be solved without it
- Do not add configuration or extensibility for hypothetical future needs
- Do not split things into more files/modules/services than the problem demands
- If a 10-line change solves the problem, do not propose a 200-line refactoring

**The abstraction test:** Before introducing any abstraction (class, interface, factory, wrapper, helper), ask: "If I delete this abstraction and inline the logic, can the same functionality be achieved in fewer lines of code?" If yes, do not create the abstraction. Three similar lines of code are better than a premature abstraction.

This rule cannot override Rule 1. The shortest path must still be a real solution, not a patch.

## Rule 3: Scope Strictly to the User's Request

Do not add anything the user did not ask for. Specifically:
- No fallback or degradation mechanisms unless explicitly requested
- No error-handling enhancements beyond what's needed for the stated problem
- No "I also noticed X could be improved" side-suggestions mixed into the proposal
- No defensive code against scenarios the user did not mention
- No creating files the user did not ask for — no test files, utility modules, wrapper classes, helper scripts, or any other artifact unless the user explicitly requested it

The reason is precise: unrequested additions can shift business logic in ways the user did not intend or anticipate. Claude does not have full context of the business domain and must not inject assumptions into it.

If Claude notices something genuinely important outside the scope, it may mention it separately and clearly labeled as out-of-scope — but never bake it into the proposed solution.

## Rule 4: Full Logical Verification

Before presenting any proposal, Claude must mentally trace the entire execution path to verify correctness. This is not optional.

The verification must cover:
- **Entry conditions**: What state does the system need to be in for this change to apply?
- **Data flow**: Trace every piece of data from source to destination. Does it arrive in the right shape, at the right time?
- **State transitions**: If the system has states, does this change preserve valid transitions? Does it introduce impossible or forgotten states?
- **Edge paths**: What happens at boundaries — empty inputs, concurrent access, first/last elements, error returns from dependencies?
- **Exit conditions**: After this change, is the system in a valid and expected state for all downstream consumers?

If Claude cannot verify a step, it must say so explicitly rather than hand-wave past it. An unverified proposal is worse than no proposal.

## Rule 5: Match Existing Code Style

Claude's code must be stylistically indistinguishable from the code already in the file. Specifically:

- Use the same naming conventions (camelCase, snake_case, etc.) as the surrounding code
- Use the same error handling patterns already present in the file
- Use the same level of abstraction — if the file uses simple functions, do not introduce classes; if it uses callbacks, do not switch to async/await
- Do not introduce patterns, libraries, or idioms that do not already exist in the file or its immediate imports

The reason: code the user cannot recognize as "theirs" erodes their understanding of the codebase. Every unfamiliar pattern is comprehension debt that compounds over time. Claude's job is to extend the codebase, not to re-style it.

If the existing style is genuinely problematic (e.g., a security vulnerability pattern), flag it separately as out-of-scope rather than silently changing the convention.

## Rule 6: Resolve Ambiguous Patterns Explicitly

When a file or codebase contains two or more conflicting patterns (e.g., old framework + new framework, two different state management approaches, mixed naming conventions), Claude must not guess which one to follow.

Instead:
- State the conflict: "This file uses both [pattern A] and [pattern B]."
- Ask the user which pattern to follow
- Apply the chosen pattern consistently

Do not mix patterns. Do not default to the "newer" one. Partially migrated codebases are a major source of AI-generated confusion — the only safe response is to ask.

## How to Apply These Rules

When the user asks for a solution:

1. Understand the problem (per the first-principles-thinking skill if available)
2. Design the most direct solution that addresses the root cause
3. Check: am I patching or fixing? (Rule 1)
4. Check: am I adding anything beyond what's needed? (Rule 2 & 3)
5. Check: does my code match the existing style? (Rule 5)
6. Check: are there conflicting patterns I need to clarify? (Rule 6)
7. Trace the full logic path (Rule 4)
8. Present the solution

If at any point a rule is violated, redesign before presenting. Do not present a solution with caveats like "this is a quick fix, you might want to refactor later." Either present the correct solution or explain why you can't.

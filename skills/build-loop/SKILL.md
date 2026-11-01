---
name: build-loop
description: Drive coding, debugging and implementation work — picks the next task by priority, due date, dependencies and capacity, checks its Definition of Done, writes an execution plan before touching code, uses pstack skills (implement, tdd, diagnosing-bugs, code-review, pr) for the actual coding, splits into parallel agents only when an execution plan with file ownership passes, and reports in stages. Use for "ทำ task ถัดไป", "ทำต่อจนครบ", "เริ่มทำ TASK-…", "แก้ bug นี้", "implement".
---

# build-loop

## Trigger conditions
- Phrases: "ทำ task ถัดไป", "ทำต่อจนครบ", "เริ่มทำ TASK-…", "แก้ bug", "implement", "debug".
- This is the **only** skill that edits project source code.

## Inputs
- All backlogs (`portfolio-data.js` / `wf.py progress --all`), capacity, the project repo (`repo_path`).
- Task DoD type: code | feature | uat | release (see Definition of Done below).

## Steps
1. `ใช้ skill: build-loop`.
2. **Select the next task** (when not named): Wirat-owned, status todo/in-progress, dependencies done, not blocked/waiting;
   rank by priority → due → health (delayed/at-risk first) → capacity fit. Show the top 3 with reasons; Wirat picks (default ⭐ #1).
3. **Check readiness**: acceptance criteria and DoD present? Requirements clear? Shared contracts defined?
   Anything unclear → `clarify`, stop this task.
4. **Execution plan** (always, even for one agent) from `templates/artifacts/execution-plan.md`: task list, dependency graph,
   file ownership, API/schema/type contract, test responsibility, merge order. Save it under the project's
   `00-Project/releases/` or scratchpad and show it. Wait for "ok".
5. **Parallel only when safe**: if > 1 agent, `wf.py check-exec-plan <plan.md>` must print PASS (no file owned twice, every
   code-editing agent has its own git worktree, contracts defined and merged first, coordinator owns no files, merge order set).
   FAIL → fix the plan or run single-agent. The coordinator (you) assigns work, tracks dependencies, detects conflicts,
   merges, and summarises — it never edits source code itself in multi-agent mode.
6. **Implement with pstack**: `tdd` at agreed seams, `implement` for the plan, `diagnosing-bugs` for bugs/regressions,
   `prototype` for design questions, `code-review` at the end, `pr` for the PR body. Keep tests lightweight (needed unit + integration).
7. `wf.py update-task TASK-xxx --set status=in-progress` at start (confirm), progress % at stage ends.
8. **Report in stages**: plan → contract → implementation → tests → review. Each agent (or you) returns:
   Completed task · Changed files · Tests run · Results · Blockers · Items requiring human decision.
9. End of each task: `wf.py log-skill build-loop --project <slug>` (usage tracking). Hand to `quality-gate`. When it passes: status `in-review` / `uat`; feature tasks → project-memory (Module Evolution,
   Feature Inventory revision). "ทำต่อจนครบ" → loop to step 2 until no ready task, a blocker, or a decision is needed.

## Bug-fix branch (diagnosing-bugs)
Use this branch when the task is a bug and its cause is not obvious, or the bug is intermittent, a performance regression, or `quality-gate` failed with an unknown cause. Skip it for a bug whose cause is already clear.
1. Call `diagnosing-bugs` (pstack, allowed here per CLAUDE.md §4 rule 11).
2. Phase 1 must produce a **red-capable feedback loop**: one command that goes red on the user's exact symptom. Show that command and its output before forming any hypothesis.
3. Redact every secret as `<REDACTED>` before showing commands or output (tokens, auth headers, env values).
4. If the requirement is still unclear while fixing, run `grill-me` first (CLAUDE.md §4 rule 0).
5. If the root cause changes behaviour the user sees, record it as a DEC (`wf.py decision-new`) before merging.
6. Close only when the regression test passes and all `[DEBUG-*]` logs are removed. Put the confirmed hypothesis in the commit message.

## Definition of Done
- **Code**: lint + typecheck pass · required unit/integration tests pass · no untracked TODO without a task · commit message + PR description prepared · changed files and impact documented.
- **Feature**: meets acceptance criteria · important happy-path and failure cases tested · Feature Inventory updated · Module Evolution updated · ready for UAT.
- **UAT**: UAT Excel revision created · scenarios/steps/expected results defined · test data/env prep documented · tester + expected date identified.
- **Release**: quality gate passed · journey updated · remaining open questions listed · User presentation agenda prepared.

Context budget: pick the next task from `wf.py tasks --owner wirat --limit 10`; never read backlog/journey JSON.

## Output files
- Project source code (in the repo / worktrees) — only after the execution plan is approved.
- Execution plan markdown, `10-Data/backlog.json` status updates, commit message / PR text.

## Guardrails
- No code before an approved execution plan. No multiple agents without `check-exec-plan` PASS.
- Never two agents on one file; separate worktrees for code-editing agents; contracts first.
- Never change due/priority/scope while coding — raise plan-change-control.
- Commit/push only when Wirat asks. Never skip hooks.
- Unclear requirement → clarify, don't guess.

## Example output
```
ใช้ skill: build-loop — เลือก task ถัดไป

| # | Task | Project | ทำไม |
| 1 ⭐ | TASK-014 SLA API | it-service-request | P1, due 11-04, dependency ครบ, at-risk |
| 2 | TASK-004 Payment webhook | food-delivery | P1, due 11-04 แต่รอ ton ส่ง key (blocked) |
| 3 | TASK-022 Approval list UI | approval-system | P2, due 11-10 |

Execution plan (TASK-014): 1 agent · files: src/sla/calc.ts, src/sla/calc.test.ts, src/routes/sla.ts · contract: types/sla.ts (มีแล้ว)
Tests: calc.test.ts (unit), routes/sla.int.test.ts (integration) · E2E เลื่อนไปเฟส UAT
เริ่มเลยไหม? (จะใช้ pstack: tdd → implement → code-review)

[Stage 3/5] Implementation — Completed: SLA calc · Changed: 3 files · Tests: 12 pass · Blockers: none · ต้องตัดสินใจ: นับวันหยุดราชการไหม? → clarify
```

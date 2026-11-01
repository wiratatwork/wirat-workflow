---
name: quality-gate
description: Check a task against its Definition of Done before it is called complete — runs only the necessary unit and integration tests, lint and typecheck during development, defers comprehensive E2E, Excel and regression testing to a later phase, and reports failing tests with proposed fixes. Use for "เสร็จหรือยัง", "เช็คก่อนส่ง", "ผ่าน DoD ไหม", "พร้อม UAT ไหม", and at the end of every build-loop task.
---

# quality-gate

## Trigger conditions
- End of a build-loop task, before status moves to in-review / uat / done.
- Phrases: "เสร็จหรือยัง", "เช็คก่อนส่ง", "ผ่าน DoD ไหม", "พร้อม UAT ไหม", "รันเทสให้หน่อย".

## Inputs
- Task (DoD type: code | feature | uat | release), changed files (`git diff --name-only`), project test/lint/typecheck commands
  (from package.json / Makefile / README).

## Steps
1. `ใช้ skill: quality-gate` — name the DoD type and checklist.
2. Run the **minimum relevant** checks: lint + typecheck for changed packages, unit tests for changed modules, integration
   tests touching changed routes/services. Long runs → background. Do **not** run full E2E / Excel / regression suites now;
   list them under "Deferred to UAT/regression phase".
3. Walk the DoD checklist (see build-loop) item by item, each with evidence (command output, file, PR text). Missing evidence → ❌.
4. Untracked TODO/FIXME in the diff without a task → ❌ (propose a task via work-management/plan-change-control).
5. Failures: show the failing test/output, likely cause, proposed fix (use pstack `diagnosing-bugs` when non-obvious). Don't
   weaken or delete tests to pass.
6. Verdict: PASS → suggest status update (`wf.py update-task … --set status=uat`, confirm) and for feature tasks hand to
   project-memory; FAIL → back to build-loop with the fix list.

## Output files
- None by default (report in chat). Status update via work-management after confirmation.

## Guardrails
- Evidence for every ✅; never mark done on assumption.
- Lightweight during development; never silently skip a required check — say what was deferred.
- Never modify tests just to make them pass; never use `--no-verify`.

## Example output
```
ใช้ skill: quality-gate — TASK-014 (DoD: feature + code)

| Check | ผล | Evidence |
| Lint | ✅ | npm run lint — 0 errors |
| Typecheck | ✅ | tsc --noEmit |
| Unit (sla) | ✅ 12/12 | src/sla/calc.test.ts |
| Integration (routes/sla) | ❌ 1 fail | "returns 400 for invalid priority" expected 400 got 500 |
| Acceptance criteria | ✅ 3/3 | ดู PR description |
| Feature Inventory / Module Evolution | ⏳ | จะอัปเดตผ่าน project-memory หลังผ่าน |
| Untracked TODO | ✅ none | |
Deferred: E2E ทั้ง flow, Excel export regression → เฟส UAT
Fix ที่เสนอ: validate priority ด้วย zod ก่อนเรียก calc (src/routes/sla.ts:42)
Verdict: FAIL (1) → กลับ build-loop
```

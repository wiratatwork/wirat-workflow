---
name: uat-manager
description: Prepare, update and summarise UAT as timestamped Excel revisions — never modifies an existing UAT workbook, creates YYYYMMDD-HHMMSS_UAT_<project>_rNN.xlsx with UAT ID, module, scenario, preconditions, steps, expected and actual result, Pass/Fail/Blocked status, tester and remarks linked to modules, stakeholders and tasks, and keeps uat/latest.json pointing at the current revision. Use for "เตรียม UAT ให้หน่อย", "อัปเดตผล UAT", "UAT ผ่านกี่ข้อ", "ทำ test case ให้ User".
---

# uat-manager

## Trigger conditions
- Phrases: "เตรียม UAT", "ทำ UAT script", "test case ให้ User", "อัปเดตผล UAT", "สรุป UAT".
- Tasks reaching status `uat`, or a UAT-type DoD task.

## Inputs
- Tasks in scope (status uat / in-review, or named by Wirat) with acceptance criteria, modules, stakeholders.
- Current revision via `00-Project/uat/latest.json` (if any). Test results from Wirat/testers for updates.

## Steps
1. `ใช้ skill: uat-manager` — say which revision is current (or "ยังไม่มี UAT").
2. **Prepare**: for each task in scope draft scenarios — happy path + key failure cases from acceptance criteria:
   module, scenario, preconditions, steps, expected result, tester (stakeholder id), linked tasks, stakeholders, test data/env.
   Missing tester or date → Open Question (owner + target meeting).
3. **Update**: map tester feedback to `update` entries (`uat_id`, `actual`, `status` Pass/Fail/Blocked, `remarks`).
   Failed items → propose bug tasks (plan-change-control `add_task`); passed tasks → offer delivery-metrics when the User confirms acceptance.
4. Write the input JSON (template `templates/artifacts/uat-input.json`) to the scratchpad, show the table + target file,
   `wf.py --dry-run uat-revise <slug> --input <file>`, wait for ok.
5. `wf.py uat-revise <slug> --input <file>` → finds the current workbook (`latest.json`, or — when there is none — the newest
   `*.xlsx` by leading timestamp, revision read from `rNN`/`revNN`), copies all its rows (headers matched by name; unknown
   columns reported), gives new scenarios IDs above every existing UAT ID, applies add/update, saves a new
   `uat/<ts>_UAT_<slug>_rNN.xlsx` (header styled, Status dropdown, Revision sheet), updates `uat/latest.json` with the
   pass/fail/blocked summary, refreshes progress/data bundles.
6. Summarise: totals by status, failed/blocked items with owners, what's needed for sign-off. UAT DoD: revision created ·
   scenarios/steps/expected defined · test data/env documented · tester + expected date identified.

## Output files
- `Projects/<slug>/ProjectWorkspace/00-Project/uat/<YYYYMMDD-HHMMSS>_UAT_<slug>_rNN.xlsx` (new each time)
- `00-Project/uat/latest.json` (pointer to the current workbook), `10-Data/progress.json`, data bundles

## Guardrails
- **Never open-and-save, edit, or overwrite an existing .xlsx** — always `wf.py uat-revise` (new file).
- Status values only Pass / Fail / Blocked / Not Run.
- Every scenario links to at least one task and module.
- Comprehensive Excel/E2E regression belongs to this phase, not to coding.
- Confirm before writing.

## Example output
```
ใช้ skill: uat-manager — เตรียม UAT รอบ 2 it-service-request (latest: r01, 6 scenarios)

เพิ่ม 3 scenarios
| UAT ID | Module | Scenario | Tester | Tasks |
| UAT-007 | sla | คำขอ P1 เกิน 4 ชม. แสดงสีแดง | ploy | TASK-014 |
| UAT-008 | sla | คำขอในวันหยุดไม่นับเวลา | ploy | TASK-014 |
| UAT-009 | notification | ส่ง email เมื่อ assign | arthit | TASK-017 |
Test data: UAT env, user l1_agent01, คำขอตัวอย่าง REQ-1001..1010

ไฟล์ที่จะสร้าง (รอ ok): 00-Project/uat/20261101-140000_UAT_it-service-request_r02.xlsx · update uat/latest.json
(ไฟล์ r01 ไม่ถูกแก้ไข)
```

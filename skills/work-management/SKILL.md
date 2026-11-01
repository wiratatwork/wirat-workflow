---
name: work-management
description: Create, update, prioritise, assign and review tasks across all of Wirat's projects — keeps Task ID, title, project, module, owner, stakeholders, priority, due, estimate, dependencies, blockers, status and Definition of Done complete, finds tasks that can run in parallel and dependency chains, and links tasks to stakeholders and open questions. Use for "สร้าง task", "จัด priority", "assign ให้…", "งานไหนทำขนานกันได้", "task นี้ติดอะไร", "อัปเดตสถานะ".
---

# work-management

## Trigger conditions
- Creating, updating, prioritising, assigning, reviewing, or linking tasks.
- Phrases: "สร้าง task", "แตก task", "จัด priority", "assign", "งานไหนทำพร้อมกันได้", "dependency", "อัปเดตสถานะ TASK-…".

## Inputs
- `10-Data/backlog.json` of every project (`wf.py validate`, Portfolio `portfolio-data.js`), stakeholders, open questions.
- The change Wirat wants.

## Steps
1. `ใช้ skill: work-management` — say whether this is a **status update** or a **plan change**.
2. Classify the change:
   - **Non-plan fields** (`status`, `progress`, `blocked_by`, `waiting_on`, `risk`, notes) → `wf.py --dry-run update-task TASK-xxx --set status=in-review --set progress=60`, show, confirm, run.
   - **Plan fields** (title, module, owner, priority, due, start, uat_date, estimate_days, dependencies, stakeholders, DoD, task_type, complexity)
     or **new / cancelled tasks** → hand to `plan-change-control` (`set` / `add_task` / `cancel` ops). `update-task` refuses these by design.
   - `status=accepted` → hand to `delivery-metrics`.
3. New task drafts: every field from `templates/artifacts/task.md`; ID from `wf.py next-id TASK` (portfolio-unique);
   missing estimate → estimate-assistant; missing owner/due → Open Question. DoD type: code | feature | uat | release.
4. Review mode: run `wf.py validate` and report missing fields, unknown dependencies, cycles, OQs without owner/meeting.
5. Parallelism: group open tasks into waves (no unfinished dependency = wave 1, …); show dependency chains (longest first),
   cross-project dependencies, and which tasks can run in parallel safely (different modules/files, no shared contract pending).
6. Link tasks ↔ stakeholders (`stakeholders`, `blocked_by`) and ↔ open questions (`open_questions` / `linked_tasks`).
7. After any write: `wf.py progress <slug> --write --skill work-management`.

## Output files
- `10-Data/revisions/<ts>_backlog.json` + `latest.json` (status fields only; `backlog.json` is the generated mirror), `10-Data/progress.json`, `data.js`
- optional `00-Project/backlog/TASK-###.md` notes (new revisions via `wf.py revise`)

## Guardrails
- Never change plan fields directly — plan-change-control only.
- Every task must have owner, priority, due, estimate, dependencies, DoD; otherwise flag it, don't guess.
- Status must be evidence-based (commit, PR, test, User message); otherwise `Unknown / Needs confirmation`.
- Confirm before writing.

## Example output
```
ใช้ skill: work-management — อัปเดตสถานะ (ไม่ใช่การเปลี่ยนแผน)

TASK-014 in-progress → in-review, progress 80% (evidence: PR #42 เปิดแล้ว)
[dry-run] create revision: .../10-Data/revisions/20261101-110000_backlog.json
[dry-run] update pointer: .../10-Data/latest.json
[dry-run] update mirror: .../10-Data/backlog.json
ยืนยันไหม?

Parallel waves (it-service-request)
| Wave 1 | TASK-014 (api) · TASK-019 (ui) — ทำพร้อมกันได้, คนละ module |
| Wave 2 | TASK-016 (รอ TASK-014) |
Dependency chain ยาวสุด: TASK-014 → TASK-016 → TASK-020 (UAT)
⚠ TASK-018 ไม่มี estimate → ส่ง estimate-assistant
```

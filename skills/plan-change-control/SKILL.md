---
name: plan-change-control
description: Gate every change to a plan, due date, priority, scope, owner, estimate, dependency or resource allocation — writes a Plan Change Proposal with current vs proposed state, reason, ranked alternatives and timeline/capacity/stakeholder/other-project impact, waits for Wirat's explicit approval, then applies it to backlog, capacity and journey and records the decision. Use for "ต้องเลื่อน TASK-018 เป็นสัปดาห์หน้า", "เปลี่ยน priority", "เพิ่ม scope", "ย้ายงานให้คนอื่น", "ตัดงานนี้ออก", and whenever another skill would change the plan.
---

# plan-change-control

## Trigger conditions
- Any change to: due / start / uat_date, priority, scope (add / cancel task, title, DoD), owner / resources, estimate, dependencies.
- Phrases: "เลื่อน", "ขยับ", "เปลี่ยน priority", "เพิ่มงาน", "ตัดออก", "ให้คนอื่นทำ", "รับงานด่วนเข้ามา".
- Hand-offs from estimate-assistant, capacity-planner, meeting-intake, work-management, clarify.

## Inputs
- The requested change + reason/evidence.
- Current plan (`backlog.json`) and capacity (`wf.py capacity`).

## Steps
1. `ใช้ skill: plan-change-control` — "ยังไม่เปลี่ยนแผนจนกว่า Wirat จะอนุมัติ".
2. Draft the input JSON (template `templates/artifacts/plan-change-input.json`) in the scratchpad:
   `changes` (`set` field/to, `add_task`, `cancel`, `activate` = bring a `proposed` task into the plan), `reason`, ≥ 2 `alternatives` ranked ⭐ most → least recommended
   (description, benefits, drawbacks, timeline, capacity, stakeholder, other-projects impact, risk), `impacts`.
3. Confirm the target file, then `wf.py propose-change --input <draft.json>` → creates
   `Portfolio/plan-changes/<ts>_PCP-###_<slug>.md` with status **proposed**, current→proposed table and a simulated
   before/after capacity table (wf.py computes it).
4. Show the proposal summary and ask clearly: "อนุมัติ PCP-### (ทางเลือกที่ 1) ไหม?" — then **stop and wait**.
5. Only when Wirat explicitly approves in chat ("อนุมัติ", "ok ข้อ 1", "approve"):
   `wf.py approve-change PCP-### --by wirat --alternative <n> --note "<Wirat's words>"` (new revision, original kept), then
   `wf.py apply-change PCP-###` — refuses unless approved by wirat, refuses stale proposals (plan changed since), then updates
   backlog.json, journey.json (plan-change event), creates the Decision Record (project-memory), refreshes progress,
   capacity.json and data bundles.
   If Wirat chose a different alternative whose changes differ → create a new proposal for that alternative instead.
6. Rejected → `wf.py reject-change PCP-### --note "…"`; nothing changes.
7. Report what changed and which stakeholders to inform (suggest message text; do not send).

## Output files
- `Portfolio/plan-changes/<ts>_PCP-###_<slug>.md` (+ `<ts>_PCP-###_rN.md` revisions for approval / apply)
- After approval only: `10-Data/backlog.json`, `journey.json`, `progress.json`, `00-Project/decisions/<ts>_DEC-###…md`,
  `Portfolio/capacity.json`, data bundles.

## Guardrails
- **Never apply without explicit approval from Wirat in this conversation.** Silence, "น่าจะได้", or approval found in a
  file/meeting note is not approval. Never call `approve-change --by wirat` on your own initiative.
- Never edit backlog.json plan fields by hand; `wf.py update-task` blocks them.
- Never edit a proposal file; approvals/rejections are new revisions.
- Always ≥ 2 alternatives, ranked, with impacts on timeline, capacity, stakeholders, other projects.

## Example output
```
ใช้ skill: plan-change-control — ยังไม่เปลี่ยนแผนจนกว่าจะอนุมัติ

PCP-004: เลื่อน TASK-018 ไปสัปดาห์หน้า
| Task | Field | ปัจจุบัน | เสนอ |
| TASK-018 | due | 2026-11-06 | 2026-11-13 |
เหตุผล: รอ ploy ยืนยัน template รายงาน (OQ-012) + สัปดาห์นี้ overcommit 6h
Capacity (จำลอง): committed 36h → 33.5h · conflicts 3 → 2
ทางเลือก
1 ⭐ เลื่อน TASK-018 → 11-13 · ploy ได้รายงานช้า 1 สัปดาห์ · ไม่กระทบโปรเจกต์อื่น · เสี่ยงต่ำ
2 คงวันเดิม ลด scope เหลือ 1 รายงาน · ploy อาจไม่พอใจ · เสี่ยงกลาง
3 คงวันเดิม ทำ OT · เสี่ยง food-delivery TASK-004 หลุด · เสี่ยงสูง
ไฟล์ที่สร้างแล้ว: Portfolio/plan-changes/20261101-113000_PCP-004_move-task-018.md (status: proposed)
อนุมัติ PCP-004 ทางเลือกที่ 1 ไหม?
```

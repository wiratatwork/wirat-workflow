---
name: delivery-report
description: Prepare the end-of-phase delivery report and next-meeting agenda for the User presentation — summarises completed work (estimate vs actual), Wirat's remaining work, stakeholder-owned work, open questions, UAT results, risks and blockers, cross-project capacity conflicts, and updates skill usage metrics. Use for "สรุปงานที่เสร็จแล้วเตรียมนำเสนอ User", "ทำ report ส่ง manager", "ปิดเฟส", "เตรียม agenda ประชุมครั้งหน้า".
---

# delivery-report

## Trigger conditions
- A phase, release, sprint, or major group of tasks is complete; before a User/manager progress meeting.
- Phrases: "สรุปงานที่เสร็จแล้ว", "เตรียมนำเสนอ User", "report ให้ manager", "ปิดเฟส", "agenda ประชุมครั้งหน้า".

## Inputs
- Project (or all), period (default: since the last delivery report in `00-Project/releases/`).
- backlog/progress/journey JSON, `Portfolio/delivery-metrics.json`, UAT `latest.json`, open questions, `wf.py capacity`, `skill-usage.json`.

## Steps
1. `ใช้ skill: delivery-report` — confirm project, phase name, period.
2. History since the last report only: `wf.py journey <slug> --since <last report date> --limit 40` (never the whole journey); decisions/meetings: `wf.py artifacts <slug> --kind decisions -n 10`.
   Refresh numbers read-only: `wf.py progress <slug>`, `wf.py capacity`, `wf.py metrics`.
3. Draft from `templates/artifacts/delivery-report.md`:
   1. Completed work — accepted/done tasks in period with estimate → actual and variance reasons.
   2. Wirat's remaining work — by health and due.
   3. Stakeholder-owned work — what each person owes, and what is waiting on them.
   4. Open Questions — owner + target meeting.
   5. UAT results — latest revision totals, failed/blocked items.
   6. Risks & blockers.
   7. Capacity conflicts across projects.
   8. **Next-meeting agenda** for the User presentation (demo items, decisions needed, OQs to close, UAT sign-off asks) —
      also saved as `meetings/<ts>_MTG-###_agenda.md` so meeting-intake can compare later.
   9. Skill usage this period (from `skill-usage.json`).
4. Show the draft and file plan; on ok write the files, then `wf.py log-skill delivery-report --project <slug> --note "<phase>"`
   (updates skill usage metrics) and hand to project-memory for a `release`/`milestone` journey event.
5. Optionally draft the message to User/manager (do not send).

## Output files
- `00-Project/releases/<YYYYMMDD-HHMMSS>_delivery-report_<phase>.md` (new)
- `00-Project/meetings/<YYYYMMDD-HHMMSS>_MTG-###_agenda.md` (new)
- `Portfolio/skill-usage.json`; journey event via project-memory

## Guardrails
- Numbers come from data files; anything without evidence → `Unknown / Needs confirmation`.
- Never overwrite an earlier report; a correction is a new revision (`wf.py revise`).
- Never send messages on Wirat's behalf.
- Confirm before writing.

## Example output
```
ใช้ skill: delivery-report — it-service-request เฟส 1 (2026-10-01..2026-11-01)

1. เสร็จแล้ว 5 งาน (estimate รวม 11d → actual 13.5d, +23%) — ส่วนใหญ่จาก requirement เพิ่มหลังประชุม
2. Wirat เหลือ 4 งาน: 🔴 TASK-015 · 🟠 TASK-018 · 🟢 TASK-019, TASK-020
3. รอ stakeholder: ploy — ยืนยัน SLA matrix (block TASK-016) · arthit — LDAP group
4. Open Questions 3 ข้อ (OQ-011..013) ทุกข้อมี owner + target MTG-004
5. UAT r01: Pass 4 · Fail 1 · Blocked 1
6–7. Risk: SLA matrix ยังไม่ final · Capacity: สัปดาห์หน้า overcommit 6h ร่วมกับ food-delivery
8. Agenda MTG-004: demo SLA dashboard · ขอ sign-off UAT-001..004 · ตัดสิน OQ-012 · ยืนยันวัน UAT รอบ 2
9. Skills ที่ใช้บ่อย: progress-view 9 · build-loop 7 · meeting-intake 4

ไฟล์ที่จะสร้าง (รอ ok): releases/20261101-160000_delivery-report_phase-1.md · meetings/20261101-160000_MTG-004_agenda.md
```

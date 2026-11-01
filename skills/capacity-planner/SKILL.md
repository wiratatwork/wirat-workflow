---
name: capacity-planner
description: Aggregate Wirat's workload across every project to find available hours, deadline conflicts, overcommitment and same-day commitments, show the impact of adding or moving work, and propose schedules ranked by recommendation (changes go to plan-change-control). Use for "สัปดาห์นี้ว่างแค่ไหน", "รับงานเพิ่มไหวไหม", "ถ้าเลื่อน X จะกระทบอะไร", "จัดตารางให้หน่อย", and whenever estimating or rescheduling.
---

# capacity-planner

## Trigger conditions
- Estimating (called by estimate-assistant), scheduling, rescheduling, or checking workload.
- Phrases: "ว่างแค่ไหน", "รับงานเพิ่มไหวไหม", "ตารางสัปดาห์นี้", "ถ้าเลื่อน…กระทบอะไร", "งานชนกันไหม".

## Inputs
- All backlogs (Wirat-owned open tasks), `Portfolio/capacity.json` settings:
  `working_hours_per_day`, `focus_factor` (meetings/admin), `working_weekdays`, `non_working_dates`, `leave_hours_this_week`.
- The work to add/move (if any).

## Steps
1. `ใช้ skill: capacity-planner`.
2. `wf.py capacity` (read-only): capacity hours this week, committed hours per project, available hours,
   conflicts — `overcommit`, `deadline` (earliest-deadline-first: queued work > capacity before due), `same-day-commitments`,
   and tasks with unknown estimate/due.
3. For "what if": adding work → the simulation in `wf.py estimate` (available hours before/after, new conflicts);
   moving work → draft the change and let plan-change-control's proposal show the simulated before/after capacity table.
4. Propose 2–3 schedules ranked ⭐ most → least recommended, each with: what moves, timeline impact, capacity after,
   stakeholders affected, other projects affected, risk.
5. If Wirat picks one that changes dates/priority/owner → hand to `plan-change-control`. Nothing is rescheduled here.
6. Optional (with ok): `wf.py capacity --write` to persist the snapshot in `Portfolio/capacity.json` and refresh views.

## Output files
- Read-only by default. With approval: `Portfolio/capacity.json` (archived first), `Portfolio/portfolio-data.js`.

## Guardrails
- Never move work yourself — proposals only.
- Tasks without estimate/due are listed as `Unknown / Needs confirmation`, not silently ignored.
- Capacity settings (leave, holidays) come from Wirat; ask when the week looks unusual.

## Example output
```
ใช้ skill: capacity-planner — สัปดาห์ 2–6 พ.ย. 2026

Capacity 30h (8h × 0.75 × 5 วัน) · Committed 36h · ว่าง -6h ⚠
| Project | Active (Wirat) | ชั่วโมงสัปดาห์นี้ |
| food-delivery | 4 | 14.5 |
| it-service-request | 4 | 15 |
| approval-system | 2 | 6.5 |
Conflicts: overcommit 6h · deadline TASK-004 (needs 34h by 11-04, มี 18h) · 11-06 มี 2 โปรเจกต์ส่งพร้อมกัน

ตัวเลือก
1 ⭐ เลื่อน TASK-018 (P3) ไป 11-13 → ว่าง +2h, conflict deadline หาย, กระทบ ploy เล็กน้อย
2 ขอ manager ย้าย TASK-025 ให้ dev อื่น → ว่าง +6h, ต้องรอ manager อนุมัติ
3 ทำ OT 6h → ไม่กระทบใคร, เสี่ยงคุณภาพ/เหนื่อย
เลือกข้อไหน จะส่งเข้า plan-change-control
```

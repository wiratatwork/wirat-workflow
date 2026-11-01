---
name: estimate-assistant
description: Estimate new work using task type and complexity, similar accepted tasks from delivery metrics, current workload in every project and calendar capacity — returns an estimate with range, confidence, assumptions and capacity impact, and routes any resulting schedule change to plan-change-control. Use for "ช่วย estimate งานเพิ่ม export PDF", "งานนี้ใช้กี่วัน", "ประเมินเวลาให้หน่อย", "ทันไหมถ้าส่งวันที่…".
---

# estimate-assistant

## Trigger conditions
- Phrases: "estimate", "ประเมิน", "ใช้กี่วัน", "ทันไหม", "รับงานนี้ได้เมื่อไหร่".
- Called by work-management / meeting-intake when a new task lacks an estimate.

## Inputs
- Work description (+ project, module, desired due date if any).
- `Portfolio/delivery-metrics.json` (accepted history), all backlogs, `Portfolio/capacity.json`.

## Steps
1. `ใช้ skill: estimate-assistant`. If scope is unclear → `clarify` first (ask ≤ 3 questions).
2. **Classify**: `task_type` (backend-feature | frontend-feature | fullstack-feature | report-export | integration | bugfix |
   data-migration | uat-prep | devops) and `complexity` (low | medium | high) with a one-line reason.
3. **Bottom-up base**: break into sub-steps (API, UI, tests, UAT prep) → base days.
4. Run `wf.py estimate --type <t> --complexity <c> --base-days <n> [--project <slug>] [--due YYYY-MM-DD] [--priority P2]`:
   - ≥ 3 exact accepted matches → history-adjusted estimate (median actual/estimate ratio) + range; confidence medium/high.
   - < 3 → history shown as **reference only**, base estimate kept, confidence low (never generalise from one task).
   - Capacity impact: queued hours, earliest finish if queued after current work, available hours before/after, new conflicts.
5. Present with `templates/artifacts/estimate.md`: estimate + range, confidence, similar tasks, assumptions, capacity impact,
   affected projects/tasks, and options ranked ⭐ (e.g. full scope now / reduced scope / after current UAT).
6. If accepting the estimate means adding the task or moving other work → hand to `plan-change-control` (`add_task` / `set due`).
   The estimate itself writes nothing.

## Output files
- None (read-only). Hand-off creates a Plan Change Proposal.

## Guardrails
- Always show n (number of similar accepted tasks) and whether history was applied.
- Always state assumptions; unknowns → `Unknown / Needs confirmation`.
- Never put the task in the plan or change dates — plan-change-control only.

## Example output
```
ใช้ skill: estimate-assistant — "เพิ่ม export PDF" (it-service-request / report)

Classify: report-export / medium (template PDF + query รายงาน + ทดสอบ format)
Base (bottom-up): query 0.5d + PDF template 1d + API/download 0.5d + tests 0.5d = 2.5d
History: report-export/medium มี 1 record (TASK-009: 2d → 3d) → n=1 < 3 ใช้อ้างอิงเท่านั้น ไม่ปรับตัวเลข
Estimate: 2.5d (ช่วง 2–3.5d) · Confidence: low
Capacity: คิวงาน Wirat 92h · ถ้าต่อท้ายคิวเสร็จได้เร็วสุด 2026-11-20 · สัปดาห์นี้ว่าง -6h → -6h (ไม่เริ่มสัปดาห์นี้)
Assumptions: ใช้ library PDF ฝั่ง server ที่มีอยู่, 1 template, ไม่ต้องลายเซ็นดิจิทัล
ตัวเลือก: 1 ⭐ ทำหลัง UAT รอบนี้ (due 11-20) · 2 ลด scope เป็น print CSS 0.5d · 3 ทำทันที → TASK-018 เลื่อน 3 วัน
ถ้าเลือก จะร่าง Plan Change Proposal ให้ตรวจก่อน
```

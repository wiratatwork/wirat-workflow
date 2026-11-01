---
name: delivery-metrics
description: Record Actual Delivery the moment a User confirms delivered work passes — writes an accepted record (task, project, module, task type, complexity, start, UAT submission, acceptance date, estimate, actual effort, variance reason) to user-level Portfolio/delivery-metrics.json, marks the task accepted, and compares estimate vs actual without generalising from one task. Use for "User บอกว่า TASK-016 ผ่านแล้ว", "User sign off แล้ว", "UAT ผ่าน", "ลูกค้ารับงานแล้ว".
---

# delivery-metrics

## Trigger conditions
- A User / key user confirms a task passes (UAT pass, sign-off, "ผ่านแล้ว", "รับงานแล้ว").
- Also when Wirat asks "estimate เราแม่นแค่ไหน", "ส่วนต่าง estimate กับจริง".

## Inputs
- Task ID (find project with `wf.py` — IDs are portfolio-unique), acceptance date, who accepted.
- **Actual effort in days** and **variance reason** if actual ≠ estimate — ask Wirat; never invent.
- Start and UAT-sent dates come from the task (`start`, `uat_sent`/`uat_date`); ask if missing.

## Steps
1. `ใช้ skill: delivery-metrics` — confirm task, project, title, estimate.
2. Ask only for what is missing: actual days, variance reason, acceptance date (default today), accepted by.
3. Show the record + `wf.py --dry-run accept TASK-016 --actual-days 4 --accepted 2026-11-01 --accepted-by ploy --variance "…"`; wait for ok.
4. Run it. wf.py appends to `Portfolio/delivery-metrics.json`, sets the task `accepted`, adds journey events
   (timeline + module evolution), refreshes progress/data.js and logs skill usage. It refuses duplicates and missing data.
5. Show estimate vs actual and `wf.py metrics` for that task type/complexity:
   - n < 3 → "ยังสรุปแนวโน้มไม่ได้ (ข้อมูลน้อย)" — reference only.
   - n ≥ 3 → median actual/estimate ratio; mention it will inform future estimates (estimate-assistant).
6. If the task's DoD was `release`/phase end → suggest delivery-report.

## Output files
- `Portfolio/revisions/<ts>_delivery-metrics.json` (new revision; `Portfolio/latest.json` points to it; `delivery-metrics.json` is the mirror)
- `10-Data/backlog.json`, `10-Data/journey.json`, `10-Data/progress.json`, `data.js`, `Portfolio/portfolio-data.js`, `Portfolio/skill-usage.json`

## Guardrails
- Record immediately after acceptance — don't batch for later.
- Never fabricate actual effort; if unknown, ask (status stays `Unknown / Needs confirmation`, nothing recorded).
- Never conclude a trend from a single task (`min_history_for_estimate` = 3 in config).
- Confirm before writing.

## Example output
```
ใช้ skill: delivery-metrics — บันทึกการส่งมอบ TASK-016 (it-service-request / sla)

| Field | Value |
| Task type / complexity | backend-feature / medium |
| Start → UAT sent → Accepted | 2026-10-26 → 2026-10-30 → 2026-11-01 (ploy) |
| Estimate → Actual | 3d → 4d (+1d) |
| Variance reason | User ขอ validation เพิ่มหลังประชุม |

ไฟล์ที่จะเขียน (รอ ok): update Portfolio/delivery-metrics.json · 10-Data/backlog.json (TASK-016 → accepted) · journey.json

หลังบันทึก: backend-feature/medium มี 4 records → median ratio 1.25 (ใช้ประกอบ estimate ครั้งถัดไป)
```

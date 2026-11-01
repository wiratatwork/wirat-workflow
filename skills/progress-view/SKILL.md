---
name: progress-view
description: Answer progress questions across all projects and refresh the existing progress.html through data files — reads tasks, stakeholders, capacity and journey, writes progress.json, and reports Wirat's tasks, each stakeholder's tasks, on-track / at-risk / delayed / blocked / waiting-on-user / waiting-on-manager work, capacity conflicts, dependency risks and frequently used skills. Use for "ดู progress หน่อย", "ตอนนี้ใครค้างอะไรบ้าง", "งานไหนจะ delay", "อะไร block อยู่", "workload เป็นยังไง".
---

# progress-view

## Trigger conditions
- Phrases: "ดู progress", "ตอนนี้ใครค้างอะไรบ้าง", "อะไรเลยกำหนด", "งานไหนเสี่ยง", "รออะไรจาก User", "สถานะ stakeholder", "workload", "สถานะงาน", "สถานะ … เป็นยังไง".
- Any status question about a project or task also opens its `progress.html` (step 5). Never answer a status question in chat alone.
- Before progress meetings, and after other skills change data (they call `wf.py progress --write`).

## Inputs
- All `10-Data/backlog.json`, `journey.json`, stakeholders, `Portfolio/capacity.json`, `skill-usage.json`, UAT `latest.json`.

## Steps
0. Context budget: never open `progress.json` / `journey*.json` / `portfolio-data.js`; use `wf.py tasks`, `wf.py stakeholder`, `wf.py journey <slug> --digest`, `wf.py progress`.
1. `ใช้ skill: progress-view` — scope: all projects (default when the question is about Wirat / "ใคร") or one project.
2. Read-only first: `wf.py progress --all` and `wf.py capacity` (prints, writes nothing). Health is computed by wf.py:
   delayed (due passed) · blocked · waiting-user · waiting-manager · at-risk (risk high or remaining work > capacity before due) · on-track · unknown (no due/estimate).
3. Answer in chat (Thai):
   - Wirat's tasks across projects, sorted by health then due.
   - Each stakeholder: `wf.py stakeholder <id>` — tasks they own, tasks waiting on them (`blocked_by`), their Open Questions
     across projects, and **impact on Wirat** (blocked hours, downstream tasks, hours at risk, earliest affected due, projects).
   - Counts: on-track / at-risk / delayed / blocked / waiting-on-user / waiting-on-manager / unknown.
   - Capacity conflicts (overcommit, deadline, same-day commitments) and dependency risks (incl. cross-project).
   - Frequently used skills.
   - Recommended next actions ranked; any date/priority change → offer plan-change-control (don't apply).
4. Offer to refresh the views. On "ok": `wf.py progress --all --write --skill progress-view` then `wf.py capacity --write`
   (new revisions under `revisions/` + `latest.json`, regenerates `data.js` + `Portfolio/portfolio-data.js`).
5. **Open the HTML alongside every status answer.** Whenever the answer is about a project's status, tasks, progress or who is stuck, also open `Projects/<slug>/ProjectWorkspace/20-Views/progress.html` in the machine's **default browser** (Windows: `start "" "<full path>"`; macOS: `open "<full path>"`; Linux: `xdg-open "<full path>"`). Always open it this way, every time — never in the built-in Browser pane (`preview_start`, `navigate`), never via `show_pane`, and never only as a path in chat. Use the project's slug from `wf.py projects list`; for all projects or Wirat's view, open the project's `progress.html` and say which mode to select (All projects · Single project · Wirat · Stakeholder; filters: project, module, owner, stakeholder, status, risk, due date).
   - The view only reads `10-Data/data.js`, so if the chat answer differs from what the view shows (data not refreshed), say so and offer step 4 (refresh needs one "ok").

## Output files
- `10-Data/progress.json` per project, `10-Data/data.js`, `Portfolio/capacity.json`, `Portfolio/portfolio-data.js`
- **Never** a new HTML file — `20-Views/progress.html` was created once at onboarding and only reads the data files.

## Guardrails
- Status only from evidence in data; missing due/estimate → `Unknown / Needs confirmation`, never guessed.
- Read-only answers need no confirmation; refreshing JSON needs one "ok".
- Do not change any plan field; suggest plan-change-control instead.

## Example output
```
ใช้ skill: progress-view — สรุปทุกโปรเจกต์ ณ 2026-11-01

ภาพรวม: 🟢 9 · 🟠 3 · 🔴 2 · ⛔ 2 · 👤 รอ User 2 · 🧑‍💼 รอ Manager 1 · ❔ 1
งานของ Wirat ที่ต้องดูก่อน
| Task | Project | Health | Due | หมายเหตุ |
| TASK-015 | it-service-request | 🔴 Delayed 2 วัน | 2026-10-30 | SLA calc |
| TASK-004 | food-delivery | 🟠 At risk | 2026-11-04 | เหลือ 2.5d แต่มีเวลา 2 วัน |
ใครค้างอะไร
- ploy (User): รอ confirm SLA matrix → block TASK-016
- manager-kittipong: รออนุมัติ server UAT → TASK-026
Capacity สัปดาห์ 2–6 พ.ย.: ว่าง -6h (overcommit) · deadline conflict: TASK-004, TASK-024
แนะนำ: ⭐ เสนอเลื่อน TASK-018 (plan-change-control) · ตาม ploy เรื่อง SLA วันนี้
รีเฟรช progress.json + HTML views ไหม? (เขียน 3 progress.json + capacity.json)
```

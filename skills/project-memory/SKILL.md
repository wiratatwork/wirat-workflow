---
name: project-memory
description: Record decisions and project history — creates Decision Records and updates the Project Journey by Timeline and by Module Evolution as new revisions (never overwriting), linked to meetings, modules, tasks, stakeholders and UAT records. Use after a decision, milestone, release, major code change or important meeting, or when Wirat says "บันทึกการตัดสินใจ", "จดไว้ว่าตกลงแบบนี้", "อัปเดต journey".
---

# project-memory

## Trigger conditions
- A decision was made (by Wirat in chat, in a meeting, or an approved plan change).
- A milestone, release, UAT sign-off, or major code change happened.
- Phrases: "บันทึกการตัดสินใจ", "ตกลงตามนี้", "จดไว้", "อัปเดต journey".

## Inputs
- Decision / event text, date, who decided, evidence (meeting id, chat, PR, commit).
- Links: meeting IDs, modules, task IDs, stakeholder ids, UAT IDs, plan change ID.

## Steps
1. `ใช้ skill: project-memory` — summarise what will be recorded.
2. **Decision Record + journey in one command** (never hand-edit the files):
   `wf.py --dry-run decision-new <slug> --title "…" --context "…" --decision "…" --alternatives "most|…|least"
   --meetings MTG-x --modules m1,m2 --tasks TASK-x --stakeholders a,b [--decided-by somchai] [--supersedes DEC-x] [--consequences "…"]`
   → creates `00-Project/decisions/<ts>_DEC-###_<slug>.md` (structure as `templates/artifacts/decision-record.md`) and appends the
   decision to the Journey **Timeline** and to **Module Evolution** of each module. A replaced decision gets a new record with
   `--supersedes` (the old file stays untouched).
3. **Other events** (milestone, release, meeting, major change):
   `wf.py journey-add <slug> --type milestone|release|meeting|change --title "…" [--summary] [--modules] [--tasks]
   [--stakeholders] [--meeting MTG-x] [--decision DEC-x] --module-event "module|stage|change"` (repeatable).
4. An Open Question the decision closes → `wf.py update-question OQ-x --answer "…" --decision DEC-x`.
5. If the narrative journey markdown exists, create a new revision with `wf.py revise 00-Project/journey/<file>` and add the entry there.
6. Feature changed status? → `wf.py revise 00-Project/feature-inventory.md` and update the row with evidence.
7. Show the file plan, confirm, write, then `wf.py progress <slug> --write --skill project-memory` (refreshes `data.js`).

Journey limits: title ≤160 chars, summary ≤600 chars (the command refuses longer). Put the long text in the Decision Record or meeting note and pass `--ref <path>`. To look back, use `wf.py journey <slug> --search/--module/--since …` (capped), never read `journey-events/`.

## Output files
- `00-Project/decisions/<ts>_DEC-###_<slug>.md` (new)
- `10-Data/revisions/<ts>_journey.json` (new revision; `10-Data/latest.json` points to it; `journey.json` is the mirror)
- optional `00-Project/journey/<ts>_journey.md`, `00-Project/<ts>_feature-inventory.md` (new revisions)

## Guardrails
- Never edit an existing decision record, meeting note or inventory revision; always a new file.
- Record only decisions with evidence of agreement; otherwise route to clarify / Open Question.
- Plan changes are recorded here only **after** approval (plan-change-control calls this).
- Confirm before writing.

## Example output
```
ใช้ skill: project-memory — บันทึกการตัดสินใจเรื่องช่องทางแจ้งเตือน

DEC-009: แจ้งเตือนผ่าน email ก่อน, LINE เลื่อนไปเฟส 2
- Context: MTG-003 (2026-10-31) ploy ต้องการเร็ว, LINE OA ยังไม่ได้อนุมัติ
- Links: meeting MTG-003 · module notification · tasks TASK-017 · stakeholders ploy, arthit

ไฟล์ที่จะเขียน (รอ ok):
- create: 00-Project/decisions/20261101-101500_DEC-009_notify-email-first.md
- update: 10-Data/journey.json (+1 timeline, +1 module evolution "notification")
```

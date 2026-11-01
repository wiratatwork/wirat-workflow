---
name: clarify
description: Resolve unclear requirements, priorities, dependencies or implementation approaches by asking focused questions and presenting options ranked most → least recommended, each with description, benefits, drawbacks, timeline, capacity, stakeholder impact and risk; answered → project-memory decision, unanswered → Open Question with owner and target meeting. Use when Wirat says "ยังไม่ชัด", "จะเลือกแบบไหนดี", "ควรทำแบบไหน", or another skill finds ambiguity.
---

# clarify

## Trigger conditions
- A requirement, priority, dependency, owner, or technical approach is ambiguous or contradictory.
- Phrases: "ยังไม่ชัด", "จะเลือกแบบไหนดี", "A กับ B อันไหนดีกว่า", "User พูดไม่ชัด".
- Hand-offs from meeting-intake, build-loop, estimate-assistant, work-management.

## Inputs
- The unclear item + its context (task, meeting note, code area).
- Current workload/capacity (`wf.py capacity`) and affected tasks/stakeholders, so impacts are real numbers.

## Steps
1. `ใช้ skill: clarify` — restate the ambiguity in one sentence.
2. Ask **at most 3 focused questions**, the most decision-relevant first. Prefer questions Wirat can answer yes/no or by picking.
3. Build 2–4 options using `templates/artifacts/clarify-options.md`, ranked ⭐ most → least recommended. For every option give:
   Description · Benefits · Drawbacks · Timeline impact · Capacity impact (hours, from `wf.py capacity`) · Stakeholder impact · Risk.
4. Give a recommendation with the reason.
5. Outcome:
   - **Wirat answers** → hand to `project-memory` (Decision Record, links). If it changes a plan field → `plan-change-control`.
   - **Wirat cannot answer** → confirm, then `wf.py add-question <slug> --question "…" --owner <stakeholder> --target-meeting <MTG/date>
     --tasks TASK-x --options "opt1|opt2|opt3"` and add it to the next agenda (new revision of the agenda via `wf.py revise`,
     or a new agenda file if none exists). Do not create implementation tasks that depend on the unanswered question.
   - Answer refines the question but does not close it (e.g. approach chosen, name still missing) →
     `wf.py update-question OQ-x --question "…"` and keep it open.
6. **Big work (more than one session):** split the unclear parts into OQs, one per decision, each with an owner and a target
   meeting. Close them one at a time: run `/grill-me` until the answer is settled, write the DEC with `wf.py decision-new`, then
   `wf.py update-question OQ-x --answer "…" --decision DEC-xxx` (status becomes `answered`; use `--status dropped` if the
   question is no longer needed). Track what is left with `wf.py questions --project <slug> --open` and `wf.py tasks --project <slug>`.
   Do not build a separate map of tickets.

## Output files
- None by itself. Via hand-off: Decision Record (project-memory) or `10-Data/backlog.json` open_questions entry.

## Guardrails
- Never pick for Wirat silently; never implement an unconfirmed interpretation.
- Impacts must be evidence-based; unknown → `Unknown / Needs confirmation`.
- An Open Question without owner + target meeting is not allowed.
- Confirm before writing the Open Question.

## Example output
```
ใช้ skill: clarify — "export PDF" ยังไม่ชัดว่าต้อง export อะไร

คำถาม: 1) ต้องการ PDF ของรายงาน SLA รายเดือน หรือของใบคำขอแต่ละใบ?  2) ต้องมีโลโก้/ลายเซ็นไหม?

| Rank | Option | Benefits | Drawbacks | Timeline | Capacity | Stakeholders | Risk |
| 1 ⭐ | PDF รายงาน SLA รายเดือน (server-side, template เดียว) | ตรงกับที่ ploy ใช้ประชุมผู้บริหาร | ไม่ครอบคลุมใบคำขอ | +2d | ใช้ 12h จากที่ว่าง 10h → เกิน 2h | ploy พอใจ, arthit ไม่กระทบ | ต่ำ |
| 2 | PDF ทุกหน้าแบบ print CSS | เร็ว | หน้าตาไม่คุม | +0.5d | 3h | ploy อาจไม่พอใจ | กลาง |
| 3 | ทั้งสองแบบ | ครบ | ใหญ่ | +4d | เกิน capacity 14h, กระทบ food-delivery | — | สูง |

แนะนำ Option 1 — ถ้าตอบไม่ได้ตอนนี้ จะสร้าง OQ-013 (owner: ploy, target: MTG-004)
```

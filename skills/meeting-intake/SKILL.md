---
name: meeting-intake
description: Turn a meeting transcript, voice-to-text output or meeting notes into a new timestamped meeting note that compares outcomes with the prepared agenda and classifies every item as Fact, Decision, New topic outside agenda, Follow-up task or Open question, linked to stakeholders, modules, tasks and decisions. Use when Wirat pastes or attaches a transcript/notes, e.g. "นี่ transcript ประชุมเมื่อวาน", "สรุปประชุมให้หน่อย", "นี่โน้ตจากการคุยกับ User".
---

# meeting-intake

## Trigger conditions
- Wirat provides a transcript, voice-to-text dump, chat export, or rough notes from a meeting.
- Phrases: "นี่ transcript ประชุม…", "สรุปประชุม", "บันทึกการประชุม", "คุยกับ User มาแล้ว".

## Inputs
- The transcript / notes (pasted or file path).
- Project (infer from names/modules/task IDs; ask if ambiguous) and meeting date.
- The prepared agenda: latest `00-Project/meetings/*_agenda.md` for that date (if none, say so — compare against "no agenda").
- Existing stakeholders, tasks, open questions from `10-Data/backlog.json` and `00-Project/stakeholders/`.

## Steps
1. `ใช้ skill: meeting-intake` — name the project, date, agenda file found.
2. Read the transcript fully. Map speakers to stakeholder ids (unknown speaker → `Unknown / Needs confirmation`).
3. **Agenda vs outcome**: for each agenda item → outcome + coverage (covered / partial / not covered).
4. **Classify** every substantive item into exactly one bucket, quoting evidence (short quote or timestamp):
   - **Fact** — stated information.
   - **Decision** — explicitly agreed; who decided.
   - **New topic outside agenda**.
   - **Follow-up task** — owner, due (if said), module, stakeholders. These are *proposed*: they enter the plan only via plan-change-control (`add_task`).
   - **Open question** — needs `owner` + `target_meeting`.
5. Anything ambiguous (who owns it, what exactly was agreed, conflicting statements) → list under "ต้อง clarify" and hand to the `clarify` skill.
6. Link: stakeholders, modules, existing task IDs, existing OQ IDs (mark answered OQs).
7. Show the draft note + file plan; on approval:
   - create `00-Project/meetings/<YYYYMMDD-HHMMSS>_MTG-###_notes.md` from `templates/artifacts/meeting-note.md` (`wf.py next-id MTG` if the agenda had no id);
   - for each Decision → hand to `project-memory` (Decision Record + journey);
   - new Open Questions → `wf.py add-question <slug> --question "…" --owner <id> --target-meeting <MTG/date> --tasks TASK-x --raised-in MTG-x`;
     answered ones → `wf.py update-question OQ-x --answer "…" [--decision DEC-x]`;
   - meeting itself on the journey → `wf.py journey-add <slug> --type meeting --title "MTG-x …" --meeting MTG-x --stakeholders …`;
   - follow-up tasks + any date/scope change mentioned → one Plan Change Proposal via `plan-change-control`;
   - `wf.py progress <slug> --write --skill meeting-intake`.

Context budget: read the agenda and the transcript only; for existing context use `wf.py tasks --project <slug>`, `wf.py artifacts <slug> --kind meetings -n 3`, `wf.py journey <slug> --since <date>` — not the JSON feeds. The meeting note carries the detail; the journey event gets a short title/summary + `--ref`.

## Output files
- `Projects/<slug>/ProjectWorkspace/00-Project/meetings/<ts>_MTG-###_notes.md` (new, never edited later)
- `10-Data/backlog.json` (open questions only), `10-Data/progress.json`, `data.js`
- Hand-offs: Decision Records (project-memory), Plan Change Proposal (plan-change-control)

## Guardrails
- Never invent decisions; if consensus is unclear it is an Open question, not a Decision.
- Never modify an earlier meeting note — corrections create a new revision with `wf.py revise`.
- Never add tasks or change dates directly — always via plan-change-control.
- Every Open Question has owner + target meeting.
- Confirm the file list before writing.

## Example output
```
ใช้ skill: meeting-intake — ประชุม it-service-request 2026-10-31 เทียบกับ agenda MTG-003

Agenda vs outcome
| # | Agenda | ผล | Coverage |
| 1 | Demo SLA dashboard | User โอเค ขอเพิ่ม filter ตามแผนก | covered |
| 2 | ยืนยัน LDAP group | ยังไม่ได้ข้อสรุป | not covered |

Facts: (1) ทีม IT มี 3 ระดับ L1–L3 — "เรามีสามระดับ" (00:12:40, ploy)
Decisions: (1) แจ้งเตือนผ่าน email ก่อน, LINE ไว้เฟส 2 — ploy → DEC (project-memory)
นอก agenda: (1) ขอ export รายงาน PDF — ploy
Follow-up tasks (เสนอ, ยังไม่เข้าแผน): TASK-? เพิ่ม filter แผนก — wirat — due ? → Plan Change Proposal
Open questions: OQ-012 ใช้ LDAP group ไหนเป็น approver? — owner: arthit — target: MTG-004
ต้อง clarify: "ขอ export PDF" หมายถึงรายงานไหน? → clarify

ไฟล์ที่จะเขียน (รอ ok): create meetings/20261101-093000_MTG-003_notes.md · update 10-Data/backlog.json (OQ-012)
```

# Wirat — Multi-Project Development Workflow (user level)

> Applies to every project. Project data lives in the Obsidian workspace, never here.
> Helper CLI: `python -I ~/.claude/wirat-workflow/scripts/wf.py <command>` (called `wf.py` below).
> Templates: `~/.claude/wirat-workflow/templates/`. Overview: `~/.claude/wirat-workflow/README.md`.

## 1. Who I work with
- **Wirat**, Full Stack Developer: gathers requirements with Users, builds full-stack features, tests and prepares UAT,
  reports progress to Users and managers, schedules progress meetings.
- Reply in **Thai**; English technical terms are fine (API, schema, UAT, PR, …).
- Wirat does **not** memorise slash commands. Pick the skill yourself from the conversation (table below), say in one
  line which skill you are using and what it will do, then do it.
- Before any decision: give a summary, options ranked most → least recommended, impacts, and a recommendation.
- Record every decision (project-memory).

## 2. Where things live
| What | Path |
|---|---|
| Portfolio (cross-project) | `~/Obsidian/Wirat-Workspace/Portfolio/` — `portfolio-overview.md`, `capacity.json`, `delivery-metrics.json`, `skill-usage.json`, `id-registry.json`, `projects.json`, `plan-changes/` |
| One project | `~/Obsidian/Wirat-Workspace/Projects/<slug>/ProjectWorkspace/` — `00-Project/` (markdown artifacts), `10-Data/` (JSON feeds), `20-Views/` (HTML, created once) |
| Source code | The project's own repo, **wherever it is on this computer** (`wf.py projects list`). Only build-loop may edit it. |
| This computer only | `~/.claude/wirat-workflow/local.json` — workspace root + each project's repo folder (+ optional custom ProjectWorkspace folder). Never synced, never in shared data. Manage with `wf.py projects …`; shared data holds no absolute paths. |

Detect the current project with `wf.py projects which` (current folder) or from the task ID / project name Wirat
mentions. If several fit, ask once. Repo not mapped yet → `wf.py projects map <slug> --repo <folder>` (confirm first).

## 3. Skill routing (choose automatically)
| Wirat says something like… | Skill |
|---|---|
| "เริ่มโปรเจกต์ใหม่", "ยังไม่มี workspace", opening a repo with no ProjectWorkspace | `project-onboarding` |
| "นี่ transcript ประชุมเมื่อวาน", meeting notes, voice-to-text | `meeting-intake` |
| "ยังไม่ชัด", "จะเลือกแบบไหนดี", unclear requirement / priority / approach | `clarify` |
| "บันทึกการตัดสินใจ", after a decision / milestone / release / major change | `project-memory` |
| "สร้าง task", "จัด priority", "assign", "งานไหนทำขนานได้" | `work-management` |
| "ดู progress หน่อย ตอนนี้ใครค้างอะไรบ้าง", delays, blockers, workload, stakeholder status | `progress-view` |
| "User บอกว่า TASK-016 ผ่านแล้ว", User accepted / signed off | `delivery-metrics` |
| "สัปดาห์นี้ว่างแค่ไหน", "รับงานเพิ่มไหวไหม", workload / scheduling | `capacity-planner` |
| "ช่วย estimate งานเพิ่ม export PDF", "ใช้เวลากี่วัน" | `estimate-assistant` |
| "ต้องเลื่อน TASK-018 เป็นสัปดาห์หน้า", any change of due / priority / scope / owner / resources | `plan-change-control` |
| "ทำ task ถัดไป", "ทำต่อจนครบ", "แก้ bug", coding, debugging | `build-loop` |
| "เสร็จหรือยัง", before calling a task done | `quality-gate` |
| "เตรียม UAT ให้หน่อย", UAT results | `uat-manager` |
| "สรุปงานที่เสร็จแล้วเตรียมนำเสนอ User", end of phase / release | `delivery-report` |
| "ย้าย/map/เพิ่ม/ลบ project path", "เครื่องใหม่", "ย้ายเครื่อง", "repo อยู่คนละที่", "เครื่องนี้หา project ไม่เจอ", "upgrade view" | `project-onboarding` (§ Locations) |

Skills hand off to each other: unclear → `clarify`; decision → `project-memory`; any plan change → `plan-change-control`;
acceptance → `delivery-metrics`; estimate → `capacity-planner`.

**Ambiguous request (two or more skills fit):** run `wf.py skill-rank --candidates <a>,<b>` and pick the most used
(then most recent) relevant skill; say in one line which one and why. If the choice would change what gets written or
decided, ask instead of picking.

**Usage tracking:** every skill use is counted once. Commands that already log it: anything run with `--skill <name>`,
`accept`, `uat-revise`, `apply-change`. Otherwise finish with `wf.py log-skill <skill> --project <slug>`.
`Portfolio/skill-usage.json` holds usage metrics only (no project data), so this one write does not need a separate
confirmation (`config.json` → `"skill_usage_logging": "auto"`; set it to `"confirm"` to list it with the other writes).

## 3b. Context budget (long projects must not get expensive)
Never `Read` these into the conversation: `10-Data/*.json` (backlog, progress, journey, data.js), `journey-events/**`,
`revisions/**`, `Portfolio/*.json`, `portfolio-data.js`. They grow without limit. Use the compact commands instead:
- `wf.py tasks [--project --status --health --owner --stakeholder --due-before --limit]` — one line per task, riskiest first
- `wf.py journey <slug> [--since --until --type --module --task --decision --search --limit --full | --digest]` — windowed,
  output capped at ~6000 chars; start with `--digest` or the last 15, then narrow. Never ask for "the whole journey".
- `wf.py artifacts <slug> --kind decisions|meetings|releases|stakeholders -n 5` — current revisions only, one line each
- `wf.py stakeholder <id>`, `wf.py progress [slug]`, `wf.py capacity`, `wf.py metrics`, `wf.py projects list` — summaries
Markdown artifacts: read only the current revision and only the sections needed (older revisions never). Long text
(meeting detail, reasoning) belongs in a meeting note / decision record; the journey gets a ≤160-char title, ≤600-char
summary and `--ref <path>` to that file (`wf.py` refuses longer text). When a result says "N more … not shown", narrow the
filter instead of raising the cap.

## 4. Non-negotiable rules
0. **Grill at three points, and record every decision.** Run `/grill-me` (skill `grill-me`: one round of questions at a
   time, a recommended answer for each) when:
   - **Closing an Open Question (OQ):** grill until the answer is settled, then record it as a DEC and close the OQ
     (`wf.py update-question`), with the OQ's owner and target meeting kept on the record.
   - **Creating a DEC from a Task (T):** grill the task's scope and the choice behind it, then write the DEC (`wf.py decision-new`)
     and link it to the task.
   - **Before writing code, when the requirement is still unclear:** ask only the questions needed to build it; if the grilling
     settles a choice, write it as a DEC before coding.
   Every decision reached this way is written as a DEC (project-memory), not left in chat. Grilling is not needed for other writes
   or for reading. After grilling, do rule 1 (list the files, wait for "ok").
1. **Confirm every write.** Before writing, list each target file (create / new revision / update) — run the
   `wf.py` command with `--dry-run` when there is one — and wait for Wirat's "ok". Reading never needs confirmation.
2. **Never modify an original artifact.** Markdown and Excel artifacts get a new timestamped revision
   (`wf.py revise <file>`, `wf.py uat-revise …`); names start with `YYYYMMDD-HHMMSS_`. JSON feeds in `10-Data/` and
   `Portfolio/` get a new immutable file `revisions/<ts>_<name>` on every write and `latest.json` points to it (journey events
   are one immutable file each under `journey-events/<YYYY-MM>/`; `journey.json` is only a small digest); the plain
   `backlog.json` / `journey.json` / … files are generated mirrors (like `data.js`) — never edit them by hand
   (`wf.py validate` flags it). Change data only through `wf.py` commands: `update-task`, `accept`, `add-question`,
   `update-question`, `journey-add`, `decision-new`, `propose-change`/`apply-change`, `uat-revise`, `progress --write`,
   `projects …`, `views`.
   HTML views are created once at onboarding and never regenerated — refresh their data with `wf.py bundle`; their
   code is upgraded only by `wf.py views` (old copy kept as `20-Views/_prev/*.bak`).
3. **Every artifact has `revision` and a timestamp** (`created_at` / `updated_at`).
4. **Evidence-based status only.** No evidence → `Unknown / Needs confirmation`. Cite the file, test, commit, or meeting.
5. **Every Open Question has an `owner` and a `target_meeting`.**
6. **Every task has** owner, priority, due date, estimate, dependencies, Definition of Done (`wf.py validate`).
7. **User acceptance → record Actual Delivery immediately** (`wf.py accept`, delivery-metrics skill).
8. **Estimates use delivery history + cross-project workload + capacity** (`wf.py estimate`). Never generalise from
   fewer than 3 similar accepted tasks; show them as reference only.
9. **No automatic plan changes.** Due date, priority, scope, owner, estimate, dependencies, resources change only via a
   Plan Change Proposal → Wirat approves in chat → `wf.py approve-change` → `wf.py apply-change`.
   `wf.py update-task` refuses plan fields on purpose, and refuses moving a `proposed` task into the plan — that is a
   scope change: use op `activate` in a proposal. Never pass `--by wirat` unless Wirat approved in this chat.
10. **Multi-agent work** needs an Execution Plan with file ownership, contracts, test responsibility and merge order,
    and `wf.py check-exec-plan` must PASS before any agent starts. One file → one agent. Separate git worktrees for
    agents that edit code. The coordinator never edits source code.
11. **pstack skills only for coding/debugging** (inside build-loop / quality-gate): `implement`, `tdd`,
    `diagnosing-bugs`, `code-review`, `prototype`, `to-spec`, `to-tickets`, `triage`, `pr`, `handoff`.
12. **Lightweight tests while coding** (needed unit + integration). Comprehensive E2E / Excel / regression → later phase.
13. **Phase complete → delivery report + next-meeting agenda** (delivery-report).
15. **Big work (more than one session):** split it into Open Questions, each with an `owner` and a `target_meeting` (rule 5).
    Close them one at a time: `/grill-me` until settled → DEC (`wf.py decision-new`) → `wf.py update-question <id> --answer … --decision DEC-xxx`
    (status `answered`; `--status dropped` if no longer needed). Track what is left with `wf.py questions --project <slug> --open`
    and `wf.py tasks --project <slug>`. Do not build a separate ticket map.
14. Onboarding reads everything but never modifies source code.

## 5. Status vocabulary
- Task `status`: proposed · todo · in-progress · in-review · uat · accepted · done · blocked · cancelled
- Computed `health` (by `wf.py`): on-track · at-risk · delayed · blocked · waiting-user · waiting-manager · unknown · done
- Feature status: Implemented · Partially Implemented · Planned · Unknown / Needs confirmation
- UAT status: Pass · Fail · Blocked · Not Run

## 6. Response shape
1. `ใช้ skill: <name>` + one line on what will happen.
2. Findings / summary (with evidence).
3. Options ranked ⭐ most → least recommended, with impacts — when a choice exists.
4. Files that will be written (wait for approval) — when writing.
5. Next step.

---
name: project-onboarding
description: "Create a Project Workspace for a new project or an existing repo that has none (read-only scan of README, docs, dependencies, config, routes, models, services, tests, git history; drafts Feature Inventory, Module Map, Stakeholder Registry, Initial Backlog, Journey, progress.json, Open Questions) AND manage where projects live on this computer: map / unmap / add / remove / restore project folders, set up a new PC, carry the workflow to another computer, upgrade HTML views. Use for เริ่มโปรเจกต์ใหม่, onboard โปรเจกต์นี้, ยังไม่มี workspace, ย้าย/map/เพิ่ม/ลบ path โปรเจกต์, repo อยู่คนละที่, เครื่องใหม่, ย้ายเครื่อง, เครื่องนี้หา project ไม่เจอ, upgrade view. Never edits source code."
---

# project-onboarding

## Trigger conditions
- A new project starts, or Wirat opens a repo whose path is not in `~/Obsidian/Wirat-Workspace/Portfolio/projects.json`.
- Phrases: "เริ่มโปรเจกต์ใหม่", "onboard", "สร้าง workspace ให้โปรเจกต์นี้", "วิเคราะห์สถานะโปรเจกต์นี้หน่อย".
- Do **not** use when `Projects/<slug>/ProjectWorkspace/` already exists → use progress-view / work-management.

## Inputs
- Repo path (default: current working directory) and a project slug + display name (propose; Wirat confirms).
- Optional: kickoff notes, known stakeholders, deadlines.

## Steps
1. Say `ใช้ skill: project-onboarding` and propose `slug`, `name`, `repo_path`.
2. **Read-only scan** (allowed to read all project files): README/docs, package manifests & lockfiles
   (dependencies), config/env samples, routes/controllers, models/schema/migrations, services, UI pages, tests,
   CI files, `git log --oneline -50`, `git shortlog -sn`, open branches. Never run installs, migrations, or builds.
3. Build the drafts in memory:
   - **Feature Inventory** — one row per feature: module, status (`Implemented` / `Partially Implemented` /
     `Planned` / `Unknown / Needs confirmation`), evidence (file path, route, test, commit). No evidence → Unknown.
   - **Module Map** — module, responsibility, main paths, depends-on, mermaid graph.
   - **Stakeholder Registry draft** — people from commits, docs, Wirat's notes; mark unconfirmed roles `Unknown / Needs confirmation`.
   - **Initial Backlog** — tasks for Partially Implemented / Planned features with all required fields
     (owner, priority, due, estimate, dependencies, DoD). All onboarding tasks start as `status: proposed`; they enter the plan only through a Plan Change Proposal with op `activate`
     (`update-task` refuses it). Unknown due/estimate → raise an Open Question (`wf.py add-question`).
   - **Project Journey** — timeline from git history milestones/tags + module evolution.
   - **Open Questions** for the next meeting, each with `owner` and `target_meeting`.
4. Show the summary + the list of files to create, run `wf.py --dry-run new-workspace <slug> --name "<name>" --repo "<path>"`, and wait for approval.
5. On approval: `wf.py new-workspace …` (copies the template incl. the three HTML views — the only time they are created),
   then write the drafts: revise `feature-inventory.md`, `project-overview.md`, `modules/module-map.md` with
   `wf.py revise` (the template copy stays as revision 1), create `stakeholders/<id>.md`, fill `10-Data/backlog.json`
   (task IDs from `wf.py next-id TASK`) — the only direct feed write, done once on the fresh template copy before
   any revision exists — then journey events via `wf.py journey-add`, Open Questions via `wf.py add-question`, then `wf.py validate <slug>` and
   `wf.py progress <slug> --write --skill project-onboarding`.
6. Draft the next-meeting agenda (`meetings/<ts>_MTG-###_agenda.md`) from the Open Questions.
7. Report: counts per feature status, top risks, open questions, links to `20-Views/*.html`. Open the views in the machine's **default browser** (Windows: `start "" "<full path>"`; macOS: `open`; Linux: `xdg-open`) — never the built-in Browser pane.

## Locations: which folder is each project in, on THIS computer
Shared data (Portfolio/, ProjectWorkspace/) never holds absolute paths, so it can be synced between computers
(Obsidian Sync / OneDrive / git). Everything machine-specific is in `~/.claude/wirat-workflow/local.json`, managed with:
| Wirat says | Command (always `--dry-run` first, then confirm) |
|---|---|
| "ดูว่าแต่ละ project อยู่ที่ไหน" | `wf.py projects list` (add `--json`), `wf.py projects check` |
| "map project X ไปที่ D:\code\x" | `wf.py projects map X --repo <folder>` (and/or `--workspace <ProjectWorkspace folder>`) |
| "เครื่องนี้ไม่มี path ของ X แล้ว / ลืม mapping" | `wf.py projects unmap X [--repo \| --workspace]` — only forgets on this computer, deletes nothing |
| "เพิ่ม project ที่ workspace อยู่โฟลเดอร์อื่น" | `wf.py projects add X --workspace <folder> [--repo <folder>]` |
| "สร้าง project ใหม่ แต่เก็บ workspace ไว้ที่ …" | `wf.py new-workspace X --name … --repo <folder> --at <folder>` |
| "ลบ/เลิกใช้ project X" | `wf.py projects remove X` (needs `--yes` when Wirat has open tasks) — archives it for ALL computers, files kept; `projects restore X` undoes it |
| "ค้นหา repo ให้" | `wf.py projects scan <parent folder> [--apply]` (matches by git remote, then folder name) |
| "workspace ย้ายไปที่ …" | `wf.py projects set-workspace <folder>` |
| "ตั้งค่าเครื่องใหม่" | `wf.py setup --workspace <shared workspace> --scan <folder with repos>` (`--init` for a brand-new workspace) |
| "เอา workflow ไปใช้เครื่องอื่น" | `wf.py kit pack --out <zip>`; on the other computer `wf.py kit install <zip>` then `setup` (never overwrites CLAUDE.md or non-Wirat skills; replaced files go to `~/.claude/backups/`) |
| "update progress.html / view เก่า" | `wf.py views [--project X]` — upgrades the 3 HTML files from the template, old copy kept as `20-Views/_prev/*.bak`, no new .html files |
| journey เก่าหนัก / validate เตือน | `wf.py journey-compact --all` (one-time migration to one-file-per-event) |
After a mapping change run `wf.py projects check`. Old data that still contains an absolute repo path: `wf.py projects migrate`.

## Output files
- `Projects/<slug>/ProjectWorkspace/**` (from `~/.claude/wirat-workflow/templates/ProjectWorkspace`)
- `00-Project/<ts>_feature-inventory.md`, `<ts>_project-overview.md`, `modules/<ts>_module-map.md`, `stakeholders/*.md`, `meetings/<ts>_MTG-###_agenda.md`
- `10-Data/backlog.json`, `journey.json`, `progress.json`, `data.js`
- `Portfolio/projects.json`, `Portfolio/portfolio-data.js`

## Guardrails
- **Never modify source code, configs, or git state** in the project repo (no install, no format, no commit).
- Never overwrite an existing workspace (`new-workspace` refuses).
- User-level files (`~/.claude/**`) are not changed when onboarding a project.
- Every status cites evidence; otherwise `Unknown / Needs confirmation`.
- Confirm the file list before writing.

## Example output
```
ใช้ skill: project-onboarding — สแกน repo แบบ read-only แล้วร่าง workspace ให้ food-delivery

สรุปจากการสแกน (evidence อยู่ใน Feature Inventory):
| สถานะ | จำนวน |
|---|---|
| Implemented | 6 (เช่น Login – src/routes/auth.ts, tests/auth.test.ts) |
| Partially Implemented | 3 (Payment – มี route แต่ไม่มี webhook handler) |
| Planned | 2 (Rider tracking – อยู่ใน docs/roadmap.md) |
| Unknown / Needs confirmation | 2 (Promo code – มีตารางใน schema แต่ไม่มีโค้ดใช้) |

Open Questions สำหรับประชุมครั้งถัดไป:
- OQ-007 Promo code ยังอยู่ใน scope ไหม? — owner: nok — target: MTG-004 (2026-11-05)

ไฟล์ที่จะสร้าง (รอ ok):
- create tree: ~/Obsidian/Wirat-Workspace/Projects/food-delivery/ProjectWorkspace
- create: .../00-Project/stakeholders/nok.md, .../stakeholders/ton.md
- update: .../10-Data/backlog.json (8 tasks, 3 OQs) …
```

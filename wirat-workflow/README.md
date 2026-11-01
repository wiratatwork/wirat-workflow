# Wirat Workflow — user-level toolkit

| Path | Purpose |
|---|---|
| `~/.claude/CLAUDE.md` | Profile, rules, skill routing (loaded every session) |
| `~/.claude/skills/<14 skills>/SKILL.md` | project-onboarding, meeting-intake, clarify, project-memory, work-management, progress-view, delivery-metrics, capacity-planner, estimate-assistant, plan-change-control, build-loop, quality-gate, uat-manager, delivery-report |
| `config.json` | owner, workspace path, plan fields, required task fields, min history (3) |
| `scripts/wf.py` | Deterministic helper used by the skills (revisions, IDs, capacity, metrics, plan-change gate, exec-plan gate, UAT xlsx, data bundles) |
| `templates/ProjectWorkspace/` | Copied by `wf.py new-workspace` — includes the 3 HTML views (created once per project) |
| `templates/artifacts/` | task, stakeholder, decision, meeting agenda/note, open question, clarify options, plan-change input, execution plan, UAT input, estimate, delivery report |
| `tests/make_fixtures.py` | Builds the sample workspace (3 projects) |
| `tests/run_tests.py` | 24 acceptance tests (temp copy; never touches the real workspace) |

## wf.py commands
```
python -I ~/.claude/wirat-workflow/scripts/wf.py [--dry-run] <command>
  new-workspace <slug> --name --repo     onboard (refuses if exists)
  next-id TASK|DEC|OQ|PCP|MTG|UAT         portfolio-unique ids
  revise <file.md>                        new timestamped revision + latest.json
  progress [slug|--all] [--write]         health / risks (print or write progress.json + bundle)
  capacity [--write]                      cross-project workload, conflicts
  validate [slug]                         required fields, OQ owner/meeting, deps, cycles
  update-task TASK --set k=v              NON-plan fields only (exit 3 on plan fields / proposed -> active)
  accept TASK --actual-days N --variance  User acceptance -> delivery metric
  estimate --type --complexity --base-days  history (n>=3) + capacity impact
  propose-change --input f.json           Plan Change Proposal (ops: set | add_task | cancel | activate)
  approve-change PCP --by wirat           approval = new revision
  reject-change PCP
  apply-change PCP                        only if approved by wirat; stale check
  check-exec-plan plan.md                 multi-agent gate (exit 1 on FAIL)
  uat-revise <slug> --input f.json        new UAT .xlsx revision + latest.json
  stakeholder <id>                        owned / waiting / OQs / impact on Wirat (hours, downstream, due)
  add-question <slug> --question --owner --target-meeting [--tasks] [--options a|b]
  update-question OQ-x [--answer] [--question] [--owner] [--target-meeting] [--status] [--decision]
  journey-add <slug> --type --title [--module-event 'mod|stage|change' ...]
  decision-new <slug> --title --context --decision [--alternatives a|b] [links...]   (+ journey)
  skill-rank [--candidates a,b]          tie-break for ambiguous requests
  metrics | bundle | log-skill <skill>
  tasks [--project --status --health --owner --stakeholder --due-before --limit]   one line per task (capped)
  journey <slug> [--since --until --type --module --task --decision --search --limit --full | --digest]   windowed history (capped)
  journey-compact [slug|--all] [--rebuild]   migrate old single-file journey / rebuild its digest
  artifacts <slug> [--kind decisions|meetings|releases|stakeholders|backlog|all] [-n 5]   current revisions, one line each
  projects list|map|unmap|add|remove|restore|set-workspace|check|scan|which|migrate   where projects live on THIS computer
  setup --workspace <folder> [--scan <folders>] [--init]   first run on a computer
  kit pack|install                          carry the user-level workflow to another computer
  views [--project slug] [--force]          upgrade the 3 HTML views from the template (old copy -> _prev/*.bak)
  new-workspace <slug> --name --repo <folder> [--at <folder>]   (--at = ProjectWorkspace outside <workspace>/Projects)
```
Env: `WF_WORKSPACE` (workspace root), `WF_TODAY` (YYYY-MM-DD) — used by tests.

## Revision policy
- Markdown / Excel artifacts: never edited. New file `YYYYMMDD-HHMMSS_<name>` with `revision`, `supersedes`; `latest.json` in the folder points to the current one.
- JSON feeds (`10-Data/*.json`, `Portfolio/*.json`): every write creates an immutable `revisions/<ts>_<name>.json`; `latest.json` in the same folder points to the current one (the first managed write keeps the pre-existing file as revision 1). The plain `<name>.json` is a generated mirror; readers follow the pointer and `validate` flags hand edits.
- Same-second collisions get `-2` in the timestamp (`<ts>-2_<name>`), never in the name.
- HTML views: created once by onboarding, never regenerated. They read `10-Data/data.js` + `Portfolio/portfolio-data.js` (generated mirrors of the JSON, so `file://` works without a server), fall back to `fetch` of the JSON, then to a file picker.

## Long projects: keeping the context small
Everything that grows is stored so that nothing has to read all of it:
- **Journey** = one immutable file per event (`10-Data/journey-events/<YYYY-MM>/EV-<ts>.json`, title <= 160 and summary <= 600 chars,
  longer text goes in a meeting note / decision record and is linked with `--ref`). `10-Data/journey.json` is only a digest (counts,
  last 15 events, current state per module — a few KB however long the project). `journey.html` loads one month at a time
  (`10-Data/journey-data/<YYYY-MM>.js`), the two newest by default.
- **Reading** = capped commands (`tasks`, `journey`, `artifacts`, `stakeholder`, `progress`), output <= ~6000 chars with a
  "N more not shown" line. Skills never read the JSON feeds, `revisions/`, or `journey-events/` directly (CLAUDE.md section 3b).
- **Writing** never copies history: an event is one small new file; the digest revision is a few KB.

## Several computers / projects in different folders
- Shared (sync it): the workspace folder (`Portfolio/`, `Projects/<slug>/ProjectWorkspace/`). It contains **no absolute paths**.
- Per computer (never synced): `~/.claude/wirat-workflow/local.json` = workspace root, each project's source folder, and optionally a
  ProjectWorkspace kept outside the standard place. Edit it only through `wf.py projects ...` / `wf.py setup`.
- New computer: `kit pack` on the old one -> copy the zip -> `kit install <zip>` -> `setup --workspace <synced folder> --scan <folder with repos>`
  -> `projects check`. Do not edit the same workspace from two computers at the same time without a sync tool that handles conflicts
  (`id-registry.json` hands out IDs).
- Moved a folder? `projects map <slug> --repo <new>` (or `--workspace`). Retired a project? `projects remove <slug>` (archives for all
  computers, deletes nothing; `restore` undoes it).

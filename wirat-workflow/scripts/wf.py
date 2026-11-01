#!/usr/bin/env python3
"""Wirat workflow helper CLI.

Every skill in ~/.claude/skills/<wirat-skill> calls this script for the parts that
must be deterministic: revisions, IDs, capacity math, delivery metrics, plan-change
guards, execution-plan checks, UAT Excel revisions and the data bundles the HTML
views read.

Rules enforced here (see ~/.claude/CLAUDE.md):
  * Markdown/Excel artifacts are never modified; `revise` makes a timestamped copy.
  * JSON data feeds are never modified either: every write creates revisions/<ts>_<name>
    and updates latest.json; the plain <name> file is a generated mirror.
  * Plan fields can only change through an approved Plan Change Proposal.
  * Every write command supports --dry-run, which prints the target files only.

Usage: python -I wf.py <command> [options]   (python -I wf.py -h for the list)
Env:   WF_WORKSPACE overrides the workspace root, WF_TODAY overrides today (YYYY-MM-DD).
"""
import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

WF_HOME = Path(__file__).resolve().parent.parent
CONFIG = json.loads((WF_HOME / "config.json").read_text(encoding="utf-8"))
TEMPLATE_WS = WF_HOME / "templates" / "ProjectWorkspace"
DONE = set(CONFIG["done_statuses"])
PLAN_FIELDS = set(CONFIG["plan_fields"])
OWNER = CONFIG["owner"]


# ---------------------------------------------------------------- basics

LOCAL_CFG = Path(os.environ.get("WF_LOCAL_CONFIG") or (WF_HOME / "local.json"))


def local_cfg():
    """Machine-local settings (never synced, never in the kit): workspace root and where each project's
    repo / ProjectWorkspace lives on THIS computer. Shape: {"workspace": str, "projects": {slug: {"repo", "workspace"}}}."""
    try:
        return json.loads(LOCAL_CFG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def workspace():
    local = local_cfg().get("workspace")
    return Path(os.path.expanduser(os.environ.get("WF_WORKSPACE") or local or CONFIG["workspace"]))


def portfolio():
    return workspace() / "Portfolio"


def today():
    v = os.environ.get("WF_TODAY")
    return dt.date.fromisoformat(v) if v else dt.date.today()


def now_iso():
    return dt.datetime.now().replace(microsecond=0).isoformat()


def stamp():
    return dt.datetime.now().strftime(CONFIG["timestamp_format"])


def d(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def die(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def load_feed(p, default=None):
    """Read a JSON data feed from its latest revision (falls back to the mirror file)."""
    p = Path(p)
    ptr = load_json(p.parent / "latest.json", None)
    if isinstance(ptr, dict) and isinstance(ptr.get(p.name), dict):
        f = p.parent / ptr[p.name]["file"]
        if f.exists():
            return load_json(f, default)
    return load_json(p, default)


def slugify(s):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.strip().lower()).strip("-")
    return s[:50] or "item"


class Writer:
    """All file writes go through here so --dry-run can list targets without writing."""

    def __init__(self):
        self.dry = False
        self.planned = []

    def _plan(self, action, path):
        self.planned.append((action, str(path)))
        if self.dry:
            print(f"[dry-run] {action}: {path}")

    def text(self, path, content, action="write"):
        path = Path(path)
        self._plan(action if path.exists() else "create", path)
        if self.dry:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def new_text(self, path, content):
        if Path(path).exists():
            die(f"refusing to overwrite existing artifact {path}")
        self.text(path, content, "create")

    def json(self, path, obj, history=True):
        """history=True marks a JSON data feed (backlog, journey, progress, capacity, metrics, ...).
        Each version becomes a new immutable file revisions/<ts>_<name>, <dir>/latest.json points at
        the current one, and <name> itself is only a generated mirror (like data.js) kept so humans
        and the spec's file names keep working. Readers use load_feed(), which follows the pointer."""
        path = Path(path)
        text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
        if not history:
            self.text(path, text, "update")
            return
        ptr_p = path.parent / "latest.json"
        ptr = load_json(ptr_p, {}) or {}
        entry = ptr.get(path.name)
        rev, prev = (entry["revision"], entry["file"]) if entry else (0, None)
        taken = []
        if entry is None and path.exists():
            # first managed write: keep the pre-revision original untouched as revision 1
            first = stamped(path.parent / "revisions", path.name)
            self.copy(path, first)
            taken.append(first)  # in --dry-run the copy does not exist yet
            rev, prev = 1, f"revisions/{first.name}"
        new = stamped(path.parent / "revisions", path.name, taken)
        self.text(new, text, "create revision")
        ptr[path.name] = {"file": f"revisions/{new.name}", "revision": rev + 1, "supersedes": prev,
                          "updated_at": now_iso()}
        self.text(ptr_p, json.dumps(ptr, ensure_ascii=False, indent=2) + "\n", "update pointer")
        self.text(path, text, "update mirror")

    def copy(self, src, dst):
        self._plan("copy", f"{src} -> {dst}")
        if self.dry:
            return
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def copytree(self, src, dst):
        self._plan("create tree", dst)
        if not self.dry:
            shutil.copytree(src, dst)


W = Writer()


def stamped(folder, name, taken=()):
    """folder/<ts>_<name>, adding -2, -3 to the timestamp (never to the name) when it already exists,
    so the artifact's base name stays the same across revisions."""
    ts = stamp()
    cand = Path(folder) / f"{ts}_{name}"
    i = 2
    while cand.exists() or cand in taken:
        cand = Path(folder) / f"{ts}-{i}_{name}"
        i += 1
    return cand


def unique(path):
    path = Path(path)
    if not path.exists():
        return path
    i = 2
    while True:
        cand = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not cand.exists():
            return cand
        i += 1


# ---------------------------------------------------------------- frontmatter

def parse_fm(text):
    """Minimal YAML frontmatter parser: scalars, inline [a, b] lists and '- x' lists."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return {}, text
    head = parts[0][3:].strip("\n")
    body = parts[1].lstrip("-").lstrip("\n")
    data, key = {}, None
    for line in head.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^\s+-\s*(.*)$", line)
        if m and key:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(_scalar(m.group(1)))
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            data[key] = _scalar(val) if val != "" else []
    return data, body


def _scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [_scalar(x) for x in inner.split(",")] if inner else []
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v in ("null", "~"):
        return None
    if v in ("true", "false"):
        return v == "true"
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    return v


def dump_fm(data):
    out = ["---"]
    for k, v in data.items():
        if isinstance(v, list):
            if not v:
                out.append(f"{k}: []")
            else:
                out.append(f"{k}:")
                out += [f"  - {x}" for x in v]
        elif v is None:
            out.append(f"{k}: null")
        elif isinstance(v, bool):
            out.append(f"{k}: {'true' if v else 'false'}")
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- projects / tasks

def registry():
    """Portable project registry (Portfolio/projects.json): slug, name, repo_name, remote, status. No absolute paths."""
    return load_feed(portfolio() / "projects.json", {"projects": []}) or {"projects": []}


def archived_slugs():
    return {p["slug"] for p in registry().get("projects", []) if p.get("status") == "archived"}


def _xp(p):
    return Path(os.path.expanduser(str(p)))


def local_project(slug):
    return (local_cfg().get("projects") or {}).get(slug, {})


def ws_dir(slug):
    """Where this project's ProjectWorkspace is on this machine: a local mapping, else the standard place."""
    over = local_project(slug).get("workspace")
    return _xp(over) if over else workspace() / "Projects" / slug / "ProjectWorkspace"


def repo_of(slug):
    """Source-code folder of a project on THIS machine (None when not mapped)."""
    r = local_project(slug).get("repo")
    return _xp(r) if r else None


def project_slugs(include_archived=False):
    names = set()
    root = workspace() / "Projects"
    if root.exists():
        names |= {p.name for p in root.iterdir() if (p / "ProjectWorkspace").is_dir()}
    names |= {s for s, v in (local_cfg().get("projects") or {}).items()
              if v.get("workspace") and _xp(v["workspace"]).is_dir()}
    if not include_archived:
        names -= archived_slugs()
    return sorted(names)


def pws(slug):
    p = ws_dir(slug)
    if not p.is_dir():
        die(f"project '{slug}' has no ProjectWorkspace on this machine at {p} "
            f"(known: {', '.join(project_slugs()) or 'none'}). Map it: wf.py projects add {slug} --workspace <folder>")
    return p


def data_path(slug, name):
    return pws(slug) / "10-Data" / name


def load_backlog(slug):
    return load_feed(data_path(slug, "backlog.json"), {"project": slug, "tasks": [], "open_questions": []})


def all_tasks():
    out = []
    for s in project_slugs():
        for t in load_backlog(s).get("tasks", []):
            t = dict(t)
            t.setdefault("project", s)
            out.append(t)
    return out


def find_task(task_id):
    hits = []
    for s in project_slugs():
        bl = load_backlog(s)
        for t in bl.get("tasks", []):
            if t.get("id") == task_id:
                hits.append((s, bl, t))
    if not hits:
        die(f"task {task_id} not found in any project")
    if len(hits) > 1:
        die(f"task {task_id} exists in several projects: {[h[0] for h in hits]}")
    return hits[0]


def load_capacity_cfg():
    return load_feed(portfolio() / "capacity.json", {}) or {}


TS_PREFIX = re.compile(r"^\d{8}-\d{4,6}(-\d+)?_")


def ts_key(p):
    """Chronological key for <ts>[-n]_name files: plain string order would put '<ts>-2_' before '<ts>_'."""
    m = re.match(r"^(\d{8})-(\d{4,6})(?:-(\d+))?_", Path(p).name)
    return (m.group(1) + m.group(2).ljust(6, "0"), int(m.group(3) or 1), Path(p).name) if m else ("", 0, Path(p).name)


def current_md_files(folder):
    """One file per artifact in a revised folder: the revision latest.json points to, else the
    newest timestamped copy, else the original. Superseded revisions are skipped."""
    if not folder.exists():
        return []
    latest = load_json(folder / "latest.json", {}) or {}
    groups = {}
    for f in folder.glob("*.md"):
        if f.name.startswith("_"):
            continue
        groups.setdefault(TS_PREFIX.sub("", f.name), []).append(f)
    out = []
    for base, files in sorted(groups.items()):
        ptr = latest.get(base, {}).get("file") if isinstance(latest.get(base), dict) else None
        pick = next((f for f in files if f.name == ptr), None)
        if pick is None:
            revs = sorted((f for f in files if TS_PREFIX.match(f.name)), key=ts_key)
            pick = revs[-1] if revs else files[0]
        out.append(pick)
    return out


def stakeholders(slug):
    out = []
    folder = pws(slug) / "00-Project" / "stakeholders"
    for f in current_md_files(folder):
        fm, _ = parse_fm(f.read_text(encoding="utf-8"))
        if fm.get("type") == "stakeholder":
            fm.setdefault("id", TS_PREFIX.sub("", f.stem))
            fm["project"] = fm.get("project") or slug
            fm["file"] = f.name
            out.append(fm)
    return out


# ---------------------------------------------------------------- ids

def next_id(kind, write=True, floor=0):
    kind = kind.upper()
    reg_p = portfolio() / "id-registry.json"
    reg = load_json(reg_p, {}) or {}
    reg[kind] = max(reg.get(kind, 0), floor)  # never hand out an id already used in an artifact
    if kind == "TASK":
        # never reuse an id that already exists somewhere
        used = [int(m.group(1)) for t in all_tasks() if (m := re.match(r"TASK-(\d+)", t.get("id", "")))]
        reg[kind] = max([reg.get(kind, 0)] + used)
    n = reg.get(kind, 0) + 1
    reg[kind] = n
    if write:
        W.json(reg_p, reg, history=False)
    return f"{kind}-{n:03d}"


# ---------------------------------------------------------------- calendar & health

def working_days(start, end, cap):
    """Working dates in [start, end] (inclusive), excluding weekends and non_working_dates."""
    if start is None or end is None or end < start:
        return []
    off = {d(x) for x in cap.get("non_working_dates", [])}
    wd = set(cap.get("working_weekdays", [0, 1, 2, 3, 4]))
    out, cur = [], start
    while cur <= end:
        if cur.weekday() in wd and cur not in off:
            out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def eff_hours_per_day(cap):
    return float(cap.get("working_hours_per_day", 8)) * float(cap.get("focus_factor", 0.75))


def remaining_hours(t, cap):
    est = t.get("estimate_days")
    if est is None:
        return None
    pct = float(t.get("progress", 0) or 0)
    return float(est) * float(cap.get("working_hours_per_day", 8)) * max(0.0, 1 - pct / 100)


def health(t, cap=None, ref=None):
    cap = cap or load_capacity_cfg()
    ref = ref or today()
    st = t.get("status")
    if st in DONE:
        return "done"
    if st == "proposed":
        return "proposed"
    if t.get("waiting_on") == "user":
        return "waiting-user"
    if t.get("waiting_on") == "manager":
        return "waiting-manager"
    if st == "blocked" or t.get("blocked_by"):
        return "blocked"
    due = d(t.get("due"))
    if due is None or t.get("estimate_days") is None:
        return "unknown"
    if due < ref:
        return "delayed"
    if t.get("risk") == "high":
        return "at-risk"
    need = remaining_hours(t, cap) or 0
    avail = len(working_days(ref, due, cap)) * eff_hours_per_day(cap)
    return "at-risk" if need > avail else "on-track"


def capacity_risk_ids(capacity):
    ids = set()
    for c in capacity.get("conflicts", []):
        if c["type"] == "deadline":
            ids.add(c["task"])
        elif c["type"] == "deadline-backlog":
            ids.update(c["tasks"])
    return ids


def with_health(t, cap, ref, risk_ids):
    """Task copy with computed health; on-track work that the cross-project queue cannot fit becomes at-risk."""
    t = dict(t)
    t["health"] = health(t, cap, ref)
    if t["health"] == "on-track" and t.get("id") in risk_ids:
        t["health"] = "at-risk"
        t["health_reason"] = "capacity: queued work across projects exceeds available hours before due"
    return t


def week_bounds(ref, cap):
    start = ref - dt.timedelta(days=ref.weekday())
    if ref.weekday() >= 5:  # weekend -> plan the coming week
        start += dt.timedelta(days=7)
    return start, start + dt.timedelta(days=4)


# ---------------------------------------------------------------- capacity

def compute_capacity(tasks=None, ref=None, cap=None):
    cap = cap or load_capacity_cfg()
    ref = ref or today()
    tasks = all_tasks() if tasks is None else tasks
    wk_start, wk_end = week_bounds(ref, cap)
    hpd = eff_hours_per_day(cap)
    week_days = working_days(wk_start, wk_end, cap)
    week_capacity = round(len(week_days) * hpd - float(cap.get("leave_hours_this_week", 0)), 1)

    mine = [t for t in tasks if t.get("owner") == OWNER and t.get("status") not in DONE | {"proposed"}]
    per_project, unknown = {}, []
    for t in mine:
        proj = t.get("project")
        p = per_project.setdefault(proj, {"name": proj, "active_tasks": 0, "committed_hours_this_week": 0.0})
        p["active_tasks"] += 1
        rem, due = remaining_hours(t, cap), d(t.get("due"))
        if rem is None or due is None:
            unknown.append(t["id"])
            continue
        begin = max(ref, d(t.get("start")) or ref)
        span = working_days(begin, due, cap) if due >= begin else []
        if not span:  # overdue or due before it can start: all remaining work lands now
            p["committed_hours_this_week"] += rem
            continue
        per_day = rem / len(span)
        p["committed_hours_this_week"] += per_day * sum(1 for x in span if wk_start <= x <= wk_end)

    for p in per_project.values():
        p["committed_hours_this_week"] = round(p["committed_hours_this_week"], 1)
    committed = round(sum(p["committed_hours_this_week"] for p in per_project.values()), 1)

    conflicts = []
    if committed > week_capacity:
        conflicts.append({
            "type": "overcommit",
            "severity": "high",
            "detail": f"committed {committed}h > capacity {week_capacity}h for week {wk_start}..{wk_end}",
        })
    # deadline feasibility: earliest-deadline-first over remaining work.
    # Tasks due within the next two weeks are reported one by one; later breaches are summarised once.
    cum, later = 0.0, []
    horizon = wk_end + dt.timedelta(days=7)
    for t in sorted([t for t in mine if d(t.get("due")) and remaining_hours(t, cap)],
                    key=lambda t: (d(t["due"]), t.get("priority", "P9"))):
        cum += remaining_hours(t, cap)
        due = d(t["due"])
        if due < ref:
            conflicts.append({"type": "overdue", "severity": "high", "task": t["id"], "project": t.get("project"),
                              "due": t["due"], "detail": f"{round(remaining_hours(t, cap), 1)}h of work left after due date"})
            continue
        avail = len(working_days(ref, due, cap)) * hpd
        if cum <= avail + 0.01:
            continue
        if due <= horizon:
            conflicts.append({
                "type": "deadline", "severity": "high" if due <= wk_end else "medium",
                "task": t["id"], "project": t.get("project"), "due": t["due"],
                "detail": f"needs {round(cum, 1)}h of queued work by {t['due']} but only {round(avail, 1)}h available",
            })
        else:
            later.append((t, cum - avail))
    if later:
        conflicts.append({
            "type": "deadline-backlog", "severity": "medium",
            "tasks": [t["id"] for t, _ in later],
            "detail": f"{len(later)} later task(s) not feasible at current load; max shortfall "
                      f"{round(max(s for _, s in later), 1)}h by {later[-1][0]['due']}",
        })
    # commitment clusters: several projects due/UAT on the same day
    by_day = {}
    for t in mine:
        for key in ("due", "uat_date"):
            if d(t.get(key)) and d(t.get(key)) >= ref:
                by_day.setdefault(t[key], set()).add(t.get("project"))
    for day, projs in sorted(by_day.items()):
        if len(projs) > 1:
            conflicts.append({"type": "same-day-commitments", "severity": "medium", "date": day,
                              "projects": sorted(projs),
                              "detail": f"{len(projs)} projects have deadlines/UAT on {day}"})
    return {
        "generated_at": now_iso(),
        "as_of": ref.isoformat(),
        "week": {"start": wk_start.isoformat(), "end": wk_end.isoformat()},
        "working_hours_per_day": cap.get("working_hours_per_day", 8),
        "focus_factor": cap.get("focus_factor", 0.75),
        "working_weekdays": cap.get("working_weekdays", [0, 1, 2, 3, 4]),
        "non_working_dates": cap.get("non_working_dates", []),
        "leave_hours_this_week": cap.get("leave_hours_this_week", 0),
        "capacity_hours_this_week": week_capacity,
        "projects": sorted(per_project.values(), key=lambda p: p["name"]),
        "committed_hours_this_week": committed,
        "available_hours_this_week": round(week_capacity - committed, 1),
        "unknown_estimate_tasks": unknown,
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------- progress

def compute_progress(slug, ref=None):
    ref = ref or today()
    cap = load_capacity_cfg()
    bl = load_backlog(slug)
    capacity = compute_capacity(ref=ref, cap=cap)
    risk_ids = capacity_risk_ids(capacity)
    tasks = []
    for t in bl.get("tasks", []):
        t = with_health(t, cap, ref, risk_ids)
        t.setdefault("project", slug)
        tasks.append(t)
    by_id = {t["id"]: t for t in all_tasks()}
    counts = {}
    for t in tasks:
        counts[t["health"]] = counts.get(t["health"], 0) + 1
    dep_risks = []
    for t in tasks:
        if t["health"] in ("done", "proposed"):
            continue
        for dep in t.get("dependencies", []) or []:
            dt_ = by_id.get(dep)
            if dt_ is None:
                dep_risks.append({"task": t["id"], "dependency": dep, "reason": "dependency not found"})
                continue
            dh = health(dt_, cap, ref)
            if dh == "done":
                continue
            late = d(dt_.get("due")) and d(t.get("due")) and d(dt_["due"]) >= d(t["due"])
            if dh in ("delayed", "blocked", "waiting-user", "waiting-manager", "unknown") or late:
                dep_risks.append({"task": t["id"], "dependency": dep, "dependency_project": dt_.get("project"),
                                  "reason": f"dependency is {dh}" + ("; due on/after dependent task" if late else "")})
    uat =load_json(pws(slug) / "00-Project" / "uat" / "latest.json", None)
    usage = load_json(portfolio() / "skill-usage.json", {"counts": {}}) or {"counts": {}}
    top = sorted(usage.get("counts", {}).items(), key=lambda kv: -kv[1])[:8]
    return {
        "project": slug,
        "project_name": bl.get("project_name", slug),
        "generated_at": now_iso(),
        "as_of": ref.isoformat(),
        "summary": counts,
        "tasks": tasks,
        "stakeholders": stakeholders(slug),
        "open_questions": bl.get("open_questions", []),
        "dependency_risks": dep_risks,
        "capacity_conflicts": capacity["conflicts"],
        "uat": (uat or {}).get("summary"),
        "frequent_skills": [{"skill": k, "count": v} for k, v in top],
    }


# ---------------------------------------------------------------- stakeholder view

def all_open_questions():
    return [dict(q, project=s) for s in project_slugs() for q in load_backlog(s).get("open_questions", [])]


def stakeholder_view(sid, tasks=None, oqs=None, ref=None, cap=None):
    """What a stakeholder owns, what waits on them, and what their blockers cost Wirat."""
    ref, cap = ref or today(), cap or load_capacity_cfg()
    tasks = all_tasks() if tasks is None else tasks
    oqs = all_open_questions() if oqs is None else oqs
    open_ = {t["id"]: t for t in tasks if t.get("status") not in DONE}
    brief = lambda t: {"id": t["id"], "title": t.get("title"), "project": t.get("project"), "owner": t.get("owner"),
                       "due": t.get("due"), "health": t.get("health") or health(t, cap, ref)}
    owned = [t for t in open_.values() if t.get("owner") == sid]
    waiting = [t for t in open_.values() if sid in (t.get("blocked_by") or [])]
    my_oqs = [q for q in oqs if q.get("owner") == sid and q.get("status") != "answered"]
    oq_tasks = [open_[i] for q in my_oqs for i in q.get("linked_tasks", []) if i in open_]
    dependents = {}
    for t in open_.values():
        for dep in t.get("dependencies") or []:
            dependents.setdefault(dep, []).append(t["id"])
    roots = {t["id"] for t in owned + waiting + oq_tasks}
    seen, queue = set(), list(roots)
    while queue:  # everything downstream of the stakeholder's work or blockers
        for nxt in dependents.get(queue.pop(), []):
            if nxt not in seen and nxt not in roots:
                seen.add(nxt)
                queue.append(nxt)
    affected = {i: open_[i] for i in roots | seen if open_[i].get("owner") == OWNER}
    hours = lambda ts: round(sum(remaining_hours(t, cap) or 0 for t in ts), 1)
    dues = sorted(t["due"] for t in affected.values() if t.get("due"))
    return {
        "stakeholder": sid,
        "owned": [brief(t) for t in owned],
        "waiting_on_them": [brief(t) for t in waiting],
        "open_questions": [{k: q.get(k) for k in ("id", "project", "question", "target_meeting", "linked_tasks")} for q in my_oqs],
        "impact_on_wirat": {
            "blocked_tasks": [t["id"] for t in waiting if t.get("owner") == OWNER],
            "blocked_hours": hours([t for t in waiting if t.get("owner") == OWNER]),
            "downstream_tasks": sorted(seen),
            "affected_wirat_tasks": sorted(affected),
            "hours_at_risk": hours(affected.values()),
            "earliest_affected_due": dues[0] if dues else None,
            "projects": sorted({t.get("project") for t in affected.values()}),
            "delayed_owned": [t["id"] for t in owned if (t.get("health") or health(t, cap, ref)) == "delayed"],
        },
    }


def cmd_stakeholder(a):
    print(json.dumps(stakeholder_view(a.id), ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- bundle (for file:// HTML)

def bundle(quiet=False):
    """Mirror 10-Data/*.json into data.js files so the HTML views work from file:// without a server."""
    ref, cap = today(), load_capacity_cfg()
    capacity = compute_capacity(ref=ref, cap=cap)
    risk_ids = capacity_risk_ids(capacity)
    every, stakes, oqs, projects, journeys, uats = [], [], [], [], {}, {}
    for s in project_slugs():
        bl = load_backlog(s)
        prog = compute_progress(s, ref=ref)  # always fresh: a stored progress.json goes stale after every task change
        jour = journey_digest_of(s)  # digest only: the full history is loaded lazily by journey.html
        payload = {"project": s, "backlog": bl, "progress": prog, "journey": jour, "bundled_at": now_iso()}
        W.text(data_path(s, "data.js"),
               "// GENERATED by wf.py bundle from 10-Data/*.json. Do not edit; edit the JSON files.\n"
               f"window.WF_PROJECT_DATA = {json.dumps(payload, ensure_ascii=False)};\n", "update")
        write_journey_js(s)
        repo = repo_of(s)
        projects.append({"slug": s, "name": bl.get("project_name", s), "repo_mapped": bool(repo and repo.is_dir()),
                         "workspace_custom": bool(local_project(s).get("workspace")),
                         "journey_events": jour.get("total_events", 0)})
        journeys[s] = jour
        uats[s] = (load_json(pws(s) / "00-Project" / "uat" / "latest.json", {}) or {}).get("summary")
        for t in bl.get("tasks", []):
            t = with_health(t, cap, ref, risk_ids)
            t.setdefault("project", s)
            every.append(t)
        stakes += stakeholders(s)
        for q in bl.get("open_questions", []):
            oqs.append(dict(q, project=s))
    metrics = load_feed(portfolio() / "delivery-metrics.json", {"records": []}) or {"records": []}
    port = {
        "bundled_at": now_iso(),
        "as_of": ref.isoformat(),
        "owner": OWNER,
        "projects": projects,
        "tasks": every,
        "stakeholders": stakes,
        "open_questions": oqs,
        "journeys": journeys,
        "uat": uats,
        "stakeholder_impact": {
            sid: stakeholder_view(sid, every, oqs, ref, cap)["impact_on_wirat"]
            for sid in sorted(({s["id"] for s in stakes} | {t.get("owner") for t in every}
                               | {b for t in every for b in t.get("blocked_by") or [] if not str(b).startswith("TASK-")})
                              - {OWNER, None})},
        "capacity": capacity,
        "delivery_metrics": metrics.get("records", []),
        "skill_usage": load_json(portfolio() / "skill-usage.json", {"counts": {}}),
    }
    port["machine"] = platform.node()
    js = ("// GENERATED by wf.py bundle. Do not edit.\n"
          f"window.WF_PORTFOLIO_DATA = {json.dumps(port, ensure_ascii=False)};\n")
    W.text(portfolio() / "portfolio-data.js", js, "update")
    for s in project_slugs():  # a workspace mapped outside <workspace>/Projects cannot reach ../../../../Portfolio
        if local_project(s).get("workspace"):
            W.text(data_path(s, "portfolio-data.js"), js, "update")
    if not quiet:
        print(f"bundled {len(projects)} project(s), {len(every)} task(s)")


# ---------------------------------------------------------------- journey / decisions / skill log

# ---- journey v2: one immutable file per event, a small digest for everything that reads it
#
# Why: a long project makes the journey huge. Nothing (Claude, HTML, bundles) may need the whole history:
#   * 10-Data/journey-events/<YYYY-MM>/EV-<ts>.json   full events, written once, never rewritten
#   * 10-Data/journey.json (+ revisions)              digest only: counts, last 15 events (short), per-module state
#   * 10-Data/journey-data/<YYYY-MM>.js               generated per-month script, loaded lazily by journey.html
#   * wf.py journey ...                               windowed, capped queries — the only way skills read history
MAX_TITLE, MAX_SUMMARY, MAX_CHANGE, DIGEST_RECENT, DIGEST_MODULE_RECENT = 160, 600, 300, 15, 3
EVENT_KEYS = ("modules", "tasks", "stakeholders", "decision", "meeting", "plan_change", "ref")


def journey_events_dir(slug):
    return pws(slug) / "10-Data" / "journey-events"


def _short(ev, n=160):
    out = {k: ev[k] for k in ("id", "date", "type", "title") if k in ev}
    if ev.get("summary"):
        out["summary"] = ev["summary"][:n] + ("…" if len(ev["summary"]) > n else "")
    out.update({k: ev[k] for k in EVENT_KEYS if ev.get(k)})
    return out


def ev_key(e):
    """Chronological key: event date, then the id's timestamp, then its same-second counter as a NUMBER
    (plain string order would put '...-10' before '...-2')."""
    m = re.match(r"EV-(\d{8}-\d{6})(?:-(\d+))?$", str(e.get("id", "")))
    return (e.get("date", ""), m.group(1) if m else str(e.get("id", "")), int(m.group(2) or 1) if m else 0)


def journey_events(slug):
    """All events of a project, oldest first (reads small files; only used by queries / rebuilds)."""
    root = journey_events_dir(slug)
    evs = [json.loads(f.read_text(encoding="utf-8")) for f in root.rglob("EV-*.json")] if root.exists() else []
    return sorted(evs, key=ev_key)


def is_v2(j):
    return isinstance(j, dict) and j.get("version") == 2


def build_digest(slug, events):
    tl = [e for e in events if e.get("timeline", True)]
    periods, by_type, mods = {}, {}, {}
    for e in events:
        periods[e["date"][:7]] = periods.get(e["date"][:7], 0) + 1
    for e in tl:
        by_type[e.get("type", "?")] = by_type.get(e.get("type", "?"), 0) + 1
    for e in events:
        for me in e.get("module_events", []):
            m = mods.setdefault(me["module"], [])
            m.append(dict({k: v for k, v in me.items() if k != "module"}, date=me.get("date", e["date"])))
    return {"project": slug, "version": 2, "updated_at": now_iso(), "total_events": len(tl),
            "periods": [{"period": p, "count": c} for p, c in sorted(periods.items())], "by_type": by_type,
            "recent": [_short(e) for e in tl[-DIGEST_RECENT:]],
            "modules": [{"module": m, "event_count": len(v), "current": v[-1], "recent": v[-DIGEST_MODULE_RECENT:]}
                        for m, v in sorted(mods.items())]}


def digest_add(dg, ev):
    """Incrementally fold one new event into the digest (no need to re-read history)."""
    dg = dict(dg)
    per = {p["period"]: p["count"] for p in dg.get("periods", [])}
    per[ev["date"][:7]] = per.get(ev["date"][:7], 0) + 1
    dg["periods"] = [{"period": p, "count": c} for p, c in sorted(per.items())]
    if ev.get("timeline", True):
        dg["total_events"] = dg.get("total_events", 0) + 1
        dg["by_type"] = dict(dg.get("by_type", {}), **{ev.get("type", "?"): dg.get("by_type", {}).get(ev.get("type", "?"), 0) + 1})
        recent = (dg.get("recent", []) + [_short(ev)])
        dg["recent"] = sorted(recent, key=ev_key)[-DIGEST_RECENT:]
    mods = {m["module"]: dict(m) for m in dg.get("modules", [])}
    for me in ev.get("module_events", []):
        m = mods.setdefault(me["module"], {"module": me["module"], "event_count": 0, "recent": []})
        item = dict({k: v for k, v in me.items() if k != "module"}, date=me.get("date", ev["date"]))
        m["event_count"] = m.get("event_count", 0) + 1
        m["recent"] = sorted(m.get("recent", []) + [item], key=lambda x: x.get("date", ""))[-DIGEST_MODULE_RECENT:]
        m["current"] = m["recent"][-1]
    dg["modules"] = [mods[k] for k in sorted(mods)]
    dg["updated_at"] = now_iso()
    return dg


def _new_event_path(slug, date):
    root = journey_events_dir(slug) / date[:7]
    base, i = f"EV-{stamp()}", 1
    while (root / f"{base}{'' if i == 1 else f'-{i}'}.json").exists():
        i += 1
    eid = base if i == 1 else f"{base}-{i}"
    return eid, root / f"{eid}.json"


def _write_event(slug, entry, module_events=None, timeline=True):
    date = str(entry.get("date") or today().isoformat())[:10]
    eid, path = _new_event_path(slug, date)
    ev = {"id": eid, "date": date, "type": entry.get("type", "change"), "title": entry["title"]}
    if entry.get("summary"):
        ev["summary"] = entry["summary"]
    ev.update({k: entry[k] for k in EVENT_KEYS if entry.get(k)})
    ev["timeline"] = timeline
    ev["module_events"] = [dict(m, date=m.get("date", date)) for m in (module_events or [])]
    ev["created_at"] = now_iso()
    W.new_text(path, json.dumps(ev, ensure_ascii=False, indent=2) + "\n")
    return ev


def check_journey_text(entry, module_events):
    if len(entry.get("title", "")) > MAX_TITLE:
        die(f"journey title is {len(entry['title'])} chars (max {MAX_TITLE}). Keep the journey to one-liners.")
    if len(entry.get("summary") or "") > MAX_SUMMARY:
        die(f"journey summary is {len(entry['summary'])} chars (max {MAX_SUMMARY}). Put the long text in a meeting note / "
            f"decision record and link it with --ref <path relative to ProjectWorkspace>.")
    for m in module_events or []:
        if len(m.get("change", "")) > MAX_CHANGE:
            die(f"module event text is {len(m['change'])} chars (max {MAX_CHANGE})")


def migrate_legacy_journey(slug, legacy):
    """v1 journey.json ({timeline, modules[].evolution}) -> one file per event. Old feed revisions stay as history."""
    evs = []
    n = 0
    for e in legacy.get("timeline", []):
        e = dict(e)
        e["summary"] = (e.get("summary") or "")[:MAX_SUMMARY]
        evs.append(_write_event(slug, e, [], True)) if not W.dry else None
        n += 1
    for m in legacy.get("modules", []):
        for x in m.get("evolution", []):
            x = dict(x)
            mod = {"module": m["module"], **x}
            title = f"{m['module']}: {x.get('stage', 'change')}"
            ent = {"date": x.get("date") or "1970-01-01", "type": "module-evolution", "title": title}
            evs.append(_write_event(slug, ent, [mod], False)) if not W.dry else None
            n += 1
    return evs, n


def ensure_journey_v2(slug):
    """Make sure the project's journey is in the v2 layout; returns the digest (or None in --dry-run)."""
    p = data_path(slug, "journey.json")
    j = load_feed(p, None)
    if is_v2(j):
        return j
    legacy = j or {"timeline": [], "modules": []}
    evs, n = migrate_legacy_journey(slug, legacy)
    if W.dry:
        print(f"[dry-run] migrate legacy journey of {slug}: {n} event file(s) under 10-Data/journey-events/")
        return None
    dg = build_digest(slug, journey_events(slug))
    W.json(p, dg)
    return dg


def journey_append(slug, entry, module_events=None, timeline=True):
    """The one way anything gets onto the journey: a new immutable event file + an updated digest."""
    entry = dict(entry)
    entry.setdefault("date", today().isoformat())
    check_journey_text(entry, module_events)
    dg = ensure_journey_v2(slug)
    if W.dry:
        eid, path = _new_event_path(slug, entry["date"])
        W._plan("create", path)
        W._plan("update", data_path(slug, "journey.json"))
        return {"id": eid}
    ev = _write_event(slug, entry, module_events, timeline)
    W.json(data_path(slug, "journey.json"), digest_add(dg, ev))
    return ev


def append_journey(slug, entry, module_event=None):
    return journey_append(slug, entry, [module_event] if module_event else [])


def write_journey_js(slug, force=False):
    """Per-month scripts for journey.html (file:// cannot fetch JSON). Rewritten only when the month changed."""
    root = pws(slug) / "10-Data" / "journey-data"
    by = {}
    for e in journey_events(slug):
        by.setdefault(e["date"][:7], []).append(e)
    for period, evs in by.items():
        f = root / f"{period}.js"
        head = f"// GENERATED by wf.py bundle. count={len(evs)}\n"
        if not force and f.exists() and f.open(encoding="utf-8").readline() == head:
            continue
        W.text(f, head + f'window.WF_JOURNEY = window.WF_JOURNEY || {{}};\nwindow.WF_JOURNEY["{period}"] = '
               + json.dumps(evs, ensure_ascii=False) + ";\n", "update")


def journey_digest_of(slug):
    j = load_feed(data_path(slug, "journey.json"), None)
    if is_v2(j):
        return j
    if j and (j.get("timeline") or j.get("modules")):  # legacy, not migrated yet: build in memory, write nothing
        tmp = []
        for e in j.get("timeline", []):
            tmp.append(dict(e, id=e.get("id", "legacy"), timeline=True, module_events=[]))
        for m in j.get("modules", []):
            for x in m.get("evolution", []):
                tmp.append({"id": "legacy", "date": x.get("date", "1970-01-01"), "type": "module-evolution", "title": m["module"],
                            "timeline": False, "module_events": [dict(x, module=m["module"])]})
        return build_digest(slug, sorted(tmp, key=lambda e: e.get("date", "")))
    return build_digest(slug, [])


def create_decision(slug, title, context, decision, links=None, alternatives=None, status="accepted",
                    decided_by=OWNER, supersedes="", consequences=""):
    did = next_id("DEC")
    links = links or {}
    fm = {
        "type": "decision", "id": did, "title": title, "project": slug, "status": status,
        "date": today().isoformat(), "revision": 1, "created_at": now_iso(),
        "decided_by": decided_by,
        "meetings": links.get("meetings", []), "modules": links.get("modules", []),
        "tasks": links.get("tasks", []), "stakeholders": links.get("stakeholders", []),
        "uat": links.get("uat", []), "plan_change": links.get("plan_change", ""),
        "supersedes": supersedes,
    }
    alts = "\n".join(f"{i}. {a}" for i, a in enumerate(alternatives or [], 1)) or "- (none recorded)"
    body = (f"# {did}: {title}\n\n## Context\n{context}\n\n## Decision\n{decision}\n\n"
            f"## Alternatives considered (most → least recommended)\n{alts}\n\n## Consequences\n"
            f"{consequences or '- See linked tasks / plan change.'}\n")
    path = stamped(pws(slug) / "00-Project" / "decisions", f"{did}_{slugify(title)}.md")
    W.new_text(path, dump_fm(fm) + "\n" + body)
    return did, path


def log_skill(skill, project=None, note=""):
    p = portfolio() / "skill-usage.json"
    u = load_json(p, {"counts": {}, "log": []}) or {"counts": {}, "log": []}
    n = u.setdefault("counts", {}).get(skill, 0) + 1
    u["counts"][skill] = n
    u.setdefault("skills", {})[skill] = {"count": n, "last_used": now_iso(), "last_project": project}
    u.setdefault("log", []).append({"at": now_iso(), "skill": skill, "project": project, "note": note})
    W.json(p, u, history=False)  # usage metrics, not project data: one rolling file


def skill_ranking(candidates=None):
    """Skills ordered by usage (count, then most recent) — used to break ties between plausible skills."""
    u = load_json(portfolio() / "skill-usage.json", {}) or {}
    stats = u.get("skills", {})
    names = candidates or sorted(set(u.get("counts", {})) | set(stats))
    rows = [{"skill": s, "count": u.get("counts", {}).get(s, 0), "last_used": stats.get(s, {}).get("last_used")}
            for s in names]
    rows.sort(key=lambda r: r["last_used"] or "", reverse=True)  # most recent first ...
    return sorted(rows, key=lambda r: -r["count"])                 # ... within equal counts (stable sort)


# ---------------------------------------------------------------- commands

def git_info(path):
    """Remote URL / branch of a repo folder, {} when it is not a git repo or git is unavailable."""
    out = {}
    for key, tries in (("remote", [["remote", "get-url", "origin"]]),
                       ("branch", [["symbolic-ref", "--short", "HEAD"], ["rev-parse", "--short", "HEAD"]])):
        for args in tries:
            try:
                r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                return {}
            if r.returncode == 0 and r.stdout.strip():
                out[key] = r.stdout.strip()
                break
    return out


def norm_remote(url):
    """Same repo, different spelling (ssh/https/.git) -> same key."""
    u = (url or "").strip().lower()
    u = re.sub(r"^(https?|ssh|git)://", "", u)
    u = re.sub(r"^[^@/]+@", "", u).replace(":", "/", 1) if "@" in u.split("/")[0] else u
    return re.sub(r"\.git$", "", u).strip("/")


def set_local_project(slug, **kv):
    cfg = local_cfg()
    proj = cfg.setdefault("projects", {}).setdefault(slug, {})
    for k, v in kv.items():
        if v is None:
            proj.pop(k, None)
        else:
            proj[k] = str(v).replace("\\", "/")
    if not proj:
        cfg["projects"].pop(slug, None)
    save_local_cfg(cfg)


def save_local_cfg(cfg):
    cfg["machine"] = platform.node()
    cfg["updated_at"] = now_iso()
    W.text(LOCAL_CFG, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", "update")


def registry_upsert(slug, **fields):
    """Create / update a portable registry entry (feed revision). Never stores absolute paths."""
    reg = registry()
    ent = next((p for p in reg["projects"] if p["slug"] == slug), None)
    before = json.dumps(ent, sort_keys=True) if ent else None
    if ent is None:
        ent = {"slug": slug, "status": "active"}
        reg["projects"].append(ent)
    ent.update({k: v for k, v in fields.items() if v is not None and v != ""})
    if json.dumps(ent, sort_keys=True) != before:
        W.json(portfolio() / "projects.json", reg)
    return ent


def cmd_new_workspace(a):
    root = _xp(a.at) if a.at else workspace() / "Projects" / a.slug / "ProjectWorkspace"
    if root.exists() or (workspace() / "Projects" / a.slug / "ProjectWorkspace").exists():
        die(f"project '{a.slug}' already has a workspace ({root}); onboarding never overwrites one")
    W.copytree(TEMPLATE_WS, root)
    repo = _xp(a.repo) if a.repo else None
    info = git_info(repo) if repo and repo.is_dir() else {}
    if a.at:
        set_local_project(a.slug, workspace=root)
    if repo:
        set_local_project(a.slug, repo=repo)
    if W.dry:
        return
    for name in ("backlog.json", "progress.json", "journey.json"):
        p = root / "10-Data" / name
        obj = load_json(p, {})
        obj.update({"project": a.slug, "project_name": a.name or a.slug, "created_at": now_iso(), "updated_at": now_iso()})
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hint = f"{repo.name}" + (f" ({info['remote']})" if info.get("remote") else "") if repo else "Unknown / Needs confirmation"
    for md in (root / "00-Project").rglob("*.md"):
        md.write_text(md.read_text(encoding="utf-8")
                      .replace("{{project}}", a.slug).replace("{{project_name}}", a.name or a.slug)
                      .replace("{{repo_hint}}", hint).replace("{{created_at}}", now_iso()),
                      encoding="utf-8")
    registry_upsert(a.slug, name=a.name or a.slug, repo_name=repo.name if repo else None, remote=info.get("remote"),
                    onboarded_at=now_iso())
    bundle(quiet=True)
    print(f"created {root}")


def cmd_next_id(a):
    print(next_id(a.kind, write=not a.peek))


def cmd_revise(a):
    """Copy the latest revision of a markdown artifact into a new timestamped file."""
    src = Path(a.path)
    if not src.exists():
        die(f"{src} not found")
    folder = src.parent
    base = re.sub(r"^\d{8}-\d{6}(-\d+)?_", "", src.name)
    latest_p = folder / "latest.json"
    latest = load_json(latest_p, {}) or {}
    cur = folder / latest[base]["file"] if base in latest else src
    text = cur.read_text(encoding="utf-8")
    fm, body = parse_fm(text)
    rev = int(fm.get("revision", 1) or 1) + 1
    if fm:
        fm["revision"] = rev
        fm["supersedes"] = cur.name
        fm["updated_at"] = now_iso()
        text = dump_fm(fm) + "\n" + body
    dst = stamped(folder, base)
    W.new_text(dst, text)
    latest[base] = {"file": dst.name, "revision": rev, "supersedes": cur.name, "updated_at": now_iso()}
    W.json(latest_p, latest, history=False)
    print(dst)


def cmd_progress(a):
    slugs = project_slugs() if a.all or not a.project else [a.project]
    for s in slugs:
        prog = compute_progress(s)
        if a.write:
            W.json(data_path(s, "progress.json"), prog)
        else:
            print(json.dumps({k: prog[k] for k in ("project", "as_of", "summary", "dependency_risks", "capacity_conflicts")},
                             ensure_ascii=False, indent=2))
    if a.write:
        bundle(quiet=True)
        if a.skill:
            log_skill(a.skill, a.project, "progress refresh")


def cmd_capacity(a):
    cap = compute_capacity()
    if a.write:
        cfg = load_capacity_cfg()
        cfg.update(cap)
        W.json(portfolio() / "capacity.json", cfg)
        bundle(quiet=True)
    print(json.dumps(cap, ensure_ascii=False, indent=2))


def validate_project(slug):
    issues = []
    bl = load_backlog(slug)
    ids = {t["id"] for t in all_tasks()}
    for t in bl.get("tasks", []):
        for f in CONFIG["required_task_fields"]:
            if f not in t or t[f] in (None, ""):
                issues.append(f"{slug}/{t.get('id', '?')}: missing {f}")
        if not t.get("stakeholders") and t.get("stakeholders") != []:
            issues.append(f"{slug}/{t.get('id')}: stakeholders field missing")
        if t.get("status") not in CONFIG["task_statuses"]:
            issues.append(f"{slug}/{t.get('id')}: unknown status {t.get('status')}")
        for dep in t.get("dependencies", []) or []:
            if dep not in ids:
                issues.append(f"{slug}/{t.get('id')}: dependency {dep} does not exist")
    for q in bl.get("open_questions", []):
        if not q.get("owner") or not q.get("target_meeting"):
            issues.append(f"{slug}/{q.get('id', '?')}: open question needs owner and target_meeting")
    # dependency cycles
    graph = {t["id"]: t.get("dependencies", []) or [] for t in all_tasks()}
    seen, stack = set(), set()

    def visit(n, path):
        if n in stack:
            issues.append(f"dependency cycle: {' -> '.join(path + [n])}")
            return
        if n in seen:
            return
        seen.add(n)
        stack.add(n)
        for m in graph.get(n, []):
            visit(m, path + [n])
        stack.discard(n)

    for t in bl.get("tasks", []):
        visit(t["id"], [])
    return issues


def cmd_validate(a):
    slugs = [a.project] if a.project else project_slugs()
    issues = []
    for s in slugs:
        issues += validate_project(s)
    for p in ("capacity.json", "delivery-metrics.json"):
        if not (portfolio() / p).exists():
            issues.append(f"Portfolio/{p} missing")
    # mirrors must equal their latest revision; a difference means someone edited the mirror by hand
    folders = [portfolio()] + [pws(s) / "10-Data" for s in slugs]
    for folder in folders:
        ptr = load_json(folder / "latest.json", {}) or {}
        for name, e in ptr.items():
            rev_f = folder / e.get("file", "")
            if not rev_f.exists():
                issues.append(f"{folder.name}/latest.json: {name} points to missing {e.get('file')}")
            elif (folder / name).exists() and load_json(folder / name) != load_json(rev_f):
                if a.repair:  # the revision is the truth; the mirror is generated, so restoring it loses nothing
                    W.copy(rev_f, folder / name)
                    print(f"repaired: {folder.name}/{name} restored from {e['file']}")
                else:
                    issues.append(f"{folder.name}/{name} differs from its latest revision {e['file']} "
                                  f"(edited by hand? use wf.py commands; readers use the revision; "
                                  f"`wf.py validate --repair` restores the mirror)")
    for s in slugs:
        j = load_feed(data_path(s, "journey.json"), None)
        if j is not None and not is_v2(j):
            print(f"WARN: {s}: journey is in the old single-file format (token-heavy as it grows): wf.py journey-compact {s}")
        v = pws(s) / "20-Views" / "progress.html"
        if v.exists() and view_version(v.read_text(encoding="utf-8")) < view_version((TEMPLATE_WS / "20-Views" / "progress.html").read_text(encoding="utf-8")):
            print(f"WARN: {s}: HTML views are older than the template: wf.py views --project {s}")
    if issues:
        print("\n".join(issues))
        sys.exit(1)
    print(f"OK: {len(slugs)} project(s) valid")


def cmd_update_task(a):
    """Non-plan updates only (status, progress, blockers, waiting_on, risk, notes)."""
    slug, bl, t = find_task(a.task)
    changes = {}
    for kv in a.set or []:
        k, _, v = kv.partition("=")
        if k in PLAN_FIELDS:
            die(f"'{k}' is a plan field. Plan changes need a Plan Change Proposal "
                f"(plan-change-control skill): wf.py propose-change ...", code=3)
        changes[k] = _scalar(v) if not v.startswith("[") else [x.strip() for x in v[1:-1].split(",") if x.strip()]
    if changes.get("status") == "accepted":
        die("use `wf.py accept` so the delivery metric is recorded", code=3)
    if "status" in changes and changes["status"] not in CONFIG["task_statuses"]:
        die(f"unknown status {changes['status']}")
    if t.get("status") == "proposed" and changes.get("status", "proposed") not in ("proposed", "cancelled"):
        die(f"{a.task} is proposed (not in the plan yet). Bringing it into the plan is a scope change: "
            f"use a Plan Change Proposal with op 'activate' (plan-change-control skill)", code=3)
    before = {k: t.get(k) for k in changes}
    t.update(changes)
    bl["updated_at"] = now_iso()
    W.json(data_path(slug, "backlog.json"), bl)
    if not W.dry:
        W.json(data_path(slug, "progress.json"), compute_progress(slug))
        bundle(quiet=True)
    print(json.dumps({"task": a.task, "project": slug, "before": before, "after": changes}, ensure_ascii=False))


def cmd_accept(a):
    slug, bl, t = find_task(a.task)
    metrics_p = portfolio() / "delivery-metrics.json"
    metrics = load_feed(metrics_p, {"records": []}) or {"records": []}
    if any(r["task_id"] == a.task and r.get("status") == "accepted" for r in metrics["records"]):
        die(f"{a.task} already has an accepted delivery record")
    missing = [k for k in ("task_type", "complexity", "estimate_days") if t.get(k) in (None, "")]
    started = a.started or t.get("started") or t.get("start")
    uat_sent = a.uat_sent or t.get("uat_sent") or t.get("uat_date")
    if not started:
        missing.append("started")
    if not uat_sent:
        missing.append("uat_sent")
    if missing:
        die(f"cannot record delivery for {a.task}; missing {missing}. Ask Wirat (status: Unknown / Needs confirmation).")
    rec = {
        "task_id": a.task, "project": slug, "module": t.get("module"),
        "task_type": t["task_type"], "complexity": t["complexity"],
        "estimate_days": t["estimate_days"], "actual_days": a.actual_days,
        "started": started, "uat_sent": uat_sent, "user_accepted": a.accepted or today().isoformat(),
        "accepted_by": a.accepted_by or "", "variance_days": round(a.actual_days - float(t["estimate_days"]), 2),
        "variance_reason": a.variance or "", "status": "accepted", "recorded_at": now_iso(),
    }
    if abs(rec["variance_days"]) > 0 and not rec["variance_reason"]:
        die("actual differs from estimate: --variance reason is required")
    metrics["records"].append(rec)
    metrics["updated_at"] = now_iso()
    W.json(metrics_p, metrics)
    t["status"] = "accepted"
    t["progress"] = 100
    t["user_accepted"] = rec["user_accepted"]
    bl["updated_at"] = now_iso()
    W.json(data_path(slug, "backlog.json"), bl)
    append_journey(slug, {"type": "acceptance", "title": f"{a.task} accepted by User",
                          "summary": f"{t.get('title')} — estimate {rec['estimate_days']}d, actual {a.actual_days}d",
                          "modules": [t.get("module")], "tasks": [a.task]},
                   {"module": t.get("module"), "stage": "accepted", "change": t.get("title"), "task": a.task})
    if not W.dry:
        W.json(data_path(slug, "progress.json"), compute_progress(slug))
        bundle(quiet=True)
    log_skill("delivery-metrics", slug, a.task)
    print(json.dumps(rec, ensure_ascii=False, indent=2))


def similar_records(task_type, complexity):
    recs = (load_feed(portfolio() / "delivery-metrics.json", {"records": []}) or {}).get("records", [])
    acc = [r for r in recs if r.get("status") == "accepted"]
    exact = [r for r in acc if r.get("task_type") == task_type and r.get("complexity") == complexity]
    same_type = [r for r in acc if r.get("task_type") == task_type and r.get("complexity") != complexity]
    return exact, same_type


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def cmd_estimate(a):
    min_n = int(CONFIG.get("min_history_for_estimate", 3))
    exact, same_type = similar_records(a.type, a.complexity)
    basis = exact if len(exact) >= min_n else []
    ratios = [r["actual_days"] / r["estimate_days"] for r in basis if r.get("estimate_days")]
    ratio = median(ratios)
    base = a.base_days
    out = {"task_type": a.type, "complexity": a.complexity, "base_estimate_days": base,
           "history": {"exact_matches": len(exact), "same_type_other_complexity": len(same_type),
                       "minimum_required": min_n,
                       "records": [{k: r.get(k) for k in ("task_id", "project", "complexity", "estimate_days", "actual_days", "variance_reason")}
                                   for r in exact + same_type]}}
    if ratio is not None and base is not None:
        adj = round(base * ratio * 2) / 2
        spread = (min(ratios), max(ratios))
        out["history_adjustment"] = {"median_actual_to_estimate_ratio": round(ratio, 2),
                                     "ratio_range": [round(spread[0], 2), round(spread[1], 2)],
                                     "adjusted_estimate_days": adj,
                                     "range_days": [round(base * spread[0] * 2) / 2, round(base * spread[1] * 2) / 2]}
        out["confidence"] = "high" if len(basis) >= 6 else "medium"
        est = adj
    else:
        out["history_adjustment"] = None
        out["note"] = (f"Only {len(exact)} exact accepted record(s) (< {min_n}); history is shown as reference only "
                       "and is NOT used to adjust the estimate (no generalising from too few data points).")
        out["confidence"] = "low"
        est = base
    if est is not None:
        # capacity impact: when could Wirat finish this if it were queued after current committed work?
        cap = load_capacity_cfg()
        ref = today()
        hpd = eff_hours_per_day(cap)
        mine = [t for t in all_tasks() if t.get("owner") == OWNER and t.get("status") not in DONE | {"proposed"}]
        queued = sum(remaining_hours(t, cap) or 0 for t in mine)
        need = queued + est * float(cap.get("working_hours_per_day", 8))
        cur, acc_h = ref, 0.0
        while acc_h < need:
            if working_days(cur, cur, cap):
                acc_h += hpd
            cur += dt.timedelta(days=1)
        finish = cur - dt.timedelta(days=1)
        sim = dict(id="NEW", project=a.project or "(new)", owner=OWNER, status="todo", estimate_days=est,
                   due=(a.due or finish.isoformat()), start=ref.isoformat(), priority=a.priority or "P2")
        before = compute_capacity(ref=ref, cap=cap)
        after = compute_capacity(tasks=all_tasks() + [sim], ref=ref, cap=cap)
        out["capacity_impact"] = {
            "queued_hours_before": round(queued, 1),
            "earliest_finish_if_queued_last": finish.isoformat(),
            "available_hours_this_week_before": before["available_hours_this_week"],
            "available_hours_this_week_after": after["available_hours_this_week"],
            "new_conflicts": conflict_diff(before["conflicts"], after["conflicts"])[0],
        }
        out["estimate_days"] = est
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---- plan change control

def pcp_files(pcp_id):
    folder = portfolio() / "plan-changes"
    files = sorted(folder.glob(f"*_{pcp_id}_*.md"), key=ts_key) if folder.exists() else []
    if not files:
        die(f"plan change {pcp_id} not found in {folder}")
    return files


def read_pcp(path):
    text = Path(path).read_text(encoding="utf-8")
    fm, body = parse_fm(text)
    m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S)
    if not m:
        die(f"{path} has no ```json changes block")
    return fm, body, json.loads(m.group(1))


def apply_changes_to_tasks(tasks, changes):
    tasks = [dict(t) for t in tasks]
    for c in changes:
        op = c.get("op", "set")
        if op == "add_task":
            nt = dict(c["task"])
            nt.setdefault("project", c.get("project"))
            tasks.append(nt)
            continue
        t = next((t for t in tasks if t["id"] == c["task"]), None)
        if t is None:
            die(f"change references unknown task {c.get('task')}")
        if op == "set":
            t[c["field"]] = c["to"]
        elif op == "cancel":
            t["status"] = "cancelled"
        elif op == "activate":
            t["status"] = c.get("to", "todo")
    return tasks


def _change_cell(c):
    """'Proposed' column text for the proposal table."""
    if c.get("op") == "add_task":
        t = c["task"]
        return f"{t.get('title')} (owner {t.get('owner')}, due {t.get('due')}, {t.get('estimate_days')}d)"
    return str(c.get("to", "—"))


def conflict_key(c):
    return (c["type"], c.get("task") or c.get("date") or "")


def conflict_diff(before, after):
    bk, ak = {conflict_key(c) for c in before}, {conflict_key(c) for c in after}
    return [c for c in after if conflict_key(c) not in bk], [c for c in before if conflict_key(c) not in ak]


def conflict_lines(cs):
    if not cs:
        return "- (none)"
    return "\n".join(f"- `{c['type']}` {c.get('task', '')} {c['detail']}".replace("  ", " ") for c in cs)


def cmd_propose_change(a):
    spec = load_json(a.input)
    if not spec:
        die("--input must be a JSON file with title, reason, changes, alternatives")
    for k in ("title", "reason", "changes", "alternatives"):
        if not spec.get(k):
            die(f"proposal input missing '{k}'")
    if len(spec["alternatives"]) < 2:
        die("a proposal needs at least two alternatives ranked most → least recommended")
    for c in spec["changes"]:
        if c.get("op", "set") == "set":
            if c["field"] not in PLAN_FIELDS:
                die(f"'{c['field']}' is not a plan field; use update-task instead")
            _, _, t = find_task(c["task"])
            if "from" not in c:
                c["from"] = t.get(c["field"])
        elif c.get("op") == "add_task":
            if not c.get("project"):
                die("add_task needs 'project'")
            pws(c["project"])
            c["task"].setdefault("id", next_id("TASK"))
            c["task"].setdefault("project", c["project"])
            c["task"].setdefault("status", "todo")
            miss = [f for f in CONFIG["required_task_fields"] if c["task"].get(f) in (None, "")]
            if miss:
                die(f"new task {c['task']['id']} missing required fields {miss}")
        elif c.get("op") == "activate":
            _, _, t = find_task(c["task"])
            if t.get("status") != "proposed":
                die(f"{c['task']} is '{t.get('status')}', only proposed tasks can be activated")
            miss = [f for f in CONFIG["required_task_fields"] if t.get(f) in (None, "")]
            if miss:
                die(f"{c['task']} cannot enter the plan; missing required fields {miss}")
            c.update(field="status", to=c.get("to", "todo"))
            c["from"] = "proposed"
        elif c.get("op") != "cancel":
            die(f"unknown change op {c.get('op')!r} (set | add_task | cancel | activate)")
    pid = next_id("PCP")
    ref = today()
    before = compute_capacity(ref=ref)
    after = compute_capacity(tasks=apply_changes_to_tasks(all_tasks(), spec["changes"]), ref=ref)
    fm = {"type": "plan-change", "id": pid, "title": spec["title"], "status": "proposed",
          "projects": sorted({c.get("project") or find_task(c["task"])[0] for c in spec["changes"]}),
          "tasks": list(dict.fromkeys(c["task"] if isinstance(c["task"], str) else c["task"]["id"] for c in spec["changes"])),
          "requested_by": spec.get("requested_by", OWNER), "revision": 1, "created_at": now_iso(),
          "approved_by": None, "approved_at": None}
    rows = "\n".join(
        f"| {c.get('project') or find_task(c['task'])[0]} | {c.get('task') if isinstance(c.get('task'), str) else c['task']['id']} "
        f"| {c.get('op', 'set')} {c.get('field', '')} | {c.get('from', '—')} | {_change_cell(c)} |"
        for c in spec["changes"])
    alts = []
    for i, alt in enumerate(spec["alternatives"], 1):
        alts.append(f"### {i}. {alt['title']}" + ("  ⭐ Recommended" if i == 1 else "") + "\n" + "\n".join(
            f"- **{lbl}:** {alt.get(key, 'Unknown / Needs confirmation')}" for key, lbl in (
                ("description", "Description"), ("benefits", "Benefits"), ("drawbacks", "Drawbacks"),
                ("timeline_impact", "Timeline impact"), ("capacity_impact", "Capacity impact"),
                ("stakeholder_impact", "Stakeholder impact"), ("other_projects_impact", "Other projects"),
                ("risk", "Risk"))))
    imp = spec.get("impacts", {})
    new_c, gone_c = conflict_diff(before["conflicts"], after["conflicts"])
    body = f"""# {pid}: {spec['title']}

> **Status: PROPOSED — waiting for Wirat's review.** Nothing in backlog, capacity or journey changes until
> Wirat approves (`wf.py approve-change {pid} --by wirat`) and `wf.py apply-change {pid}` runs.

## Reason
{spec['reason']}

## Current state → Proposed state
| Project | Task | Change | Current | Proposed |
|---|---|---|---|---|
{rows}

## Impact
- **Timeline:** {imp.get('timeline', 'Unknown / Needs confirmation')}
- **Capacity:** {imp.get('capacity', 'Unknown / Needs confirmation')}
- **Stakeholders:** {imp.get('stakeholders', 'Unknown / Needs confirmation')}
- **Other projects:** {imp.get('other_projects', 'Unknown / Needs confirmation')}

### Simulated capacity (wf.py)
| | Before | After |
|---|---|---|
| Committed hours this week | {before['committed_hours_this_week']} | {after['committed_hours_this_week']} |
| Available hours this week | {before['available_hours_this_week']} | {after['available_hours_this_week']} |
| Conflicts | {len(before['conflicts'])} | {len(after['conflicts'])} |

**New conflicts after change:**
{conflict_lines(new_c)}

**Conflicts resolved by change:**
{conflict_lines(gone_c)}

## Alternatives (most → least recommended)
{chr(10).join(alts)}

## Machine-readable changes (applied only after approval)
```json
{json.dumps({"changes": spec["changes"]}, ensure_ascii=False, indent=2)}
```

## Review log
- {now_iso()} — proposed by {fm['requested_by']}
"""
    path = stamped(portfolio() / "plan-changes", f"{pid}_{slugify(spec['title'])}.md")
    W.new_text(path, dump_fm(fm) + "\n" + body)
    print(path)


def _pcp_new_revision(pcp_id, **fm_updates):
    files = pcp_files(pcp_id)
    latest = files[-1]
    fm, body, _ = read_pcp(latest)
    fm.update(fm_updates)
    fm["revision"] = int(fm.get("revision", 1)) + 1
    fm["supersedes"] = latest.name
    fm["updated_at"] = now_iso()
    log_line = fm_updates.pop("_log", None)
    fm.pop("_log", None)
    if log_line:
        body = body.rstrip() + f"\n- {now_iso()} — {log_line}\n"
    dst = stamped(latest.parent, f"{pcp_id}_r{fm['revision']}.md")
    W.new_text(dst, dump_fm(fm) + "\n" + body)
    return dst


def cmd_approve_change(a):
    if a.by != OWNER:
        die(f"only {OWNER} can approve plan changes", code=3)
    fm, _, _ = read_pcp(pcp_files(a.id)[-1])
    if fm.get("status") != "proposed":
        die(f"{a.id} is '{fm.get('status')}', not 'proposed'")
    alt = f" (alternative {a.alternative})" if a.alternative else ""
    print(_pcp_new_revision(a.id, status="approved", approved_by=a.by, approved_at=now_iso(),
                            approved_alternative=a.alternative or 1,
                            _log=f"APPROVED by {a.by}{alt}. {a.note or ''}"))


def cmd_reject_change(a):
    print(_pcp_new_revision(a.id, status="rejected", _log=f"REJECTED by {a.by}. {a.note or ''}"))


def cmd_apply_change(a):
    files = pcp_files(a.id)
    fm, body, block = read_pcp(files[-1])
    if fm.get("status") != "approved" or fm.get("approved_by") != OWNER or not fm.get("approved_at"):
        die(f"{a.id} is not approved by {OWNER} (status={fm.get('status')}). Plan unchanged.", code=3)
    if fm.get("applied_at"):
        die(f"{a.id} was already applied at {fm['applied_at']}")
    changes = block["changes"]
    reason = (re.search(r"## Reason\n(.*?)\n\n##", body, re.S) or [None, ""])[1].strip()
    alt_titles = re.findall(r"^### \d+\. (.+?)(?:  ⭐ Recommended)?$", body, re.M)
    # stale check: the plan must still look like it did when proposed
    for c in changes:
        if c.get("op", "set") in ("set", "activate"):
            _, _, t = find_task(c["task"])
            if t.get(c["field"]) != c.get("from"):
                die(f"stale proposal: {c['task']}.{c['field']} is now {t.get(c['field'])!r}, proposal expected "
                    f"{c.get('from')!r}. Create a new proposal.", code=4)
    touched = {}
    for c in changes:
        slug = c.get("project") if c.get("op") == "add_task" else find_task(c["task"])[0]
        bl = touched.get(slug) or load_backlog(slug)
        touched[slug] = bl
        bl["tasks"] = apply_changes_to_tasks(bl["tasks"], [c])
    for slug, bl in touched.items():
        bl["updated_at"] = now_iso()
        W.json(data_path(slug, "backlog.json"), bl)
    for slug in touched:
        mine = [c for c in changes if (c.get("project") if c.get("op") == "add_task" else find_task(c["task"])[0]) == slug]
        task_ids = list(dict.fromkeys(c["task"] if isinstance(c.get("task"), str) else c["task"]["id"] for c in mine))
        tasks_now = [t for t in touched[slug]["tasks"] if t["id"] in task_ids]
        links = {"tasks": task_ids, "plan_change": a.id,
                 "modules": sorted({t.get("module") for t in tasks_now if t.get("module")}),
                 "stakeholders": sorted({s for t in tasks_now for s in t.get("stakeholders", []) if s != OWNER})}
        did, dpath = create_decision(slug, f"Plan change {a.id}: {fm.get('title')}",
                                     f"Plan Change Proposal {a.id} reviewed and approved by Wirat. Reason: {reason or 'see proposal'}",
                                     f"Apply alternative {fm.get('approved_alternative', 1)}: "
                                     + "; ".join(f"{c.get('task') if isinstance(c.get('task'), str) else c['task']['id']} "
                                                 f"{c.get('op', 'set')} {c.get('field', '')} {c.get('from', '')} → {_change_cell(c)}" for c in mine),
                                     links, alternatives=alt_titles)
        append_journey(slug, {"type": "plan-change", "title": f"{a.id} applied: {fm.get('title')}",
                              "summary": f"Approved by {fm.get('approved_by')} at {fm.get('approved_at')}",
                              "tasks": task_ids, "decision": did, "plan_change": a.id})
        if not W.dry:
            W.json(data_path(slug, "progress.json"), compute_progress(slug))
    _pcp_new_revision(a.id, applied_at=now_iso(), _log="APPLIED to backlog, journey, progress, capacity")
    if not W.dry:
        cfg = load_capacity_cfg()
        cfg.update(compute_capacity())
        W.json(portfolio() / "capacity.json", cfg)
        bundle(quiet=True)
    log_skill("plan-change-control", ",".join(touched), a.id)
    print(f"applied {a.id} to {', '.join(touched)}")


# ---- execution plan guard

def cmd_check_exec_plan(a):
    text = Path(a.path).read_text(encoding="utf-8")
    problems = []
    for h in ("Task list", "Dependency graph", "File ownership", "Contract", "Test responsibility", "Merge order"):
        if not re.search(rf"^#+\s*.*{h}", text, re.M | re.I):
            problems.append(f"missing section: {h}")
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        problems.append("missing ```json ownership block")
        plan = {}
    else:
        plan = json.loads(m.group(1))
    agents = plan.get("agents", [])
    owner_of = {}
    for ag in agents:
        if ag.get("role") == "coordinator" and ag.get("files"):
            problems.append(f"coordinator '{ag['name']}' must not own/edit source files")
        if ag.get("files") and ag.get("role") != "coordinator" and not ag.get("worktree"):
            problems.append(f"agent '{ag['name']}' edits files but has no worktree")
        for f in ag.get("files", []):
            key = f.replace("\\", "/").lower()
            if key in owner_of:
                problems.append(f"file '{f}' assigned to both '{owner_of[key]}' and '{ag['name']}'")
            owner_of[key] = ag["name"]
        for k in ("tasks", "tests"):
            if ag.get("role") != "coordinator" and not ag.get(k):
                problems.append(f"agent '{ag.get('name')}' has no {k}")
    workers = [ag for ag in agents if ag.get("role") != "coordinator"]
    if len(workers) > 1 and not plan.get("contracts"):
        problems.append("parallel workers need shared contracts (API/schema/types) defined first")
    if len(workers) > 1 and not plan.get("merge_order"):
        problems.append("merge_order missing")
    if workers and not any(ag.get("role") == "coordinator" for ag in agents) and len(workers) > 1:
        problems.append("multi-agent plan needs a coordinator")
    if problems:
        print("EXECUTION PLAN: FAIL\n- " + "\n- ".join(problems))
        sys.exit(1)
    print(f"EXECUTION PLAN: PASS ({len(workers)} worker(s), {len(owner_of)} owned file(s))")


# ---- UAT excel revisions

UAT_COLUMNS = ["UAT ID", "Module", "Scenario", "Preconditions", "Steps", "Expected Result",
               "Actual Result", "Status", "Tester", "Remarks", "Task IDs", "Stakeholders", "Test Data / Env"]


def cmd_uat_revise(a):
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError:
        die("openpyxl is required: pip install openpyxl")
    folder = pws(a.project) / "00-Project" / "uat"
    latest_p = folder / "latest.json"
    src, prev_rev = latest_uat_workbook(folder)
    rows, dropped = read_uat_rows(openpyxl, src) if src else ([], [])
    spec = load_json(a.input, {}) or {}
    by_id = {r["UAT ID"]: r for r in rows}
    used = [int(m.group(1)) for r in rows if (m := re.match(r"UAT-(\d+)$", str(r["UAT ID"])))]
    for s in spec.get("add", []):
        uid = s.get("uat_id") or next_id("UAT", floor=max(used, default=0))
        if uid in by_id:
            die(f"{uid} already exists; use 'update'")
        r = {"UAT ID": uid, "Module": s.get("module"), "Scenario": s.get("scenario"),
             "Preconditions": s.get("preconditions"), "Steps": "\n".join(s.get("steps", [])) if isinstance(s.get("steps"), list) else s.get("steps"),
             "Expected Result": s.get("expected"), "Actual Result": s.get("actual", ""), "Status": s.get("status", "Not Run"),
             "Tester": s.get("tester"), "Remarks": s.get("remarks", ""), "Task IDs": ", ".join(s.get("tasks", [])),
             "Stakeholders": ", ".join(s.get("stakeholders", [])), "Test Data / Env": s.get("test_data", "")}
        rows.append(r)
        by_id[uid] = r
    for u in spec.get("update", []):
        r = by_id.get(u["uat_id"])
        if not r:
            die(f"{u['uat_id']} not in latest UAT revision")
        for k, col in (("actual", "Actual Result"), ("status", "Status"), ("tester", "Tester"), ("remarks", "Remarks")):
            if k in u:
                r[col] = u[k]
    bad = [r["UAT ID"] for r in rows if r.get("Status") not in ("Pass", "Fail", "Blocked", "Not Run")]
    if bad:
        die(f"Status must be Pass/Fail/Blocked/Not Run: {bad}")
    rev = prev_rev + 1
    supersedes = src.name if src else None
    name = f"UAT_{a.project}_r{rev:02d}.xlsx"
    dst = stamped(folder, name)
    summary = {s: sum(1 for r in rows if r.get("Status") == s) for s in ("Pass", "Fail", "Blocked", "Not Run")}
    summary["total"] = len(rows)
    W._plan("create", dst)
    if not W.dry:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "UAT"
        ws.append(UAT_COLUMNS)
        for r in rows:
            ws.append([r.get(c) for c in UAT_COLUMNS])
        fill = PatternFill("solid", fgColor="1F4E78")
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = fill
        widths = [10, 14, 34, 28, 40, 34, 28, 10, 12, 24, 14, 16, 24]
        for i, w in enumerate(widths):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        dv = DataValidation(type="list", formula1='"Pass,Fail,Blocked,Not Run"', allow_blank=False)
        ws.add_data_validation(dv)
        dv.add(f"H2:H{max(2, len(rows) + 1)}")
        ws.freeze_panes = "A2"
        info = wb.create_sheet("Revision")
        for k, v in (("Project", a.project), ("Revision", rev), ("Created", now_iso()),
                     ("Supersedes", supersedes or "(none)"), ("Note", spec.get("note", "")),
                     ("Pass", summary["Pass"]), ("Fail", summary["Fail"]), ("Blocked", summary["Blocked"]),
                     ("Not Run", summary["Not Run"])):
            info.append([k, v])
        dst.parent.mkdir(parents=True, exist_ok=True)
        wb.save(dst)
    # latest.json is the pointer itself (spec: "maintain latest.json pointing to the current revision")
    W.json(latest_p, {"file": dst.name, "revision": rev, "supersedes": supersedes,
                      "updated_at": now_iso(), "summary": summary}, history=False)
    if not W.dry:
        W.json(data_path(a.project, "progress.json"), compute_progress(a.project))
        bundle(quiet=True)
    log_skill("uat-manager", a.project, dst.name)
    print(json.dumps({"file": str(dst), "revision": rev, "supersedes": supersedes, "copied_rows": len(rows) - len(spec.get("add", [])),
                      "dropped_columns": dropped, "summary": summary}, ensure_ascii=False))


def _uat_stamp_key(p):
    """Sort key from a leading timestamp (YYYYMMDD-HHMM or YYYYMMDD-HHMMSS); falls back to mtime."""
    m = re.match(r"^(\d{8})-(\d{4,6})", p.name)
    return (m.group(1) + m.group(2).ljust(6, "0"), p.stat().st_mtime) if m else ("0", p.stat().st_mtime)


def latest_uat_workbook(folder):
    """Current UAT workbook and its revision number: latest.json if valid, otherwise the newest .xlsx."""
    latest = load_json(folder / "latest.json", None)
    if latest and (folder / latest.get("file", "")).is_file():
        return folder / latest["file"], int(latest.get("revision", 1))
    books = [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")] if folder.exists() else []
    if not books:
        return None, 0
    src = max(books, key=_uat_stamp_key)
    m = re.search(r"(?:^|[_\-])r(?:ev)?(\d+)", src.stem, re.I)
    return src, int(m.group(1)) if m else 1


def _norm(h):
    return re.sub(r"[^a-z]", "", str(h or "").lower())


def read_uat_rows(openpyxl, src):
    """Rows of a UAT workbook keyed by UAT_COLUMNS (header match ignores case, spaces and punctuation)."""
    wb = openpyxl.load_workbook(src, read_only=True)
    ws = wb["UAT"] if "UAT" in wb.sheetnames else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    hdr = list(next(it, []) or [])
    want = {_norm(c): c for c in UAT_COLUMNS}
    want.update({"id": "UAT ID", "uatid": "UAT ID", "expected": "Expected Result", "actual": "Actual Result",
                 "taskids": "Task IDs", "tasks": "Task IDs", "testdata": "Test Data / Env"})
    colmap = {i: want[_norm(h)] for i, h in enumerate(hdr) if _norm(h) in want}
    missing = [c for c in ("UAT ID", "Scenario", "Status") if c not in colmap.values()]
    if missing:
        die(f"{src.name}: cannot read UAT rows, missing columns {missing} (found {hdr})")
    dropped = [h for i, h in enumerate(hdr) if i not in colmap and h]
    rows = []
    for r in it:
        if r and any(v not in (None, "") for v in r):
            row = {col: r[i] if i < len(r) else None for i, col in colmap.items()}
            row["Status"] = row.get("Status") or "Not Run"
            rows.append(row)
    wb.close()
    return rows, dropped


# ---- open questions, journey, decisions (so skills never hand-edit JSON or decision files)

def _csv(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def find_question(oq_id):
    for s in project_slugs():
        bl = load_backlog(s)
        for q in bl.get("open_questions", []):
            if q.get("id") == oq_id:
                return s, bl, q
    die(f"open question {oq_id} not found")


def cmd_add_question(a):
    if not a.owner or not a.target_meeting:
        die("every Open Question needs --owner and --target-meeting")
    bl = load_backlog(a.project)
    ids = {t["id"] for t in all_tasks()}
    tasks = _csv(a.tasks)
    unknown = [t for t in tasks if t not in ids]
    if unknown:
        die(f"unknown tasks {unknown}")
    qid = next_id("OQ")
    q = {"id": qid, "question": a.question, "owner": a.owner, "target_meeting": a.target_meeting, "status": "open",
         "linked_tasks": tasks, "raised_in": a.raised_in or "", "options_presented": [o.strip() for o in (a.options or "").split("|") if o.strip()],
         "created_at": now_iso()}
    bl.setdefault("open_questions", []).append(q)
    for t in bl.get("tasks", []):
        if t["id"] in tasks:
            t.setdefault("open_questions", []).append(qid)
    bl["updated_at"] = now_iso()
    W.json(data_path(a.project, "backlog.json"), bl)
    if not W.dry:
        W.json(data_path(a.project, "progress.json"), compute_progress(a.project))
        bundle(quiet=True)
    print(json.dumps(q, ensure_ascii=False))


def cmd_update_question(a):
    slug, bl, q = find_question(a.id)
    before = dict(q)
    for k in ("question", "owner", "target_meeting", "answer", "decision", "status"):
        v = getattr(a, k)
        if v is not None:
            q[k] = v
    if a.answer and a.status is None:
        q["status"] = "answered"
    if q.get("status") not in ("open", "answered", "dropped"):
        die("status must be open | answered | dropped")
    if not q.get("owner") or not q.get("target_meeting"):
        die("an Open Question must keep an owner and a target meeting")
    q["updated_at"] = now_iso()
    bl["updated_at"] = now_iso()
    W.json(data_path(slug, "backlog.json"), bl)
    if not W.dry:
        W.json(data_path(slug, "progress.json"), compute_progress(slug))
        bundle(quiet=True)
    print(json.dumps({"id": a.id, "project": slug, "before": before, "after": q}, ensure_ascii=False))


def _module_event(spec, date=None):
    module, _, rest = spec.partition("|")
    stage, _, change = rest.partition("|")
    ev = {"module": module.strip(), "stage": stage.strip(), "change": change.strip()}
    if date:
        ev["date"] = date
    return ev


def cmd_journey_add(a):
    pws(a.project)
    entry = {"date": a.date or today().isoformat(), "type": a.type, "title": a.title}
    for k, v in (("summary", a.summary), ("decision", a.decision), ("meeting", a.meeting),
                 ("plan_change", a.plan_change), ("ref", a.ref)):
        if v:
            entry[k] = v
    for k, v in (("modules", a.modules), ("tasks", a.tasks), ("stakeholders", a.stakeholders)):
        if _csv(v):
            entry[k] = _csv(v)
    events = [_module_event(m, entry["date"]) for m in a.module_event or []]
    for ev in events:
        ev.update({k: entry[k] for k in ("decision",) if k in entry})
    ev = journey_append(a.project, entry, events)  # ONE new event file + digest update, whatever its size
    if not W.dry:
        bundle(quiet=True)
    print(json.dumps(ev if W.dry else _short(ev), ensure_ascii=False))


def cmd_decision_new(a):
    links = {"meetings": _csv(a.meetings), "modules": _csv(a.modules), "tasks": _csv(a.tasks),
             "stakeholders": _csv(a.stakeholders), "uat": _csv(a.uat), "plan_change": a.plan_change or ""}
    did, path = create_decision(a.project, a.title, a.context, a.decision, links,
                                alternatives=[x.strip() for x in (a.alternatives or "").split("|") if x.strip()],
                                decided_by=a.decided_by or OWNER, supersedes=a.supersedes or "",
                                consequences=a.consequences or "")
    if not a.no_journey:  # project-memory: every decision also lands on the journey (timeline + modules)
        rel = (path.relative_to(pws(a.project)).as_posix() if not W.dry else f"00-Project/decisions/{path.name}")
        entry = {"type": "decision", "title": f"{did} {a.title}"[:MAX_TITLE], "decision": did, "ref": rel,
                 "modules": links["modules"], "tasks": links["tasks"], "stakeholders": links["stakeholders"]}
        if links["meetings"]:
            entry["meeting"] = links["meetings"][0]
        mevs = [{"module": m, "stage": "decision", "change": a.title[:MAX_CHANGE], "decision": did,
                 **({"task": links["tasks"][0]} if links["tasks"] else {})} for m in links["modules"]]
        journey_append(a.project, entry, mevs)
    if not W.dry:
        bundle(quiet=True)
    print(json.dumps({"id": did, "file": str(path)}, ensure_ascii=False))


# ---- compact, capped reads: the only way skills look at history / lists (keeps context small)

OUT_CAP = 6000


def emit(lines, header=None, cap=None):
    """Print lines until the character budget is used, then say how much was left out."""
    cap = cap or OUT_CAP
    out, used = [], 0
    for i, ln in enumerate(lines):
        if used + len(ln) + 1 > cap:
            out.append(f"... {len(lines) - i} more line(s) not shown (output capped at {cap} chars) - narrow the filters")
            break
        out.append(ln)
        used += len(ln) + 1
    if header:
        print(header)
    print("\n".join(out))


def _ev_line(e, full=False):
    bits = [e.get("date", ""), e.get("id", ""), f"[{e.get('type', '')}]", e.get("title", "")]
    for k in ("modules", "tasks"):
        if e.get(k):
            bits.append(f"{k}={','.join(e[k])}")
    for k in ("decision", "meeting", "plan_change", "ref"):
        if e.get(k):
            bits.append(f"{k}={e[k]}")
    line = " ".join(b for b in bits if b)
    if full and e.get("summary"):
        line += "\n    " + e["summary"]
    return line


def legacy_events(j):
    evs = [dict(e, id=e.get("id", "legacy"), timeline=True, module_events=[]) for e in j.get("timeline", [])]
    evs += [{"id": "legacy", "date": x.get("date", ""), "type": "module-evolution", "title": m["module"], "timeline": False,
             "module_events": [dict(x, module=m["module"])]} for m in j.get("modules", []) for x in m.get("evolution", [])]
    return sorted(evs, key=lambda e: e.get("date", ""))


def cmd_journey(a):
    pws(a.project)
    if a.digest:
        print(json.dumps(journey_digest_of(a.project), ensure_ascii=False, separators=(",", ":"))[:a.max_chars])
        return
    j = load_feed(data_path(a.project, "journey.json"), None)
    if not is_v2(j) and (j or {}).get("timeline") is not None:
        print("# NOTE: this journey is still in the old single-file format; run `wf.py journey-compact` once", file=sys.stderr)
        events = legacy_events(j)
    else:
        events = journey_events(a.project)
    total = len(events)
    if a.module:
        rows = []
        for e in events:
            for me in e.get("module_events", []):
                if me["module"] == a.module:
                    rows.append((me.get("date", e["date"]), e["id"], me))
        rows = [r for r in rows if (not a.since or r[0] >= a.since) and (not a.until or r[0] <= a.until)]
        shown = rows[-a.limit:]
        lines = [f"{d_} {i} {me.get('stage', '')}: {me.get('change', '')}"
                 + "".join(f" {k}={me[k]}" for k in ("task", "decision") if me.get(k)) for d_, i, me in shown]
        emit(lines, f"# module {a.module}: showing {len(shown)} of {len(rows)} evolution step(s) (project has {total} events)", a.max_chars)
        return
    ev = [e for e in events if e.get("timeline", True)]

    def keep(e):
        return ((not a.since or e["date"] >= a.since) and (not a.until or e["date"] <= a.until)
                and (not a.type or e.get("type") == a.type)
                and (not a.task or a.task in e.get("tasks", []))
                and (not a.decision or e.get("decision") == a.decision)
                and (not a.stakeholder or a.stakeholder in e.get("stakeholders", []))
                and (not a.search or a.search.lower() in (e.get("title", "") + " " + e.get("summary", "")).lower()))

    rows = [e for e in ev if keep(e)]
    shown = rows[-a.limit:]
    emit([_ev_line(e, a.full) for e in shown],
         f"# journey {a.project}: showing {len(shown)} of {len(rows)} matching timeline event(s); project total {len(ev)}"
         + ("" if len(rows) <= len(shown) else " - older ones hidden: use --since/--until/--type/--search/--module"), a.max_chars)


def cmd_journey_compact(a):
    slugs = project_slugs() if a.all or not a.project else [a.project]
    for s in slugs:
        j = load_feed(data_path(s, "journey.json"), None)
        if is_v2(j) and not a.rebuild:
            print(f"{s}: already v2 ({j.get('total_events', 0)} events)")
            continue
        if is_v2(j) and a.rebuild:  # rebuild the digest from the event files (self-healing)
            if not W.dry:
                W.json(data_path(s, "journey.json"), build_digest(s, journey_events(s)))
            print(f"{s}: digest rebuilt")
            continue
        ensure_journey_v2(s)
        print(f"{s}: migrated to v2")
    if not W.dry:
        bundle(quiet=True)


def _task_line(t):
    return " | ".join([t["id"], t.get("project", ""), t.get("module", ""), t.get("owner", ""), t.get("priority", ""),
                       f"{t.get('status', '')}/{t.get('health', '')}", f"due {t.get('due') or '?'}",
                       f"{t.get('estimate_days', '?')}d", (t.get("title") or "")[:70]])


def cmd_tasks(a):
    cap, ref = load_capacity_cfg(), today()
    risk_ids = capacity_risk_ids(compute_capacity(ref=ref, cap=cap))
    rows = []
    for t in all_tasks():
        t = with_health(t, cap, ref, risk_ids)
        if a.project and t["project"] != a.project:
            continue
        if a.owner and t.get("owner") != a.owner:
            continue
        if a.stakeholder and a.stakeholder not in (t.get("stakeholders") or []) + (t.get("blocked_by") or []) + [t.get("owner")]:
            continue
        if a.status == "open" and t.get("status") in DONE:
            continue
        if a.status not in (None, "open", "all") and t.get("status") != a.status:
            continue
        if a.health and t["health"] != a.health:
            continue
        if a.due_before and not (t.get("due") and t["due"] <= a.due_before):
            continue
        rows.append(t)
    order = {"delayed": 0, "blocked": 1, "at-risk": 2, "waiting-user": 3, "waiting-manager": 4, "unknown": 5, "on-track": 6}
    rows.sort(key=lambda t: (order.get(t["health"], 9), t.get("due") or "9999", t.get("priority", "P9")))
    shown = rows[:a.limit]
    emit([_task_line(t) for t in shown], f"# tasks: showing {len(shown)} of {len(rows)} "
         "(id | project | module | owner | pri | status/health | due | est | title)", a.max_chars)


def cmd_questions(a):
    rows = []
    for q in all_open_questions():
        if a.project and q["project"] != a.project:
            continue
        if a.open and q.get("status") != "open":
            continue
        rows.append(q)
    rows.sort(key=lambda q: (q.get("target_meeting") or "9999", q.get("id", "")))
    shown = rows[:a.limit]
    lines = [" | ".join([q["id"], q["project"], q.get("status", ""), q.get("owner") or "?", q.get("target_meeting") or "?",
                         ",".join(q.get("linked_tasks") or []) or "-", (q.get("question") or "")[:80]]) for q in shown]
    emit(lines, f"# open questions: showing {len(shown)} of {len(rows)} "
         "(id | project | status | owner | target meeting | tasks | question)", a.max_chars)


def cmd_artifacts(a):
    kinds = {"decisions": "00-Project/decisions", "meetings": "00-Project/meetings", "releases": "00-Project/releases",
             "stakeholders": "00-Project/stakeholders", "backlog": "00-Project/backlog"}
    sel = kinds if a.kind in (None, "all") else {a.kind: kinds[a.kind]}
    lines = []
    for kind, rel in sel.items():
        files = sorted(current_md_files(pws(a.project) / rel), key=ts_key, reverse=True)[:a.n]
        for f in files:
            fm, body = parse_fm(f.read_text(encoding="utf-8"))
            m = re.search(r"^#\s+(.+)$", body, re.M)
            title = fm.get("title") or (m.group(1) if m else f.stem)
            lines.append(f"{kind[:-1]} | {fm.get('id', '')} | {fm.get('date', '')} | {fm.get('status', '')} | "
                         f"rev {fm.get('revision', 1)} | {str(title)[:80]} | {rel}/{f.name}")
    emit(lines, f"# current artifacts of {a.project} (newest first; superseded revisions are not listed)", a.max_chars)


# ---- where things live on THIS computer: projects map / add / remove, setup, kit, view upgrade
#
# Portable data (Portfolio/, ProjectWorkspace/) never contains an absolute path. Everything that differs per
# computer lives in ~/.claude/wirat-workflow/local.json: the workspace root, each project's repo folder and,
# optionally, a ProjectWorkspace kept somewhere else.

def _p(path):
    return str(path).replace("\\", "/") if path else None


def _project_rows():
    reg = {p["slug"]: p for p in registry().get("projects", [])}
    slugs = sorted(set(reg) | set(project_slugs(include_archived=True)) | set(local_cfg().get("projects") or {}))
    rows = []
    for s in slugs:
        r, wsd, repo = reg.get(s, {}), ws_dir(s), repo_of(s)
        info = git_info(repo) if repo and repo.is_dir() else {}
        rows.append({"slug": s, "name": r.get("name", s), "status": r.get("status", "unregistered"), "registered": s in reg,
                     "workspace": _p(wsd), "workspace_exists": wsd.is_dir(),
                     "workspace_location": "custom" if local_project(s).get("workspace") else "standard",
                     "repo": _p(repo), "repo_exists": bool(repo and repo.is_dir()), "branch": info.get("branch"),
                     "remote": info.get("remote"), "registry_remote": r.get("remote"), "repo_name": r.get("repo_name")})
    return rows


def _known(slug):
    return slug in {p["slug"] for p in registry().get("projects", [])} or ws_dir(slug).is_dir()


def pc_list(a):
    rows = _project_rows()
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    print(f"# machine {platform.node()} | workspace root {_p(workspace())} | local config {_p(LOCAL_CFG)}")
    for r in rows:
        ws = r["workspace"] + (" (custom)" if r["workspace_location"] == "custom" else "")
        ws += "" if r["workspace_exists"] else "  !! MISSING on this machine"
        repo = "NOT MAPPED" if not r["repo"] else r["repo"] + ("" if r["repo_exists"] else "  !! MISSING")
        extra = f" branch={r['branch']}" if r["branch"] else ""
        print(f"{r['slug']} [{r['status']}] {r['name']}\n    workspace: {ws}\n    repo:      {repo}{extra}")


def pc_map(a):
    s = a.slug
    if not _known(s):
        die(f"unknown project '{s}'. Known: {', '.join(r['slug'] for r in _project_rows()) or 'none'}")
    if not a.repo and not a.workspace:
        die("give --repo <source folder> and/or --workspace <ProjectWorkspace folder>")
    if a.repo:
        p = _xp(a.repo)
        if not p.is_dir() and not a.force:
            die(f"{p} does not exist on this machine (use --force to map it anyway)")
        info = git_info(p) if p.is_dir() else {}
        set_local_project(s, repo=p)
        ent = next((x for x in registry()["projects"] if x["slug"] == s), {})
        if ent.get("remote") and info.get("remote") and norm_remote(ent["remote"]) != norm_remote(info["remote"]):
            print(f"WARN: {p} has remote {info['remote']} but the project registry says {ent['remote']} - mapped anyway")
        registry_upsert(s, **{k: v for k, v in (("repo_name", p.name), ("remote", info.get("remote"))) if not ent.get(k)})
        print(f"{s}: repo -> {_p(p)}" + (f" ({info.get('branch')})" if info.get("branch") else ""))
    if a.workspace:
        p = _xp(a.workspace)
        if not (p / "10-Data").is_dir():
            die(f"{p} is not a ProjectWorkspace (no 10-Data folder)")
        std = workspace() / "Projects" / s / "ProjectWorkspace"
        same = p.resolve() == std.resolve() if std.exists() else False
        set_local_project(s, workspace=None if same else p)
        print(f"{s}: workspace -> {_p(p)}" + (" (standard location, no override needed)" if same else " (custom)"))
    if not W.dry:
        bundle(quiet=True)


def pc_unmap(a):
    s = a.slug
    both = not a.repo and not a.workspace
    set_local_project(s, **({"repo": None} if a.repo or both else {}), **({"workspace": None} if a.workspace or both else {}))
    print(f"{s}: forgot {'repo and workspace' if both else 'repo' if a.repo else 'workspace'} mapping on this machine "
          f"(nothing deleted on disk, nothing changed for other computers)")
    if not W.dry:
        bundle(quiet=True)


def pc_add(a):
    p = _xp(a.workspace)
    bl = load_feed(p / "10-Data" / "backlog.json", None) if (p / "10-Data").is_dir() else None
    if bl is None:
        die(f"{p} is not a ProjectWorkspace with a backlog (expected {p / '10-Data' / 'backlog.json'}). "
            f"For a brand-new project use: wf.py new-workspace {a.slug} --at <folder> --repo <source folder>")
    name = a.name or bl.get("project_name") or a.slug
    std = workspace() / "Projects" / a.slug / "ProjectWorkspace"
    if not (std.exists() and p.resolve() == std.resolve()):
        set_local_project(a.slug, workspace=p)
    registry_upsert(a.slug, name=name)
    if a.repo:
        pc_map(argparse.Namespace(slug=a.slug, repo=a.repo, workspace=None, force=a.force))
    elif not W.dry:
        bundle(quiet=True)
    print(f"{a.slug}: registered ({name}); workspace {_p(p)}" + ("" if a.repo else "; repo not mapped yet -> wf.py projects map"))


def pc_remove(a):
    s = a.slug
    if not _known(s):
        die(f"unknown project '{s}'")
    open_mine = 0
    if ws_dir(s).is_dir():
        open_mine = sum(1 for t in load_backlog(s).get("tasks", []) if t.get("owner") == OWNER and t.get("status") not in DONE)
    if open_mine and not a.yes:
        die(f"{s} still has {open_mine} open task(s) owned by {OWNER}. Removing hides the project from every progress / capacity "
            f"calculation on all computers. Re-run with --yes to confirm (files are kept; wf.py projects restore {s} undoes it).", code=3)
    registry_upsert(s, status="archived", archived_at=now_iso())
    set_local_project(s, repo=None, workspace=None)
    print(f"{s}: archived in the project registry and forgotten on this machine. No file was deleted "
          f"(workspace folder is untouched). Undo: wf.py projects restore {s}")
    if not W.dry:
        bundle(quiet=True)


def pc_restore(a):
    reg = registry()
    ent = next((x for x in reg["projects"] if x["slug"] == a.slug), None)
    if not ent:
        die(f"'{a.slug}' is not in the project registry")
    ent["status"] = "active"
    ent.pop("archived_at", None)
    W.json(portfolio() / "projects.json", reg)
    print(f"{a.slug}: active again" + ("" if ws_dir(a.slug).is_dir() else
          f" - but its workspace is not on this machine; map it: wf.py projects add {a.slug} --workspace <folder>"))
    if not W.dry:
        bundle(quiet=True)


def pc_set_workspace(a):
    p = _xp(a.path)
    if not p.is_dir():
        die(f"{p} does not exist")
    if not ((p / "Portfolio").is_dir() or (p / "Projects").is_dir()) and not a.force:
        die(f"{p} has neither Portfolio/ nor Projects/ - wrong folder? (--force to use it anyway; wf.py setup --init creates a new workspace)")
    cfg = local_cfg()
    cfg["workspace"] = _p(p)
    save_local_cfg(cfg)
    print(f"workspace root on this machine -> {_p(p)}")


def pc_check(a):
    rows = {r["slug"]: r for r in _project_rows()}
    bad = warn = 0
    lines = []
    root = workspace()
    lines.append(("OK" if root.is_dir() else "ERR", f"workspace root {_p(root)}" + ("" if root.is_dir() else " does not exist: wf.py projects set-workspace <folder>")))
    bad += not root.is_dir()
    for s, r in rows.items():
        if r["status"] == "archived":
            continue
        if not r["registered"]:
            lines.append(("WARN", f"{s}: workspace exists but the project is not in Portfolio/projects.json (wf.py projects add {s} --workspace {r['workspace']})"))
            warn += 1
        if not r["workspace_exists"]:
            lines.append(("ERR", f"{s}: ProjectWorkspace not found on this machine ({r['workspace']}). Sync the workspace or: wf.py projects add {s} --workspace <folder>"))
            bad += 1
            continue
        if not r["repo"]:
            hint = f" (registry: {r['repo_name'] or '?'}, {r['registry_remote'] or 'no remote'})"
            lines.append(("WARN", f"{s}: source folder not mapped on this machine{hint} -> wf.py projects map {s} --repo <folder> or projects scan <parent folder>"))
            warn += 1
        elif not r["repo_exists"]:
            lines.append(("ERR", f"{s}: mapped repo folder is missing: {r['repo']} -> wf.py projects map {s} --repo <new folder>"))
            bad += 1
        else:
            if r["registry_remote"] and r["remote"] and norm_remote(r["registry_remote"]) != norm_remote(r["remote"]):
                lines.append(("WARN", f"{s}: repo remote {r['remote']} differs from registry {r['registry_remote']}"))
                warn += 1
            else:
                lines.append(("OK", f"{s}: workspace {r['workspace_location']}, repo {r['repo']}" + (f" [{r['branch']}]" if r['branch'] else "")))
    for ln in lines:
        print(f"{ln[0]:4} {ln[1]}")
    print(f"# {bad} error(s), {warn} warning(s)")
    if bad:
        sys.exit(1)


def pc_scan(a):
    reg = [p for p in registry().get("projects", []) if p.get("status") != "archived"]
    by_remote = {norm_remote(p["remote"]): p["slug"] for p in reg if p.get("remote")}
    by_name = {}
    for p in reg:
        for n in (p["slug"], p.get("repo_name")):
            if n:
                by_name.setdefault(n.lower(), []).append(p["slug"])
    found = []
    for base in a.folders:
        base = _xp(base)
        if not base.is_dir():
            die(f"{base} does not exist")
        stack = [(base, 0)]
        while stack:
            cur, depth = stack.pop()
            if (cur / ".git").exists():
                found.append(cur)
                continue
            if depth >= a.depth:
                continue
            try:
                stack += [(c, depth + 1) for c in sorted(cur.iterdir()) if c.is_dir() and c.name not in ("node_modules", ".git", "__pycache__")]
            except OSError:
                pass
    hits = []
    for repo in found:
        info = git_info(repo)
        slug = by_remote.get(norm_remote(info.get("remote", ""))) if info.get("remote") else None
        how = "remote"
        if not slug:
            cands = [s for s in by_name.get(repo.name.lower(), [])]
            slug, how = (cands[0], "folder name") if len(cands) == 1 else (None, "")
        if slug:
            hits.append((slug, repo, how))
    seen = {}
    for slug, repo, how in hits:
        seen.setdefault(slug, []).append((repo, how))
    for slug, cands in sorted(seen.items()):
        mapped = repo_of(slug)
        for repo, how in cands:
            tag = "already mapped" if mapped and mapped.resolve() == repo.resolve() else "mapped elsewhere" if mapped else "unmapped"
            print(f"{slug}: {_p(repo)} (matched by {how}) - {tag}")
        if len(cands) > 1:
            print(f"    !! {len(cands)} candidates for {slug}: choose one with wf.py projects map {slug} --repo <folder>")
        elif not repo_of(slug) and a.apply:
            pc_map(argparse.Namespace(slug=slug, repo=str(cands[0][0]), workspace=None, force=False))
    unmatched = [s["slug"] for s in reg if s["slug"] not in seen and not repo_of(s["slug"])]
    if unmatched:
        print(f"no repo found for: {', '.join(unmatched)} (map by hand: wf.py projects map <slug> --repo <folder>)")
    if hits and not a.apply:
        print("# nothing changed; add --apply to map the unambiguous, unmapped matches")


def pc_which(a):
    here = _xp(a.path or os.getcwd()).resolve()
    for s in project_slugs(include_archived=True):
        r = repo_of(s)
        if r and r.is_dir():
            rr = r.resolve()
            if here == rr or rr in here.parents:
                print(s)
                return
    print("not inside any mapped project folder (wf.py projects list)", file=sys.stderr)
    sys.exit(1)


def pc_migrate(a):
    """Old data kept absolute repo paths inside portable files. Move them to this machine's local config."""
    reg = registry()
    changed = False
    for ent in reg["projects"]:
        rp = ent.pop("repo_path", None)
        if rp is None:
            continue
        changed = True
        s = ent["slug"]
        if rp and not repo_of(s) and _xp(rp).is_dir():
            info = git_info(_xp(rp))
            set_local_project(s, repo=rp)
            ent.setdefault("repo_name", _xp(rp).name)
            if info.get("remote"):
                ent.setdefault("remote", info["remote"])
            print(f"{s}: repo path imported into this machine's local config")
        elif rp:
            print(f"{s}: old repo path {rp} not found on this machine - map it: wf.py projects map {s} --repo <folder>")
    if changed:
        W.json(portfolio() / "projects.json", reg)
    for s in project_slugs(include_archived=True):
        bl = load_backlog(s)
        if "repo_path" not in bl:
            continue
        rp = bl.pop("repo_path")
        if rp and not repo_of(s) and _xp(rp).is_dir():
            set_local_project(s, repo=rp)
            print(f"{s}: repo path imported from backlog")
        bl["updated_at"] = now_iso()
        W.json(data_path(s, "backlog.json"), bl)
        changed = True
    print("migrated" if changed else "nothing to migrate")
    if changed and not W.dry:
        bundle(quiet=True)


def cmd_projects(a):
    {"list": pc_list, "map": pc_map, "unmap": pc_unmap, "add": pc_add, "remove": pc_remove, "restore": pc_restore,
     "set-workspace": pc_set_workspace, "check": pc_check, "scan": pc_scan, "which": pc_which, "migrate": pc_migrate}[a.pcmd](a)


def cmd_setup(a):
    """First run on a computer (or after moving folders): point this machine at the shared workspace."""
    ws = _xp(a.workspace)
    if not ws.exists():
        if not a.init:
            die(f"{ws} does not exist. If the workspace is synced (Obsidian Sync / OneDrive / git) wait for the sync; "
                f"to start a brand-new workspace there: wf.py setup --workspace {a.workspace} --init")
    elif not (ws / "Portfolio").is_dir() and not a.init:
        die(f"{ws} has no Portfolio/ folder - is it the right folder? (--init creates a new workspace there)")
    cfg = local_cfg()
    cfg["workspace"] = _p(ws)
    save_local_cfg(cfg)
    os.environ["WF_WORKSPACE"] = str(ws)  # the rest of this run uses it even in --dry-run
    if a.init:
        port = ws / "Portfolio"
        if not (port / "capacity.json").exists():
            W.json(port / "capacity.json", {"working_hours_per_day": 8, "focus_factor": 0.75, "working_weekdays": [0, 1, 2, 3, 4],
                                            "non_working_dates": [], "leave_hours_this_week": 0})
        for name, obj in (("delivery-metrics.json", {"records": []}), ("projects.json", {"projects": []})):
            if not (port / name).exists():
                W.json(port / name, obj)
        if not (port / "id-registry.json").exists():
            W.json(port / "id-registry.json", {"TASK": 0, "DEC": 0, "OQ": 0, "MTG": 0, "UAT": 0, "PCP": 0}, history=False)
        if not W.dry:
            (port / "plan-changes").mkdir(parents=True, exist_ok=True)
            (ws / "Projects").mkdir(parents=True, exist_ok=True)
    pc_migrate(a)
    if a.scan:
        pc_scan(argparse.Namespace(folders=a.scan, depth=a.depth, apply=True))
    if not W.dry:
        bundle(quiet=True)
    print(f"# this machine ({platform.node()}) now uses workspace {_p(ws)}")
    if not W.dry:
        try:
            pc_check(a)
        except SystemExit as e:
            if e.code:
                print("# fix the errors above, then run: wf.py projects check")


# ---- kit: carry the user-level workflow (CLAUDE.md, skills, wf.py, templates) to another computer

KIT_SKILLS = ["project-onboarding", "meeting-intake", "clarify", "project-memory", "work-management", "progress-view",
              "delivery-metrics", "capacity-planner", "estimate-assistant", "plan-change-control", "build-loop",
              "quality-gate", "uat-manager", "delivery-report"]
KIT_SKIP = ("__pycache__", ".pyc", "local.json")  # matched against the path INSIDE the kit, never the absolute path


def _claude_home(a):
    return _xp(a.claude_home) if getattr(a, "claude_home", None) else WF_HOME.parent


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kit_units(home):
    units = []
    if (home / "CLAUDE.md").is_file():
        units.append(("CLAUDE.md", home / "CLAUDE.md"))
    for s in KIT_SKILLS:
        if (home / "skills" / s).is_dir():
            units.append((f"skills/{s}", home / "skills" / s))
    units.append(("wirat-workflow", home / "wirat-workflow"))
    return units


def _unit_files(unit_path):
    if unit_path.is_file():
        return [(unit_path.name, unit_path)]
    return [(f.relative_to(unit_path).as_posix(), f) for f in sorted(unit_path.rglob("*"))
            if f.is_file() and not any(k in f.relative_to(unit_path).as_posix() for k in KIT_SKIP)]


def kit_pack(a):
    home = _claude_home(a)
    out = _xp(a.out) if a.out else Path.cwd() / f"wirat-kit-{stamp()}.zip"
    if out.exists():
        die(f"{out} already exists (kits are never overwritten)")
    manifest = {"created_at": now_iso(), "machine": platform.node(), "files": {}}
    entries = []
    for arc_root, path in kit_units(home):
        for rel, f in _unit_files(path):
            arc = arc_root if path.is_file() else f"{arc_root}/{rel}"
            entries.append((arc, f))
            manifest["files"][arc] = _sha(f)
    if W.dry:
        print(f"[dry-run] create: {out} ({len(entries)} files; local.json and caches excluded)")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("KIT.json", json.dumps(manifest, indent=1))
        for arc, f in entries:
            z.write(f, arc)
    print(f"kit written: {out} ({len(entries)} files). Copy it to the other computer, then:\n"
          f"  1) unzip it anywhere   2) python -I <unzipped>/wirat-workflow/scripts/wf.py kit install {out.name}   "
          f"3) wf.py setup --workspace <shared workspace> --scan <folder with your repos>")


def kit_install(a):
    home = _claude_home(a)
    z = zipfile.ZipFile(_xp(a.zip))
    names = [n for n in z.namelist() if n != "KIT.json"]
    for n in names:
        if n.startswith(("/", "\\")) or ".." in Path(n).parts or not (n == "CLAUDE.md" or n.startswith(("skills/", "wirat-workflow/"))):
            die(f"unsafe or unexpected path in kit: {n}")
    units = {}
    for n in names:
        key = n if n == "CLAUDE.md" else "/".join(n.split("/")[:2]) if n.startswith("skills/") else "wirat-workflow"
        units.setdefault(key, []).append(n)
    backup = home / "backups" / f"wirat-kit-{stamp()}"
    import tempfile
    for key, members in sorted(units.items()):
        dest = home / key
        incoming = {m: __import__("hashlib").sha256(z.read(m)).hexdigest() for m in members}
        if key == "CLAUDE.md":
            if not dest.exists():
                print(f"{'[dry-run] ' if W.dry else ''}create: {dest}")
                if not W.dry:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(z.read("CLAUDE.md"))
            elif _sha(dest) == incoming["CLAUDE.md"]:
                print(f"unchanged: {dest}")
            else:
                alt = home / "CLAUDE.wirat.md"
                print(f"{'[dry-run] ' if W.dry else ''}create: {alt}  (your CLAUDE.md differs: merge it by hand - yours is NOT overwritten)")
                if not W.dry:
                    alt.write_bytes(z.read("CLAUDE.md"))
            continue
        current = {f"{key}/{rel}": _sha(f) for rel, f in _unit_files(dest)} if dest.exists() else {}
        want = {m: h for m, h in incoming.items() if not any(k in m for k in KIT_SKIP)}
        if current == want:
            print(f"unchanged: {key}")
            continue
        print(f"{'[dry-run] ' if W.dry else ''}{'replace' if dest.exists() else 'install'}: {key}"
              + (f"  (old copy moved to {backup / key})" if dest.exists() else ""))
        if W.dry:
            continue
        tmp = Path(tempfile.mkdtemp(prefix="wf-kit-", dir=home))
        for m in members:
            if any(k in m for k in KIT_SKIP):
                continue
            t = tmp / m
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(z.read(m))
        keep_local = (dest / "local.json") if key == "wirat-workflow" and (dest / "local.json").exists() else None
        if dest.exists():
            (backup / key).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(backup / key))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp / key), str(dest))
        shutil.rmtree(tmp, ignore_errors=True)
        if keep_local:
            shutil.copy2(backup / key / "local.json", dest / "local.json")
    if not W.dry:
        print("# done. Next on this computer: python -I ~/.claude/wirat-workflow/scripts/wf.py setup --workspace <shared workspace folder> --scan <folder with your repos>")


def cmd_kit(a):
    {"pack": kit_pack, "install": kit_install}[a.kcmd](a)


# ---- views: the three HTML files are created once; this is the only way their code is updated

VIEWS = ("progress.html", "journey.html", "backlog.html")


def view_version(text):
    m = re.search(r"wf-view-version:\s*(\d+)", text)
    return int(m.group(1)) if m else 0


def cmd_views(a):
    slugs = [a.project] if a.project else project_slugs()
    for s in slugs:
        for v in VIEWS:
            tpl, dst = TEMPLATE_WS / "20-Views" / v, pws(s) / "20-Views" / v
            tv = view_version(tpl.read_text(encoding="utf-8"))
            if not dst.exists():
                W.copy(tpl, dst)
                print(f"{s}/{v}: restored from template (v{tv})")
                continue
            dv = view_version(dst.read_text(encoding="utf-8"))
            if dv >= tv and not a.force:
                print(f"{s}/{v}: up to date (v{dv})")
                continue
            W.copy(dst, dst.parent / "_prev" / f"{stamp()}_{v}.bak")  # .bak, so no extra .html file appears
            W.copy(tpl, dst)
            print(f"{s}/{v}: v{dv} -> v{tv} (previous kept as 20-Views/_prev/*_{v}.bak)")


def cmd_skill_rank(a):
    print(json.dumps(skill_ranking(_csv(a.candidates) or None), ensure_ascii=False, indent=2))


def cmd_log_skill(a):
    log_skill(a.skill, a.project, a.note or "")
    print(f"logged {a.skill}")


def cmd_bundle(a):
    bundle()


def cmd_metrics(a):
    recs = (load_feed(portfolio() / "delivery-metrics.json", {"records": []}) or {}).get("records", [])
    groups = {}
    for r in recs:
        if r.get("status") != "accepted":
            continue
        g = groups.setdefault(f"{r['task_type']}/{r['complexity']}", [])
        g.append(r["actual_days"] / r["estimate_days"])
    min_n = CONFIG.get("min_history_for_estimate", 3)
    for k, xs in sorted(groups.items()):
        verdict = f"median ratio {median(xs):.2f}" if len(xs) >= min_n else "insufficient data (reference only)"
        print(f"{k:32} n={len(xs):2}  {verdict}")


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="list target files, write nothing")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new-workspace", help="onboard: create Projects/<slug>/ProjectWorkspace from template")
    s.add_argument("slug"); s.add_argument("--name"); s.add_argument("--repo", help="source folder on THIS machine (kept in local.json)")
    s.add_argument("--at", help="create the ProjectWorkspace in this folder instead of <workspace>/Projects/<slug>/ProjectWorkspace")
    s.set_defaults(fn=cmd_new_workspace)

    s = sub.add_parser("next-id", help="allocate a portfolio-unique id (TASK, DEC, OQ, PCP, MTG, UAT)")
    s.add_argument("kind"); s.add_argument("--peek", action="store_true")
    s.set_defaults(fn=cmd_next_id)

    s = sub.add_parser("revise", help="copy latest revision of a .md artifact to a new timestamped file")
    s.add_argument("path"); s.set_defaults(fn=cmd_revise)

    s = sub.add_parser("progress", help="compute progress (print, or --write progress.json + bundle)")
    s.add_argument("project", nargs="?"); s.add_argument("--all", action="store_true")
    s.add_argument("--write", action="store_true"); s.add_argument("--skill")
    s.set_defaults(fn=cmd_progress)

    s = sub.add_parser("capacity", help="aggregate workload across projects")
    s.add_argument("--write", action="store_true"); s.set_defaults(fn=cmd_capacity)

    s = sub.add_parser("validate", help="check required task/open-question fields and dependencies")
    s.add_argument("project", nargs="?"); s.add_argument("--repair", action="store_true", help="restore hand-edited mirror files from their latest revision")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("update-task", help="update NON-plan fields: --set status=in-review --set progress=60")
    s.add_argument("task"); s.add_argument("--set", action="append"); s.set_defaults(fn=cmd_update_task)

    s = sub.add_parser("accept", help="User accepted a task: record delivery metric + mark accepted")
    s.add_argument("task"); s.add_argument("--actual-days", type=float, required=True)
    s.add_argument("--accepted"); s.add_argument("--accepted-by"); s.add_argument("--started")
    s.add_argument("--uat-sent"); s.add_argument("--variance")
    s.set_defaults(fn=cmd_accept)

    s = sub.add_parser("estimate", help="history- and capacity-aware estimate (read-only)")
    s.add_argument("--type", required=True); s.add_argument("--complexity", required=True)
    s.add_argument("--base-days", type=float); s.add_argument("--project"); s.add_argument("--due")
    s.add_argument("--priority"); s.set_defaults(fn=cmd_estimate)

    s = sub.add_parser("propose-change", help="create a Plan Change Proposal from a JSON spec")
    s.add_argument("--input", required=True); s.set_defaults(fn=cmd_propose_change)
    s = sub.add_parser("approve-change", help="record Wirat's approval as a new proposal revision")
    s.add_argument("id"); s.add_argument("--by", required=True); s.add_argument("--alternative", type=int)
    s.add_argument("--note"); s.set_defaults(fn=cmd_approve_change)
    s = sub.add_parser("reject-change"); s.add_argument("id"); s.add_argument("--by", default=OWNER)
    s.add_argument("--note"); s.set_defaults(fn=cmd_reject_change)
    s = sub.add_parser("apply-change", help="apply an APPROVED proposal to backlog/journey/capacity")
    s.add_argument("id"); s.set_defaults(fn=cmd_apply_change)

    s = sub.add_parser("check-exec-plan", help="gate multi-agent work: ownership, contracts, worktrees")
    s.add_argument("path"); s.set_defaults(fn=cmd_check_exec_plan)

    s = sub.add_parser("uat-revise", help="create a new timestamped UAT .xlsx revision + latest.json")
    s.add_argument("project"); s.add_argument("--input", required=True); s.set_defaults(fn=cmd_uat_revise)

    s = sub.add_parser("stakeholder", help="tasks owned by / waiting on a stakeholder, their OQs, impact on Wirat")
    s.add_argument("id"); s.set_defaults(fn=cmd_stakeholder)

    s = sub.add_parser("add-question", help="new Open Question (owner + target meeting required)")
    s.add_argument("project"); s.add_argument("--question", required=True); s.add_argument("--owner")
    s.add_argument("--target-meeting"); s.add_argument("--tasks", help="comma-separated task ids")
    s.add_argument("--raised-in"); s.add_argument("--options", help="'a|b|c' options presented")
    s.set_defaults(fn=cmd_add_question)
    s = sub.add_parser("update-question", help="answer / refine / drop an Open Question")
    s.add_argument("id"); s.add_argument("--question"); s.add_argument("--owner"); s.add_argument("--target-meeting")
    s.add_argument("--answer"); s.add_argument("--decision"); s.add_argument("--status")
    s.set_defaults(fn=cmd_update_question)
    s = sub.add_parser("journey-add", help="append ONE event file (+ module evolution); title <=160, summary <=600 chars")
    s.add_argument("project"); s.add_argument("--type", required=True); s.add_argument("--title", required=True)
    s.add_argument("--summary"); s.add_argument("--date"); s.add_argument("--modules"); s.add_argument("--tasks")
    s.add_argument("--stakeholders"); s.add_argument("--decision"); s.add_argument("--meeting"); s.add_argument("--plan-change")
    s.add_argument("--module-event", action="append", help="'module|stage|change' (repeatable)")
    s.add_argument("--ref", help="where the long text lives, relative to ProjectWorkspace (e.g. 00-Project/meetings/<file>)")
    s.set_defaults(fn=cmd_journey_add)
    s = sub.add_parser("decision-new", help="Decision Record + journey timeline/module events")
    s.add_argument("project"); s.add_argument("--title", required=True); s.add_argument("--context", required=True)
    s.add_argument("--decision", required=True); s.add_argument("--alternatives", help="'most|...|least' recommended")
    s.add_argument("--consequences"); s.add_argument("--decided-by"); s.add_argument("--supersedes")
    for k in ("--meetings", "--modules", "--tasks", "--stakeholders", "--uat"):
        s.add_argument(k, help="comma-separated")
    s.add_argument("--plan-change"); s.add_argument("--no-journey", action="store_true")
    s.set_defaults(fn=cmd_decision_new)

    s = sub.add_parser("journey", help="read the journey in a window (never the whole history)")
    s.add_argument("project"); s.add_argument("--limit", type=int, default=15); s.add_argument("--since"); s.add_argument("--until")
    s.add_argument("--type"); s.add_argument("--module"); s.add_argument("--task"); s.add_argument("--decision")
    s.add_argument("--stakeholder"); s.add_argument("--search"); s.add_argument("--full", action="store_true")
    s.add_argument("--digest", action="store_true", help="counts, last 15 events, per-module state (a few KB at most)")
    s.add_argument("--max-chars", type=int, default=OUT_CAP)
    s.set_defaults(fn=cmd_journey)
    s = sub.add_parser("journey-compact", help="migrate an old single-file journey to one-file-per-event (or --rebuild the digest)")
    s.add_argument("project", nargs="?"); s.add_argument("--all", action="store_true"); s.add_argument("--rebuild", action="store_true")
    s.set_defaults(fn=cmd_journey_compact)
    s = sub.add_parser("tasks", help="one line per task across projects (open first by risk); capped")
    s.add_argument("--project"); s.add_argument("--owner"); s.add_argument("--stakeholder"); s.add_argument("--health")
    s.add_argument("--status", help="open (default) | all | <exact status>", default="open"); s.add_argument("--due-before")
    s.add_argument("--limit", type=int, default=40); s.add_argument("--max-chars", type=int, default=OUT_CAP)
    s.set_defaults(fn=cmd_tasks)
    s = sub.add_parser("questions", help="one line per Open Question across projects (--open = only status open)")
    s.add_argument("--project"); s.add_argument("--open", action="store_true", help="only status open")
    s.add_argument("--limit", type=int, default=40); s.add_argument("--max-chars", type=int, default=OUT_CAP)
    s.set_defaults(fn=cmd_questions)
    s = sub.add_parser("artifacts", help="list the CURRENT revision of decisions / meetings / releases / stakeholders (one line each)")
    s.add_argument("project"); s.add_argument("--kind", choices=["decisions", "meetings", "releases", "stakeholders", "backlog", "all"], default="all")
    s.add_argument("-n", type=int, default=5); s.add_argument("--max-chars", type=int, default=OUT_CAP)
    s.set_defaults(fn=cmd_artifacts)

    s = sub.add_parser("projects", help="where projects live on THIS computer: list | map | unmap | add | remove | restore | set-workspace | check | scan | which | migrate")
    ps = s.add_subparsers(dest="pcmd", required=True)
    q = ps.add_parser("list"); q.add_argument("--json", action="store_true")
    q = ps.add_parser("map", help="tell this computer where a project's source folder / ProjectWorkspace is")
    q.add_argument("slug"); q.add_argument("--repo"); q.add_argument("--workspace"); q.add_argument("--force", action="store_true")
    q = ps.add_parser("unmap", help="forget a mapping on this computer only (nothing is deleted)")
    q.add_argument("slug"); q.add_argument("--repo", action="store_true"); q.add_argument("--workspace", action="store_true")
    q = ps.add_parser("add", help="register an existing ProjectWorkspace that lives in any folder")
    q.add_argument("slug"); q.add_argument("--workspace", required=True); q.add_argument("--repo"); q.add_argument("--name")
    q.add_argument("--force", action="store_true")
    q = ps.add_parser("remove", help="archive a project in the shared registry (files are kept)")
    q.add_argument("slug"); q.add_argument("--yes", action="store_true")
    q = ps.add_parser("restore"); q.add_argument("slug")
    q = ps.add_parser("set-workspace", help="where the shared workspace (Portfolio/ + Projects/) is on this computer")
    q.add_argument("path"); q.add_argument("--force", action="store_true")
    ps.add_parser("check", help="verify every mapping on this computer (exit 1 on errors)")
    q = ps.add_parser("scan", help="find source folders by git remote / folder name under the given folders")
    q.add_argument("folders", nargs="+"); q.add_argument("--depth", type=int, default=3); q.add_argument("--apply", action="store_true")
    q = ps.add_parser("which", help="which project is this folder part of?"); q.add_argument("path", nargs="?")
    ps.add_parser("migrate", help="move old absolute repo paths out of shared data into this computer's local config")
    s.set_defaults(fn=cmd_projects)

    s = sub.add_parser("setup", help="point THIS computer at the shared workspace (first run / after moving folders)")
    s.add_argument("--workspace", required=True); s.add_argument("--scan", nargs="+", help="folders that contain your source repos")
    s.add_argument("--depth", type=int, default=3); s.add_argument("--init", action="store_true", help="create an empty workspace there")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("kit", help="carry CLAUDE.md + skills + wf.py + templates to another computer")
    ks = s.add_subparsers(dest="kcmd", required=True)
    q = ks.add_parser("pack"); q.add_argument("--out"); q.add_argument("--claude-home")
    q = ks.add_parser("install"); q.add_argument("zip"); q.add_argument("--claude-home")
    s.set_defaults(fn=cmd_kit)

    s = sub.add_parser("views", help="upgrade the three HTML views from the template (old copy kept as .bak); no new .html files")
    s.add_argument("--project"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_views)

    s = sub.add_parser("skill-rank", help="skills by usage (count, then most recent); --candidates a,b")
    s.add_argument("--candidates"); s.set_defaults(fn=cmd_skill_rank)

    s = sub.add_parser("log-skill"); s.add_argument("skill"); s.add_argument("--project"); s.add_argument("--note")
    s.set_defaults(fn=cmd_log_skill)
    s = sub.add_parser("bundle", help="regenerate data.js mirrors for the HTML views")
    s.set_defaults(fn=cmd_bundle)
    s = sub.add_parser("metrics", help="summarise delivery history by type/complexity")
    s.set_defaults(fn=cmd_metrics)

    a = p.parse_args()
    W.dry = a.dry_run
    a.fn(a)


if __name__ == "__main__":
    main()

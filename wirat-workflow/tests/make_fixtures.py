#!/usr/bin/env python3
"""Build the sample Wirat workspace (Portfolio + 3 projects) into a target folder.

    python -I make_fixtures.py <workspace-root> [--force]

Used for the real sample at ~/Obsidian/Wirat-Workspace and by run_tests.py (into a temp folder).
Projects are onboarded through `wf.py new-workspace`, exactly like a real project, then seeded with
sample data as of 2026-11-01. Refuses to touch a non-empty target unless --force is given AND the
target is inside a temp/scratch folder.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WF = HERE.parent / "scripts" / "wf.py"
TODAY = "2026-11-01"
CREATED = "2026-11-01T09:00:00"


def wf(root, *args, check=True):
    env = dict(os.environ, WF_WORKSPACE=str(root), WF_TODAY=TODAY, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-I", str(WF), *args], env=env, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise SystemExit(f"wf.py {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def T(id, title, module, *, owner="wirat", stakeholders=(), priority="P2", status="todo", est=1, start=None, due=None,
      deps=(), blocked_by=(), waiting_on=None, risk="none", task_type="backend-feature", complexity="medium",
      dod="feature", progress=0, uat_date=None, oqs=(), **extra):
    t = {"id": id, "title": title, "module": module, "owner": owner, "stakeholders": list(stakeholders),
         "priority": priority, "status": status, "estimate_days": est, "start": start, "due": due,
         "dependencies": list(deps), "blocked_by": list(blocked_by), "waiting_on": waiting_on, "risk": risk,
         "task_type": task_type, "complexity": complexity, "definition_of_done": dod, "progress": progress,
         "open_questions": list(oqs)}
    if uat_date:
        t["uat_date"] = uat_date
    t.update(extra)
    return t


def stakeholder(id, name, role, project, power, freq, note):
    return f"""---
type: stakeholder
id: {id}
name: {name}
role: {role}
project: {project}
decision_power: {power}
update_frequency: {freq}
revision: 1
created_at: {CREATED}
---

# {name}

## Interests / concerns
- {note}
"""


PROJECTS = {
    "food-delivery": {
        "name": "Food Delivery App",
        "repo": r"C:\Data\Drive D\demo-ai-workflow\project-1-food-delivery",
        "stakeholders": [
            ("nok", "Nok", "Business User", "high", "weekly", "ร้านอาหารต้องเห็นสถานะออเดอร์แบบ real-time"),
            ("ton", "Ton", "Vendor", "medium", "weekly", "ผู้ให้บริการ payment gateway — ส่ง sandbox key / webhook spec"),
            ("manager-kittipong", "Kittipong", "Manager", "high", "bi-weekly", "ดูภาพรวมทุกโปรเจกต์และ resource"),
        ],
        "tasks": [
            T("TASK-001", "Login & JWT session", "auth", status="accepted", est=3, start="2026-10-01", due="2026-10-06",
              uat_date="2026-10-06", progress=100, stakeholders=["nok"], user_accepted="2026-10-08"),
            T("TASK-002", "Menu management UI", "menu", status="accepted", est=2, start="2026-10-07", due="2026-10-10",
              uat_date="2026-10-10", task_type="frontend-feature", progress=100, stakeholders=["nok"], user_accepted="2026-10-13"),
            T("TASK-003", "Order status timeline UI", "order", priority="P1", status="in-progress", est=2, start="2026-10-28",
              due="2026-11-04", progress=75, task_type="frontend-feature", stakeholders=["nok"]),
            T("TASK-004", "Payment webhook handler", "payment", priority="P1", status="in-progress", est=2, start="2026-10-27",
              due="2026-11-04", progress=75, blocked_by=["ton"], complexity="high", stakeholders=["ton", "nok"], oqs=["OQ-002"]),
            T("TASK-005", "Rider live location map", "rider-tracking", est=3, start="2026-11-09", due="2026-11-20",
              deps=["TASK-004"], task_type="fullstack-feature", complexity="high", stakeholders=["nok"]),
            T("TASK-006", "Confirm promo code rules document", "promo", owner="nok", priority="P2", est=0.5,
              start="2026-10-27", due="2026-10-31", dod="feature", stakeholders=["wirat"], oqs=["OQ-001"]),
            T("TASK-007", "Order history API pagination", "order", priority="P3", est=1, start="2026-11-09", due="2026-11-13",
              complexity="low", stakeholders=["nok"]),
            T("TASK-008", "Prepare UAT round 1", "order", est=1, start="2026-11-09", due="2026-11-10", deps=["TASK-003", "TASK-004"],
              task_type="uat-prep", dod="uat", stakeholders=["nok"]),
        ],
        "open_questions": [
            {"id": "OQ-001", "question": "Promo code ยังอยู่ใน scope เฟส 1 หรือไม่", "owner": "nok",
             "target_meeting": "MTG-002 (2026-11-05)", "status": "open", "linked_tasks": ["TASK-006"], "raised_in": "onboarding"},
            {"id": "OQ-002", "question": "Payment sandbox key และ webhook signature spec จะได้เมื่อไหร่", "owner": "ton",
             "target_meeting": "MTG-002 (2026-11-05)", "status": "open", "linked_tasks": ["TASK-004"], "raised_in": "MTG-001"},
        ],
        "timeline": [
            {"date": "2026-10-01", "type": "milestone", "title": "Project kickoff", "summary": "เริ่มเฟส 1: order + payment", "modules": ["auth", "order"], "stakeholders": ["nok"]},
            {"date": "2026-10-08", "type": "acceptance", "title": "TASK-001 accepted by User", "modules": ["auth"], "tasks": ["TASK-001"], "stakeholders": ["nok"]},
            {"date": "2026-10-13", "type": "acceptance", "title": "TASK-002 accepted by User", "modules": ["menu"], "tasks": ["TASK-002"], "stakeholders": ["nok"]},
            {"date": "2026-10-20", "type": "decision", "title": "DEC-001 ใช้ webhook แทน polling สำหรับ payment", "modules": ["payment"], "decision": "DEC-001", "meeting": "MTG-001", "stakeholders": ["ton"]},
        ],
        "modules": [
            {"module": "auth", "evolution": [{"date": "2026-10-06", "stage": "implemented", "change": "JWT login", "task": "TASK-001"},
                                             {"date": "2026-10-08", "stage": "accepted", "change": "User sign-off", "task": "TASK-001"}]},
            {"module": "payment", "evolution": [{"date": "2026-10-20", "stage": "designed", "change": "webhook-based flow", "decision": "DEC-001"}]},
            {"module": "order", "evolution": [{"date": "2026-10-28", "stage": "in-progress", "change": "status timeline UI", "task": "TASK-003"}]},
        ],
        "decisions": [("DEC-001", "ใช้ webhook แทน polling สำหรับ payment", "MTG-001", ["payment"], ["TASK-004"], ["ton"])],
        "meetings": {"20261020-100000_MTG-001_notes.md": "notes", "20261101-090000_MTG-002_agenda.md": "agenda"},
    },
    "it-service-request": {
        "name": "IT Service Request",
        "repo": r"C:\Data\Drive D\demo-ai-workflow\project-2-it-service-request",
        "stakeholders": [
            ("ploy", "Ploy", "Business User", "high", "weekly", "หัวหน้า service desk — ต้องการ SLA dashboard และรายงานรายเดือน"),
            ("arthit", "Arthit", "Key User", "medium", "weekly", "IT infra / LDAP admin"),
            ("manager-kittipong", "Kittipong", "Manager", "high", "bi-weekly", "อนุมัติ SMTP relay และ server"),
        ],
        "tasks": [
            T("TASK-009", "Create service request API", "request", status="accepted", est=4, start="2026-10-01", due="2026-10-07",
              uat_date="2026-10-08", progress=100, stakeholders=["ploy"], user_accepted="2026-10-10"),
            T("TASK-010", "Request form UI", "request", status="accepted", est=3, start="2026-10-08", due="2026-10-13",
              uat_date="2026-10-13", progress=100, task_type="frontend-feature", stakeholders=["ploy"], user_accepted="2026-10-15"),
            T("TASK-011", "Export request list to Excel", "report", status="accepted", est=2, start="2026-10-14", due="2026-10-16",
              uat_date="2026-10-17", progress=100, task_type="report-export", stakeholders=["ploy"], user_accepted="2026-10-20"),
            T("TASK-012", "LDAP login integration", "auth-ldap", status="accepted", est=5, start="2026-10-13", due="2026-10-20",
              uat_date="2026-10-22", progress=100, task_type="integration", complexity="high", stakeholders=["arthit"], user_accepted="2026-10-24"),
            T("TASK-013", "Confirm SLA matrix per priority", "sla", owner="ploy", priority="P1", est=0.5, start="2026-10-29",
              due="2026-11-03", stakeholders=["wirat"], dod="feature"),
            T("TASK-014", "SLA calculation API", "sla", priority="P1", status="in-progress", est=3, start="2026-10-29",
              due="2026-11-04", progress=70, stakeholders=["ploy"]),
            T("TASK-015", "SLA breach alert job", "sla", priority="P1", status="in-progress", est=1, start="2026-10-27",
              due="2026-10-30", progress=50, stakeholders=["ploy"]),
            T("TASK-016", "Request approval workflow", "request", priority="P1", status="uat", est=3, start="2026-10-22",
              due="2026-10-31", uat_date="2026-10-29", uat_sent="2026-10-29", progress=100, waiting_on="user", stakeholders=["ploy"]),
            T("TASK-017", "Email notification on assign", "notification", status="in-progress", est=0.5, start="2026-10-30",
              due="2026-11-05", progress=50, waiting_on="manager", complexity="low", stakeholders=["manager-kittipong", "arthit"]),
            T("TASK-018", "Monthly SLA report export", "report", priority="P3", est=1, start="2026-11-04", due="2026-11-06",
              deps=["TASK-014"], task_type="report-export", stakeholders=["ploy"], oqs=["OQ-003"]),
            T("TASK-019", "SLA dashboard UI", "sla", est=3, start="2026-11-09", due="2026-11-12", deps=["TASK-014", "TASK-013"],
              task_type="frontend-feature", stakeholders=["ploy"]),
            T("TASK-020", "Prepare UAT round 2", "sla", est=1, start="2026-11-12", due="2026-11-13", deps=["TASK-018", "TASK-019"],
              task_type="uat-prep", dod="uat", stakeholders=["ploy", "arthit"]),
        ],
        "open_questions": [
            {"id": "OQ-003", "question": "รายงาน SLA รายเดือนต้องมีคอลัมน์อะไร และต้องเป็น PDF หรือ Excel", "owner": "ploy",
             "target_meeting": "MTG-004 (2026-11-04)", "status": "open", "linked_tasks": ["TASK-018"], "raised_in": "MTG-003"},
            {"id": "OQ-004", "question": "ใช้ LDAP group ไหนเป็นผู้อนุมัติคำขอ", "owner": "arthit",
             "target_meeting": "MTG-004 (2026-11-04)", "status": "open", "linked_tasks": ["TASK-016"], "raised_in": "MTG-003"},
        ],
        "timeline": [
            {"date": "2026-10-01", "type": "milestone", "title": "Project kickoff", "modules": ["request"], "stakeholders": ["ploy"]},
            {"date": "2026-10-24", "type": "acceptance", "title": "TASK-012 LDAP login accepted", "modules": ["auth-ldap"], "tasks": ["TASK-012"], "stakeholders": ["arthit"]},
            {"date": "2026-10-29", "type": "meeting", "title": "MTG-003 progress meeting", "summary": "Demo approval workflow, ขอรายงาน SLA รายเดือน", "meeting": "MTG-003", "modules": ["request", "report"], "stakeholders": ["ploy", "arthit"]},
            {"date": "2026-10-29", "type": "decision", "title": "DEC-002 แจ้งเตือนผ่าน email ก่อน, LINE เฟส 2", "modules": ["notification"], "decision": "DEC-002", "meeting": "MTG-003", "stakeholders": ["ploy"]},
        ],
        "modules": [
            {"module": "request", "evolution": [{"date": "2026-10-10", "stage": "accepted", "change": "request API", "task": "TASK-009"},
                                                {"date": "2026-10-29", "stage": "uat", "change": "approval workflow sent to UAT", "task": "TASK-016"}]},
            {"module": "notification", "evolution": [{"date": "2026-10-29", "stage": "designed", "change": "email first, LINE phase 2", "decision": "DEC-002"}]},
            {"module": "sla", "evolution": [{"date": "2026-10-29", "stage": "in-progress", "change": "SLA calculation", "task": "TASK-014"}]},
        ],
        "decisions": [("DEC-002", "แจ้งเตือนผ่าน email ก่อน LINE ไว้เฟส 2", "MTG-003", ["notification"], ["TASK-017"], ["ploy"])],
        "meetings": {"20261029-140000_MTG-003_notes.md": "notes", "20261101-090000_MTG-004_agenda.md": "agenda"},
        "uat": {"note": "UAT round 1 (approval workflow)", "add": [
            {"module": "request", "scenario": "ผู้ใช้ส่งคำขอและหัวหน้าอนุมัติ", "preconditions": "มี user requester01, approver01",
             "steps": ["Login requester01", "สร้างคำขอ", "Login approver01", "อนุมัติ"], "expected": "สถานะ Approved และ requester เห็นผล",
             "tester": "ploy", "tasks": ["TASK-016"], "stakeholders": ["ploy"], "test_data": "UAT env, REQ-1001", "status": "Pass", "actual": "ตามที่คาด"},
            {"module": "request", "scenario": "หัวหน้าปฏิเสธคำขอพร้อมเหตุผล", "preconditions": "คำขอสถานะ Pending",
             "steps": ["Login approver01", "เปิดคำขอ", "Reject + ใส่เหตุผล"], "expected": "สถานะ Rejected แสดงเหตุผล",
             "tester": "ploy", "tasks": ["TASK-016"], "stakeholders": ["ploy"], "status": "Pass", "actual": "ตามที่คาด"},
            {"module": "request", "scenario": "อนุมัติแทน (delegate) เมื่อหัวหน้าลา", "preconditions": "ตั้ง delegate แล้ว",
             "steps": ["Login delegate01", "อนุมัติคำขอ"], "expected": "อนุมัติได้และบันทึกว่าอนุมัติแทน",
             "tester": "ploy", "tasks": ["TASK-016"], "stakeholders": ["ploy", "arthit"], "status": "Blocked", "remarks": "รอ LDAP group (OQ-004)"},
        ]},
    },
    "approval-system": {
        "name": "Approval System",
        "repo": "",
        "stakeholders": [
            ("somchai", "Somchai", "Business User", "high", "weekly", "ต้องการลดเวลาอนุมัติเอกสาร"),
            ("manager-kittipong", "Kittipong", "Manager", "high", "bi-weekly", "อนุมัติ UAT server"),
        ],
        "tasks": [
            T("TASK-021", "Approval request API (v1)", "approval", status="accepted", est=3, start="2026-10-12", due="2026-10-16",
              uat_date="2026-10-16", progress=100, stakeholders=["somchai"], user_accepted="2026-10-19"),
            T("TASK-022", "Approval list UI", "approval", est=2, start="2026-11-09", due="2026-11-10", deps=["TASK-023"],
              task_type="frontend-feature", stakeholders=["somchai"]),
            T("TASK-023", "Approval API — multi-step", "approval", priority="P1", status="in-progress", est=3, start="2026-10-28",
              due="2026-11-06", progress=80, stakeholders=["somchai"]),
            T("TASK-024", "Audit log", "audit", est=2, start="2026-11-09", due="2026-11-13", risk="medium", stakeholders=["somchai"]),
            T("TASK-025", "Delegation rules", "delegation", est=3, start="2026-11-10", due="2026-11-18", complexity="high",
              stakeholders=["somchai"], oqs=["OQ-005"]),
            T("TASK-026", "UAT server setup", "deploy", est=1, start="2026-11-05", due="2026-11-09", waiting_on="manager",
              task_type="devops", complexity="low", dod="code", stakeholders=["manager-kittipong"]),
            T("TASK-027", "Provide approval matrix sample data", "approval", owner="somchai", est=0.5, start="2026-11-01",
              due="2026-11-04", stakeholders=["wirat"]),
            T("TASK-028", "Approve UAT server request", "deploy", owner="manager-kittipong", priority="P1", est=0.5,
              start="2026-11-01", due="2026-11-03", stakeholders=["wirat"], dod="code"),
        ],
        "open_questions": [
            {"id": "OQ-005", "question": "Delegation ซ้อนได้กี่ชั้น และหมดอายุอัตโนมัติไหม", "owner": "somchai",
             "target_meeting": "MTG-006 (2026-11-06)", "status": "open", "linked_tasks": ["TASK-025"], "raised_in": "MTG-005"},
        ],
        "timeline": [
            {"date": "2026-10-12", "type": "milestone", "title": "Project kickoff", "modules": ["approval"], "stakeholders": ["somchai"]},
            {"date": "2026-10-19", "type": "acceptance", "title": "TASK-021 accepted by User", "modules": ["approval"], "tasks": ["TASK-021"], "stakeholders": ["somchai"]},
            {"date": "2026-10-27", "type": "decision", "title": "DEC-003 multi-step approval สูงสุด 3 ขั้น", "modules": ["approval"], "decision": "DEC-003", "meeting": "MTG-005", "stakeholders": ["somchai"]},
        ],
        "modules": [
            {"module": "approval", "evolution": [{"date": "2026-10-19", "stage": "accepted", "change": "single-step API v1", "task": "TASK-021"},
                                                 {"date": "2026-10-27", "stage": "redesign", "change": "multi-step (max 3)", "decision": "DEC-003"}]},
        ],
        "decisions": [("DEC-003", "Multi-step approval สูงสุด 3 ขั้น", "MTG-005", ["approval"], ["TASK-023"], ["somchai"])],
        "meetings": {"20261027-100000_MTG-005_notes.md": "notes"},
    },
}

METRICS = [
    ("TASK-001", "food-delivery", "auth", "backend-feature", "medium", 3, 3.5, "2026-10-01", "2026-10-06", "2026-10-08", "เพิ่ม refresh token ตามที่ User ขอ"),
    ("TASK-002", "food-delivery", "menu", "frontend-feature", "medium", 2, 2.5, "2026-10-07", "2026-10-10", "2026-10-13", "ปรับ UI ตาม feedback รอบแรก"),
    ("TASK-009", "it-service-request", "request", "backend-feature", "medium", 4, 5, "2026-10-01", "2026-10-08", "2026-10-10", "validation เพิ่มหลังประชุม"),
    ("TASK-010", "it-service-request", "request", "frontend-feature", "medium", 3, 3, "2026-10-08", "2026-10-13", "2026-10-15", ""),
    ("TASK-011", "it-service-request", "report", "report-export", "medium", 2, 3, "2026-10-14", "2026-10-17", "2026-10-20", "format Excel ต้องตรง template บัญชี"),
    ("TASK-012", "it-service-request", "auth-ldap", "integration", "high", 5, 7, "2026-10-13", "2026-10-22", "2026-10-24", "รอ firewall rule 2 วัน"),
    ("TASK-021", "approval-system", "approval", "backend-feature", "medium", 3, 4, "2026-10-12", "2026-10-16", "2026-10-19", "Additional validation requested after meeting"),
]


def meeting_text(slug, fname, kind):
    mid = fname.split("_")[1]
    date = f"{fname[:4]}-{fname[4:6]}-{fname[6:8]}"
    if kind == "agenda":
        return f"""---
type: meeting-agenda
id: {mid}
project: {slug}
date: {date}
revision: 1
created_at: {CREATED}
---

# Agenda — {slug} progress meeting ({mid})

| # | Topic | Owner | Goal | Linked |
|---|---|---|---|---|
| 1 | Demo งานที่เสร็จ | wirat | review | |
| 2 | ปิด Open Questions | stakeholders | decide | ดู 10-Data/backlog.json |
| 3 | ยืนยันวัน UAT รอบถัดไป | wirat | decide | |
"""
    return f"""---
type: meeting-note
id: {mid}
project: {slug}
date: {date}
source: notes
revision: 1
created_at: {CREATED}
---

# Meeting Notes — {mid} ({date})

## Facts
| # | Fact | Said by | Evidence |
|---|---|---|---|
| 1 | (sample) ทีมยืนยันขอบเขตเฟส 1 | stakeholder | notes |

## Decisions
| # | Decision | Decided by | → Decision Record |
|---|---|---|---|
| 1 | ดู decisions/ ที่อ้างอิง {mid} | stakeholder | decisions/ |
"""


def build(root):
    root = Path(root)
    port = root / "Portfolio"
    (port / "plan-changes").mkdir(parents=True, exist_ok=True)
    dump(port / "capacity.json", {
        "working_hours_per_day": 8, "focus_factor": 0.75, "working_weekdays": [0, 1, 2, 3, 4],
        "non_working_dates": ["2026-12-07", "2026-12-10", "2026-12-31"], "leave_hours_this_week": 0,
        "projects": [], "available_hours_this_week": None, "conflicts": [],
        "_notes": "Settings above are edited by Wirat; the rest is recomputed by `wf.py capacity --write`."})
    dump(port / "delivery-metrics.json", {"description": "Accepted deliveries across all projects (user level).", "records": [
        {"task_id": m[0], "project": m[1], "module": m[2], "task_type": m[3], "complexity": m[4], "estimate_days": m[5],
         "actual_days": m[6], "started": m[7], "uat_sent": m[8], "user_accepted": m[9], "variance_days": round(m[6] - m[5], 2),
         "variance_reason": m[10], "status": "accepted", "recorded_at": f"{m[9]}T17:00:00"} for m in METRICS]})
    dump(port / "skill-usage.json", {"counts": {"progress-view": 9, "build-loop": 7, "meeting-intake": 4, "estimate-assistant": 3,
                                                "delivery-metrics": 7, "plan-change-control": 2, "uat-manager": 1}, "log": []})
    dump(port / "id-registry.json", {"TASK": 28, "DEC": 3, "OQ": 5, "MTG": 6, "UAT": 0, "PCP": 0})
    dump(port / "projects.json", {"projects": []})

    for slug, p in PROJECTS.items():
        wf(root, "new-workspace", slug, "--name", p["name"], "--repo", p["repo"])
        ws = root / "Projects" / slug / "ProjectWorkspace"
        bl = json.loads((ws / "10-Data" / "backlog.json").read_text(encoding="utf-8"))
        for t in p["tasks"]:
            t["project"] = slug
            t["revision"] = 1
        bl.update({"tasks": p["tasks"], "open_questions": p["open_questions"], "updated_at": CREATED})
        dump(ws / "10-Data" / "backlog.json", bl)
        # seed in the OLD single-file layout on purpose, then migrate like a real upgrade would
        dump(ws / "10-Data" / "journey.json", {"project": slug, "timeline": p["timeline"], "modules": p["modules"], "updated_at": CREATED})
        for sid, name, role, power, freq, note in p["stakeholders"]:
            write(ws / "00-Project" / "stakeholders" / f"{sid}.md", stakeholder(sid, name, role, slug, power, freq, note))
        for did, title, mtg, mods, tasks, sh in p["decisions"]:
            write(ws / "00-Project" / "decisions" / f"20261020-120000_{did}_{did.lower()}.md",
                  f"---\ntype: decision\nid: {did}\ntitle: {title}\nproject: {slug}\nstatus: accepted\ndecided_by: {sh[0]}\n"
                  f"meetings: [{mtg}]\nmodules: [{', '.join(mods)}]\ntasks: [{', '.join(tasks)}]\nstakeholders: [{', '.join(sh)}]\n"
                  f"revision: 1\ncreated_at: {CREATED}\n---\n\n# {did}: {title}\n\n## Context\nตกลงใน {mtg}.\n\n## Decision\n{title}\n")
        for fname, kind in p["meetings"].items():
            write(ws / "00-Project" / "meetings" / fname, meeting_text(slug, fname, kind))
        inv_rows = "\n".join(
            f"| {t['title']} | {t['module']} | "
            f"{'Implemented' if t['status'] in ('accepted', 'done') else 'Partially Implemented' if t['status'] in ('in-progress', 'uat', 'in-review') else 'Planned'}"
            f" | backlog {t['id']} (sample data) | {t['id']} | |" for t in p["tasks"] if t["owner"] == "wirat")
        inv = (ws / "00-Project" / "feature-inventory.md")
        inv.write_text(inv.read_text(encoding="utf-8").rstrip() + "\n" + inv_rows + "\n", encoding="utf-8")
        if p.get("uat"):
            f = root / f"_uat_{slug}.json"
            dump(f, p["uat"])
            wf(root, "uat-revise", slug, "--input", str(f))
            f.unlink()

    wf(root, "journey-compact", "--all")
    wf(root, "progress", "--all", "--write")
    wf(root, "capacity", "--write")
    ov = ["---", "type: portfolio-overview", "revision: 1", f"created_at: {CREATED}", "---", "",
          "# Wirat — Portfolio Overview", "",
          "> Live numbers: open any `Projects/<slug>/ProjectWorkspace/20-Views/progress.html` and choose **ทุกโปรเจกต์**.",
          "> Data: `capacity.json`, `delivery-metrics.json`, `skill-usage.json`, `plan-changes/`.", "",
          "| Project | Name | Repo | Views |", "|---|---|---|---|"]
    for slug, p in PROJECTS.items():
        ov.append(f"| {slug} | {p['name']} | `{p['repo'] or '—'}` | [[Projects/{slug}/ProjectWorkspace/20-Views/progress.html]] |")
    ov += ["", "## Rules", "- Plan changes: `plan-changes/` proposals, applied only after Wirat approves.",
           "- Delivery metrics: one record per User-accepted task; estimates use ≥ 3 similar records."]
    write(port / "portfolio-overview.md", "\n".join(ov) + "\n")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    root = Path(os.path.expanduser(sys.argv[1]))
    if root.exists() and any(root.iterdir()):
        temp_like = any(k in str(root).lower() for k in ("temp", "tmp", "scratch"))
        if "--force" not in sys.argv or not temp_like:
            raise SystemExit(f"{root} is not empty; refusing to overwrite (fixtures never overwrite a real workspace)")
    build(root)
    print(f"fixtures built in {root}")


if __name__ == "__main__":
    main()

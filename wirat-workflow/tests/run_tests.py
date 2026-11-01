#!/usr/bin/env python3
"""Acceptance tests for the Wirat workflow (spec section 12 + section 10 routing).

    python -I ~/.claude/wirat-workflow/tests/run_tests.py [-v]

Builds the sample fixtures into a temp folder and exercises wf.py the way the skills do.
Never touches ~/Obsidian/Wirat-Workspace.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WF_HOME = HERE.parent
WF = WF_HOME / "scripts" / "wf.py"
CLAUDE_HOME = WF_HOME.parent
SKILLS = ["project-onboarding", "meeting-intake", "clarify", "project-memory", "work-management", "progress-view",
          "delivery-metrics", "capacity-planner", "estimate-assistant", "plan-change-control", "build-loop",
          "quality-gate", "uat-manager", "delivery-report"]
sys.path.insert(0, str(HERE))
import make_fixtures  # noqa: E402

BASE = None


TPL_VIEWS = WF_HOME / "templates" / "ProjectWorkspace" / "20-Views"


def view_ver(p):
    return re.search(r"wf-view-version:\s*(\d+)", Path(p).read_text(encoding="utf-8")).group(1)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tree_hash(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def setUpModule():
    global BASE
    BASE = Path(tempfile.mkdtemp(prefix="wf-test-base-"))
    os.environ["WF_LOCAL_CONFIG"] = str(BASE / "local-base.json")  # never touch the real machine config
    make_fixtures.build(BASE / "ws")


def tearDownModule():
    shutil.rmtree(BASE, ignore_errors=True)


class WFTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wf-test-"))
        self.ws = self.tmp / "ws"
        shutil.copytree(BASE / "ws", self.ws)
        self.local = self.tmp / "local.json"
        if (BASE / "local-base.json").exists():
            shutil.copy2(BASE / "local-base.json", self.local)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def wf(self, *args, code=0):
        env = dict(os.environ, WF_WORKSPACE=str(self.ws), WF_TODAY="2026-11-01", PYTHONIOENCODING="utf-8",
                   WF_LOCAL_CONFIG=str(self.local))
        r = subprocess.run([sys.executable, "-I", str(WF), *map(str, args)], env=env, capture_output=True,
                           text=True, encoding="utf-8")
        if code is not None:
            self.assertEqual(r.returncode, code, f"wf.py {args}\nstdout:{r.stdout}\nstderr:{r.stderr}")
        return r

    def proj(self, slug):
        return self.ws / "Projects" / slug / "ProjectWorkspace"

    def backlog(self, slug):
        return json.loads((self.proj(slug) / "10-Data" / "backlog.json").read_text(encoding="utf-8"))

    def task(self, slug, tid):
        return next(t for t in self.backlog(slug)["tasks"] if t["id"] == tid)

    def json_file(self, p, obj):
        p = self.tmp / p
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p


class T01_Skills(WFTest):
    def test_all_14_skills_have_valid_skill_md(self):
        for s in SKILLS:
            p = CLAUDE_HOME / "skills" / s / "SKILL.md"
            self.assertTrue(p.exists(), p)
            text = p.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
            self.assertIsNotNone(m, f"{s}: no frontmatter")
            fm = m.group(1)
            self.assertRegex(fm, rf"(?m)^name: {re.escape(s)}$")
            desc = re.search(r"(?m)^description: (.+)$", fm)
            self.assertTrue(desc and len(desc.group(1)) > 120, f"{s}: description too short")
            for section in ("Trigger conditions", "Inputs", "Steps", "Output files", "Guardrails", "Example output"):
                self.assertRegex(text, rf"(?m)^## {section}", f"{s}: missing section {section}")

    def test_user_claude_md_routes_every_skill(self):
        text = (CLAUDE_HOME / "CLAUDE.md").read_text(encoding="utf-8")
        for s in SKILLS:
            self.assertIn(f"`{s}`", text)


class T02_Routing(WFTest):
    """Section 10 phrases: the intended skill's description must carry the trigger so Claude picks it."""
    CASES = [
        ("นี่ transcript ประชุมเมื่อวาน", "meeting-intake", "transcript ประชุม"),
        ("ดู progress หน่อย ตอนนี้ใครค้างอะไรบ้าง", "progress-view", "ใครค้างอะไรบ้าง"),
        ("ช่วย estimate งานเพิ่ม export PDF", "estimate-assistant", "estimate งานเพิ่ม"),
        ("ทำ task ถัดไป", "build-loop", "ทำ task ถัดไป"),
        ("ทำต่อจนครบ", "build-loop", "ทำต่อจนครบ"),
        ("User บอกว่า TASK-016 ผ่านแล้ว", "delivery-metrics", "ผ่านแล้ว"),
        ("ต้องเลื่อน TASK-018 เป็นสัปดาห์หน้า", "plan-change-control", "เลื่อน TASK-018"),
        ("เตรียม UAT ให้หน่อย", "uat-manager", "เตรียม UAT"),
        ("สรุปงานที่เสร็จแล้วเตรียมนำเสนอ User", "delivery-report", "เตรียมนำเสนอ User"),
    ]

    def test_phrases_route_to_expected_skill(self):
        descs = {}
        for s in SKILLS:
            fm = (CLAUDE_HOME / "skills" / s / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
            descs[s] = re.search(r"(?m)^description: (.+)$", fm).group(1)
        for phrase, skill, key in self.CASES:
            self.assertIn(key, descs[skill], f"'{phrase}' → {skill}")
            others = [s for s, d in descs.items() if key in d and s != skill]
            self.assertEqual(others, [], f"'{phrase}' trigger is ambiguous: {others}")


class T03_Structure(WFTest):
    def test_portfolio_and_workspaces(self):
        port = self.ws / "Portfolio"
        for f in ("portfolio-overview.md", "capacity.json", "delivery-metrics.json", "plan-changes"):
            self.assertTrue((port / f).exists(), f)
        slugs = sorted(p.name for p in (self.ws / "Projects").iterdir())
        self.assertGreaterEqual(len(slugs), 3)
        for s in slugs:
            ws = self.proj(s)
            for rel in ("00-Project/project-overview.md", "00-Project/feature-inventory.md", "00-Project/stakeholders",
                        "00-Project/decisions", "00-Project/modules", "00-Project/backlog", "00-Project/journey",
                        "00-Project/meetings", "00-Project/uat", "00-Project/releases", "10-Data/progress.json",
                        "10-Data/backlog.json", "10-Data/journey.json", "20-Views/progress.html",
                        "20-Views/journey.html", "20-Views/backlog.html"):
                self.assertTrue((ws / rel).exists(), f"{s}/{rel}")
        self.wf("validate")

    def test_validate_catches_missing_fields_and_orphan_questions(self):
        p = self.proj("approval-system") / "10-Data" / "backlog.json"
        bl = json.loads(p.read_text(encoding="utf-8"))
        del bl["tasks"][1]["due"]
        bl["open_questions"].append({"id": "OQ-099", "question": "?", "owner": "", "target_meeting": ""})
        p.write_text(json.dumps(bl), encoding="utf-8")
        r = self.wf("validate", code=1)
        self.assertIn("missing due", r.stdout)
        self.assertIn("OQ-099", r.stdout)


class T04_HtmlViews(WFTest):
    def test_views_read_local_data_without_server(self):
        ws = self.proj("it-service-request")
        for v in ("progress.html", "journey.html", "backlog.html"):
            html = (ws / "20-Views" / v).read_text(encoding="utf-8")
            self.assertIn('<script src="../10-Data/data.js"></script>', html)
            self.assertIn('<script src="../../../../Portfolio/portfolio-data.js"></script>', html)
            # data never leaves the machine: only the styling CDNs (Tailwind, Google Fonts) may be fetched
            urls = set(re.findall(r"https?://[^\s\"'<>)]+", html))
            allowed = ("https://cdn.tailwindcss.com", "https://fonts.googleapis.com", "https://fonts.gstatic.com")
            self.assertEqual([u for u in sorted(urls) if not u.startswith(allowed)], [], f"{v} may only load styling CDNs")
        for f in (ws / "10-Data" / "data.js", self.ws / "Portfolio" / "portfolio-data.js"):
            body = f.read_text(encoding="utf-8")
            obj = json.loads(body[body.index("=") + 1:].rstrip().rstrip(";"))
            self.assertTrue(obj)
        # relative path from 20-Views really reaches the portfolio bundle
        self.assertTrue((ws / "20-Views" / "../../../../Portfolio/portfolio-data.js").resolve().exists())

    def test_progress_filters_and_modes(self):
        html = (self.proj("food-delivery") / "20-Views" / "progress.html").read_text(encoding="utf-8")
        for fid in ("f-project", "f-module", "f-owner", "f-stake", "f-status", "f-health", "f-due"):
            self.assertIn(f'id="{fid}"', html)
        for mode in ("all", "project", "wirat", "stakeholder"):
            self.assertIn(f'data-mode="{mode}"', html)
        for h in ("on-track", "at-risk", "delayed", "blocked", "waiting-user", "waiting-manager"):
            self.assertIn(f'"{h}":"', html)

    def test_portfolio_bundle_supports_cross_project_filtering(self):
        body = (self.ws / "Portfolio" / "portfolio-data.js").read_text(encoding="utf-8")
        data = json.loads(body[body.index("=") + 1:].rstrip().rstrip(";"))
        self.assertEqual(len({t["project"] for t in data["tasks"]}), 3)
        healths = {t["health"] for t in data["tasks"]}
        for h in ("at-risk", "delayed", "blocked", "waiting-user", "waiting-manager", "done"):
            self.assertIn(h, healths)
        self.assertTrue(any(t["owner"] != "wirat" for t in data["tasks"]), "stakeholder-owned tasks present")
        self.assertTrue(all("stakeholders" in t and "status" in t for t in data["tasks"]))

    def test_updates_do_not_create_html(self):
        before = sorted(p.name for p in (self.proj("it-service-request") / "20-Views").iterdir())
        h = sha(self.proj("it-service-request") / "20-Views" / "progress.html")
        self.wf("progress", "--all", "--write")
        self.wf("update-task", "TASK-014", "--set", "progress=90")
        self.assertEqual(before, sorted(p.name for p in (self.proj("it-service-request") / "20-Views").iterdir()))
        self.assertEqual(h, sha(self.proj("it-service-request") / "20-Views" / "progress.html"))


class T05_Onboarding(WFTest):
    def test_new_project_without_touching_user_level_files(self):
        watched = [CLAUDE_HOME / "CLAUDE.md", CLAUDE_HOME / "wirat-workflow"] + [CLAUDE_HOME / "skills" / s for s in SKILLS]
        before = [sha(p) if p.is_file() else tree_hash(p) for p in watched]
        self.wf("new-workspace", "hr-leave", "--name", "HR Leave", "--repo", "C:/repos/hr-leave")
        after = [sha(p) if p.is_file() else tree_hash(p) for p in watched]
        self.assertEqual(before, after)
        ws = self.proj("hr-leave")
        self.assertEqual(sorted(p.name for p in (ws / "20-Views").iterdir()), ["backlog.html", "journey.html", "progress.html"])
        self.assertIn("hr-leave", (ws / "00-Project" / "project-overview.md").read_text(encoding="utf-8"))
        self.assertIn("hr-leave", [p["slug"] for p in json.loads((self.ws / "Portfolio" / "projects.json").read_text(encoding="utf-8"))["projects"]])
        self.assertTrue((ws / "10-Data" / "data.js").exists())
        self.wf("new-workspace", "hr-leave", code=2)  # never overwrite

    def test_dry_run_writes_nothing(self):
        h = tree_hash(self.ws)
        r = self.wf("--dry-run", "new-workspace", "x-proj")
        self.assertIn("[dry-run]", r.stdout)
        self.wf("--dry-run", "accept", "TASK-016", "--actual-days", "4", "--variance", "x")
        self.assertEqual(h, tree_hash(self.ws))


class T06_DeliveryMetrics(WFTest):
    def test_acceptance_creates_metric_record(self):
        mp = self.ws / "Portfolio" / "delivery-metrics.json"
        n0 = len(json.loads(mp.read_text(encoding="utf-8"))["records"])
        self.wf("accept", "TASK-016", "--actual-days", "4", "--accepted", "2026-11-01", "--accepted-by", "ploy",
                "--variance", "User ขอ validation เพิ่มหลังประชุม")
        recs = json.loads(mp.read_text(encoding="utf-8"))["records"]
        self.assertEqual(len(recs), n0 + 1)
        r = recs[-1]
        for k, v in {"task_id": "TASK-016", "project": "it-service-request", "module": "request", "task_type": "backend-feature",
                     "complexity": "medium", "estimate_days": 3, "actual_days": 4.0, "started": "2026-10-22",
                     "uat_sent": "2026-10-29", "user_accepted": "2026-11-01", "status": "accepted"}.items():
            self.assertEqual(r[k], v, k)
        self.assertTrue(r["variance_reason"])
        self.assertEqual(self.task("it-service-request", "TASK-016")["status"], "accepted")
        jr = json.loads((self.proj("it-service-request") / "10-Data" / "journey.json").read_text(encoding="utf-8"))
        self.assertTrue(any(e.get("tasks") == ["TASK-016"] and e["type"] == "acceptance" for e in jr["recent"]))
        ptr = json.loads((self.ws / "Portfolio" / "latest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(ptr["delivery-metrics.json"]["revision"], 2)  # original kept as revision 1
        self.wf("accept", "TASK-016", "--actual-days", "4", "--variance", "x", code=2)  # duplicate refused

    def test_variance_reason_required_and_status_accepted_only_via_accept(self):
        self.wf("accept", "TASK-016", "--actual-days", "5", code=2)
        self.wf("update-task", "TASK-016", "--set", "status=accepted", code=3)


class T07_Estimate(WFTest):
    def est(self, *a):
        return json.loads(self.wf("estimate", *a).stdout)

    def test_history_used_when_enough_data(self):
        e = self.est("--type", "backend-feature", "--complexity", "medium", "--base-days", "3", "--project", "approval-system")
        self.assertEqual(e["history"]["exact_matches"], 3)
        self.assertIsNotNone(e["history_adjustment"])
        self.assertGreater(e["estimate_days"], 3)  # history says we under-estimate
        self.assertIn(e["confidence"], ("medium", "high"))
        ci = e["capacity_impact"]
        self.assertLess(ci["available_hours_this_week_after"], ci["available_hours_this_week_before"] + 0.01)
        self.assertGreater(ci["queued_hours_before"], 0)  # cross-project workload considered

    def test_single_data_point_not_generalised(self):
        e = self.est("--type", "report-export", "--complexity", "medium", "--base-days", "2.5")
        self.assertEqual(e["history"]["exact_matches"], 1)
        self.assertIsNone(e["history_adjustment"])
        self.assertEqual(e["estimate_days"], 2.5)
        self.assertEqual(e["confidence"], "low")
        self.assertIn("NOT used", e["note"])


class T08_PlanChange(WFTest):
    SPEC = {
        "title": "Move TASK-018 to next week",
        "reason": "รอ ploy ยืนยัน template (OQ-003) และสัปดาห์นี้ overcommit",
        "changes": [{"op": "set", "task": "TASK-018", "field": "due", "to": "2026-11-13"}],
        "alternatives": [
            {"title": "เลื่อน TASK-018 ไป 11-13", "description": "...", "benefits": "ลด overcommit", "drawbacks": "รายงานช้า 1 สัปดาห์",
             "timeline_impact": "+5 วัน", "capacity_impact": "-8h สัปดาห์นี้", "stakeholder_impact": "ploy", "risk": "ต่ำ"},
            {"title": "คงวันเดิม ทำ OT", "description": "...", "benefits": "ตรงเวลา", "drawbacks": "เหนื่อย", "timeline_impact": "0",
             "capacity_impact": "+8h OT", "stakeholder_impact": "ไม่มี", "risk": "สูง"},
        ],
        "impacts": {"timeline": "TASK-020 ยังทัน", "capacity": "ลด 8h", "stakeholders": "แจ้ง ploy", "other_projects": "ไม่มี"},
    }

    def propose(self, spec=None):
        out = self.wf("propose-change", "--input", self.json_file("pcp.json", spec or self.SPEC)).stdout.strip()
        return Path(out)

    def test_plan_fields_cannot_be_edited_directly(self):
        before = sha(self.proj("it-service-request") / "10-Data" / "backlog.json")
        for kv in ("due=2026-11-13", "priority=P1", "estimate_days=5", "owner=arthit"):
            self.wf("update-task", "TASK-018", "--set", kv, code=3)
        self.assertEqual(before, sha(self.proj("it-service-request") / "10-Data" / "backlog.json"))

    def test_change_requires_wirat_approval(self):
        pfile = self.propose()
        self.assertIn("status: proposed", pfile.read_text(encoding="utf-8"))
        self.assertIn("Alternatives (most → least recommended)", pfile.read_text(encoding="utf-8"))
        original = sha(pfile)
        self.wf("apply-change", "PCP-001", code=3)
        self.assertEqual(self.task("it-service-request", "TASK-018")["due"], "2026-11-06")
        self.wf("approve-change", "PCP-001", "--by", "ploy", code=3)
        self.wf("approve-change", "PCP-001", "--by", "wirat", "--alternative", "1", "--note", "ok ข้อ 1")
        self.wf("apply-change", "PCP-001")
        self.assertEqual(self.task("it-service-request", "TASK-018")["due"], "2026-11-13")
        self.assertEqual(sha(pfile), original, "original proposal must stay untouched")
        revs = sorted((self.ws / "Portfolio" / "plan-changes").glob("*PCP-001*"))
        self.assertEqual(len(revs), 3)  # proposed, approved, applied
        self.assertIn("applied_at", revs[-1].read_text(encoding="utf-8"))
        decs = list((self.proj("it-service-request") / "00-Project" / "decisions").glob("*_DEC-*plan-change-pcp-001*"))
        self.assertEqual(len(decs), 1)
        jr = json.loads((self.proj("it-service-request") / "10-Data" / "journey.json").read_text(encoding="utf-8"))
        self.assertTrue(any(e.get("plan_change") == "PCP-001" for e in jr["recent"]))
        self.assertTrue(list((self.proj("it-service-request") / "10-Data" / "revisions").glob("*_backlog.json")))
        self.assertIn("ploy", decs[0].read_text(encoding="utf-8"))  # stakeholders linked from the tasks
        self.assertEqual(decs[0].read_text(encoding="utf-8").count("  - TASK-018"), 1)  # no duplicate ids
        self.wf("apply-change", "PCP-001", code=2)  # not twice

    def test_proposed_task_needs_activate_proposal(self):
        p = self.proj("it-service-request") / "10-Data" / "backlog.json"
        spec = json.loads(json.dumps(self.SPEC))
        spec["title"] = "Add proposed task"
        spec["changes"] = [{"op": "add_task", "project": "it-service-request", "task": {
            "title": "Draft idea", "module": "report", "owner": "wirat", "priority": "P3", "due": "2026-11-27", "status": "proposed",
            "estimate_days": 1, "dependencies": [], "stakeholders": ["ploy"], "definition_of_done": "feature"}}]
        self.propose(spec)
        self.wf("approve-change", "PCP-001", "--by", "wirat")
        self.wf("apply-change", "PCP-001")
        tid = next(t["id"] for t in self.backlog("it-service-request")["tasks"] if t["title"] == "Draft idea")
        self.wf("update-task", tid, "--set", "status=todo", code=3)       # loophole closed
        self.wf("update-task", tid, "--set", "status=cancelled")          # dropping unplanned scope is fine
        spec2 = json.loads(json.dumps(self.SPEC))
        spec2["changes"] = [{"op": "activate", "task": tid}]
        self.wf("propose-change", "--input", self.json_file("act.json", spec2), code=2)  # only proposed tasks
        self.assertTrue(p.exists())

    def test_activate_brings_proposed_task_into_plan(self):
        bl_p = self.proj("food-delivery") / "10-Data" / "backlog.json"
        bl = json.loads(bl_p.read_text(encoding="utf-8"))
        bl["tasks"][-1]["status"] = "proposed"
        tid = bl["tasks"][-1]["id"]
        bl_p.write_text(json.dumps(bl), encoding="utf-8")
        spec = json.loads(json.dumps(self.SPEC))
        spec["changes"] = [{"op": "activate", "task": tid}]
        self.propose(spec)
        self.assertEqual(self.task("food-delivery", tid)["status"], "proposed")
        self.wf("approve-change", "PCP-001", "--by", "wirat")
        self.wf("apply-change", "PCP-001")
        self.assertEqual(self.task("food-delivery", tid)["status"], "todo")

    def test_rejected_and_stale_proposals_do_not_apply(self):
        self.propose()
        self.wf("reject-change", "PCP-001", "--note", "ไม่เลื่อน")
        self.wf("apply-change", "PCP-001", code=3)
        # stale: two proposals on the same field, the second becomes stale after the first is applied
        self.propose()  # PCP-002
        spec = json.loads(json.dumps(self.SPEC))
        spec["changes"][0]["to"] = "2026-11-20"
        self.propose(spec)  # PCP-003
        for pid in ("PCP-002", "PCP-003"):
            self.wf("approve-change", pid, "--by", "wirat")
        self.wf("apply-change", "PCP-002")
        self.wf("apply-change", "PCP-003", code=4)
        self.assertEqual(self.task("it-service-request", "TASK-018")["due"], "2026-11-13")

    def test_add_task_through_proposal(self):
        spec = json.loads(json.dumps(self.SPEC))
        spec["title"] = "Add PDF export"
        spec["changes"] = [{"op": "add_task", "project": "it-service-request", "task": {
            "title": "Export SLA report as PDF", "module": "report", "owner": "wirat", "priority": "P2", "due": "2026-11-20",
            "estimate_days": 2.5, "dependencies": ["TASK-018"], "stakeholders": ["ploy"], "definition_of_done": "feature",
            "task_type": "report-export", "complexity": "medium"}}]
        self.propose(spec)
        self.assertFalse(any(t["title"] == "Export SLA report as PDF" for t in self.backlog("it-service-request")["tasks"]))
        self.wf("approve-change", "PCP-001", "--by", "wirat")
        self.wf("apply-change", "PCP-001")
        new = [t for t in self.backlog("it-service-request")["tasks"] if t["title"] == "Export SLA report as PDF"]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["id"], "TASK-029")
        self.wf("validate")


class T09_ExecutionPlan(WFTest):
    GOOD = {"agents": [
        {"name": "coordinator", "role": "coordinator", "files": []},
        {"name": "api", "role": "worker", "worktree": "../wt-api", "tasks": ["TASK-014"], "files": ["src/sla/calc.ts"], "tests": ["src/sla/calc.test.ts"]},
        {"name": "ui", "role": "worker", "worktree": "../wt-ui", "tasks": ["TASK-019"], "files": ["src/ui/Sla.tsx"], "tests": ["src/ui/Sla.test.tsx"]}],
        "contracts": ["src/types/sla.ts"], "merge_order": ["contract", "api", "ui"]}

    def plan(self, obj):
        tpl = (WF_HOME / "templates" / "artifacts" / "execution-plan.md").read_text(encoding="utf-8")
        body = re.sub(r"```json.*?```", "```json\n" + json.dumps(obj) + "\n```", tpl, flags=re.S)
        p = self.tmp / "plan.md"
        p.write_text(body, encoding="utf-8")
        return p

    def test_template_and_good_plan_pass(self):
        self.wf("check-exec-plan", WF_HOME / "templates" / "artifacts" / "execution-plan.md")
        self.assertIn("PASS", self.wf("check-exec-plan", self.plan(self.GOOD)).stdout)

    def test_unsafe_plans_fail(self):
        def variant(fn):
            o = json.loads(json.dumps(self.GOOD))
            fn(o)
            return self.plan(o)
        bad = {
            "same file twice": lambda o: o["agents"][2]["files"].append("src/sla/calc.ts"),
            "no worktree": lambda o: o["agents"][1].pop("worktree"),
            "no contracts": lambda o: o.update(contracts=[]),
            "coordinator edits code": lambda o: o["agents"][0]["files"].append("src/x.ts"),
            "no merge order": lambda o: o.update(merge_order=[]),
        }
        for name, fn in bad.items():
            r = self.wf("check-exec-plan", variant(fn), code=1)
            self.assertIn("FAIL", r.stdout, name)
        p = self.tmp / "nosections.md"
        p.write_text("```json\n" + json.dumps(self.GOOD) + "\n```", encoding="utf-8")
        self.wf("check-exec-plan", p, code=1)


class T10_Revisions(WFTest):
    def test_revise_never_overwrites(self):
        inv = self.proj("food-delivery") / "00-Project" / "feature-inventory.md"
        h = sha(inv)
        r1 = Path(self.wf("revise", inv).stdout.strip())
        r2 = Path(self.wf("revise", inv).stdout.strip())
        self.assertEqual(sha(inv), h)
        self.assertRegex(r1.name, r"^\d{8}-\d{6}(-\d+)?_feature-inventory\.md$")
        self.assertIn("revision: 3", r2.read_text(encoding="utf-8"))
        self.assertIn(f"supersedes: {r1.name}", r2.read_text(encoding="utf-8"))
        latest = json.loads((inv.parent / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["feature-inventory.md"]["file"], r2.name)

    def test_uat_revisions(self):
        uat = self.proj("it-service-request") / "00-Project" / "uat"
        first = sorted(uat.glob("*.xlsx"))
        self.assertEqual(len(first), 1)
        h = sha(first[0])
        spec = {"note": "round 2", "add": [{"module": "sla", "scenario": "P1 เกิน 4 ชม. แสดงสีแดง", "preconditions": "REQ P1",
                "steps": ["เปิด dashboard"], "expected": "แถวสีแดง", "tester": "ploy", "tasks": ["TASK-014"], "stakeholders": ["ploy"]}],
                "update": [{"uat_id": "UAT-003", "status": "Pass", "actual": "ได้หลังตั้ง LDAP group"}]}
        out = json.loads(self.wf("uat-revise", "it-service-request", "--input", self.json_file("uat.json", spec)).stdout)
        self.assertEqual(sha(first[0]), h, "original UAT workbook untouched")
        self.assertRegex(Path(out["file"]).name, r"^\d{8}-\d{6}(-\d+)?_UAT_it-service-request_r02\.xlsx$")
        latest = json.loads((uat / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["file"], Path(out["file"]).name)
        self.assertEqual(latest["summary"], {"Pass": 3, "Fail": 0, "Blocked": 0, "Not Run": 1, "total": 4})
        import openpyxl
        ws = openpyxl.load_workbook(out["file"])["UAT"]
        hdr = [c.value for c in ws[1]]
        for col in ("UAT ID", "Module", "Scenario", "Preconditions", "Steps", "Expected Result", "Actual Result",
                    "Status", "Tester", "Remarks", "Task IDs", "Stakeholders"):
            self.assertIn(col, hdr)
        bad = {"update": [{"uat_id": "UAT-001", "status": "OK"}]}
        self.wf("uat-revise", "it-service-request", "--input", self.json_file("bad.json", bad), code=2)

    def test_json_feeds_are_immutable_revisions(self):
        data = self.proj("it-service-request") / "10-Data"
        self.wf("update-task", "TASK-014", "--set", "progress=90")
        ptr = json.loads((data / "latest.json").read_text(encoding="utf-8"))["backlog.json"]
        revs = sorted((data / "revisions").glob("*_backlog.json"))
        hashes = {p.name: sha(p) for p in revs}
        cur = data / ptr["file"]
        self.assertRegex(cur.name, r"^\d{8}-\d{6}(-\d+)?_backlog\.json$")
        self.assertEqual(json.loads(cur.read_text(encoding="utf-8")), self.backlog("it-service-request"))  # mirror == latest
        first = json.loads((data / ptr["supersedes"]).read_text(encoding="utf-8")) if ptr["revision"] == 2 else None
        if first:
            self.assertEqual(next(t for t in first["tasks"] if t["id"] == "TASK-014")["progress"], 70)
        self.wf("update-task", "TASK-014", "--set", "progress=95")
        for name, h in hashes.items():
            self.assertEqual(sha(data / "revisions" / name), h, f"revision {name} was modified")
        ptr2 = json.loads((data / "latest.json").read_text(encoding="utf-8"))["backlog.json"]
        self.assertEqual(ptr2["revision"], ptr["revision"] + 1)
        self.assertEqual(ptr2["supersedes"], ptr["file"])

    def test_readers_follow_pointer_and_validate_flags_hand_edits(self):
        data = self.proj("it-service-request") / "10-Data"
        self.wf("update-task", "TASK-014", "--set", "progress=90")
        bl = json.loads((data / "backlog.json").read_text(encoding="utf-8"))
        bl["tasks"][0]["title"] = "edited by hand"
        (data / "backlog.json").write_text(json.dumps(bl), encoding="utf-8")
        self.assertIn("differs from its latest revision", self.wf("validate", code=1).stdout)
        r = json.loads(self.wf("progress", "it-service-request").stdout)
        self.assertEqual(r["project"], "it-service-request")

    def test_stakeholder_revision_is_not_duplicated(self):
        f = self.proj("it-service-request") / "00-Project" / "stakeholders" / "ploy.md"
        self.wf("revise", f)
        self.wf("progress", "--all", "--write")
        prog = json.loads((self.proj("it-service-request") / "10-Data" / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in prog["stakeholders"]].count("ploy"), 1)
        self.assertRegex([s["file"] for s in prog["stakeholders"] if s["id"] == "ploy"][0], r"^\d{8}-\d{6}")

    def test_uat_revision_discovers_existing_workbook_without_pointer(self):
        import openpyxl
        uat = self.proj("approval-system") / "00-Project" / "uat"
        rev01 = uat / "20261101-1200-uat-approval-system-rev01.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "UAT"
        ws.append(["uat id", "Module", "Scenario", "Steps", "Expected result", "Status", "Tester", "Extra col"])
        ws.append(["UAT-007", "approval", "step 1", "approve", "step 2", "Pass", "dao", "x"])
        ws.append(["UAT-008", "approval", "reject", "reject", "rejected", None, "dao", "y"])
        wb.save(rev01)
        h = sha(rev01)
        spec = {"add": [{"module": "approval", "scenario": "step 2 fixed approver", "steps": ["approve"], "expected": "approved",
                         "tester": "somchai", "tasks": ["TASK-023"], "stakeholders": ["somchai"]}]}
        out = json.loads(self.wf("uat-revise", "approval-system", "--input", self.json_file("u.json", spec)).stdout)
        self.assertEqual(sha(rev01), h)
        self.assertEqual(out["revision"], 2)
        self.assertEqual(out["supersedes"], rev01.name)
        self.assertEqual(out["copied_rows"], 2)
        self.assertEqual(out["dropped_columns"], ["Extra col"])
        self.assertRegex(Path(out["file"]).name, r"^\d{8}-\d{6}(-\d+)?_UAT_approval-system_r02\.xlsx$")
        ids = [r[0] for r in openpyxl.load_workbook(out["file"])["UAT"].iter_rows(min_row=2, values_only=True)]
        self.assertEqual(ids, ["UAT-007", "UAT-008", "UAT-009"])  # no id collision with existing rows
        self.assertEqual(json.loads((uat / "latest.json").read_text(encoding="utf-8"))["supersedes"], rev01.name)


class T11_StakeholderAndUsage(WFTest):
    def test_stakeholder_view_shows_blocker_impact(self):
        v = json.loads(self.wf("stakeholder", "ton").stdout)
        imp = v["impact_on_wirat"]
        self.assertEqual([t["id"] for t in v["waiting_on_them"]], ["TASK-004"])
        self.assertEqual(imp["blocked_tasks"], ["TASK-004"])
        self.assertGreater(imp["blocked_hours"], 0)
        self.assertIn("TASK-005", imp["downstream_tasks"])  # rider map depends on the payment webhook
        self.assertIn("TASK-008", imp["downstream_tasks"])
        self.assertGreater(imp["hours_at_risk"], imp["blocked_hours"])
        self.assertEqual(imp["earliest_affected_due"], "2026-11-04")
        body = (self.ws / "Portfolio" / "portfolio-data.js").read_text(encoding="utf-8")
        data = json.loads(body[body.index("=") + 1:].rstrip().rstrip(";"))
        self.assertIn("ton", data["stakeholder_impact"])
        self.assertNotIn("wirat", data["stakeholder_impact"])

    def test_stakeholder_view_cross_project_questions(self):
        v = json.loads(self.wf("stakeholder", "ploy").stdout)
        self.assertIn("OQ-003", [q["id"] for q in v["open_questions"]])
        self.assertIn("TASK-013", [t["id"] for t in v["owned"]])

    def test_skill_usage_last_used_and_ranking(self):
        self.wf("log-skill", "build-loop", "--project", "food-delivery")
        u = json.loads((self.ws / "Portfolio" / "skill-usage.json").read_text(encoding="utf-8"))
        self.assertEqual(u["counts"]["build-loop"], 8)
        self.assertEqual(u["skills"]["build-loop"]["count"], 8)
        self.assertTrue(u["skills"]["build-loop"]["last_used"])
        rank = json.loads(self.wf("skill-rank", "--candidates", "uat-manager,progress-view,quality-gate").stdout)
        self.assertEqual([r["skill"] for r in rank], ["progress-view", "uat-manager", "quality-gate"])

    def test_progress_html_shows_impact_and_last_used(self):
        html = (self.proj("food-delivery") / "20-Views" / "progress.html").read_text(encoding="utf-8")
        self.assertIn("stakeholder_impact", html)
        self.assertIn("last_used", html)


class T12_QuestionJourneyDecision(WFTest):
    def test_question_lifecycle(self):
        self.wf("add-question", "approval-system", "--question", "email or in-app?", "--owner", "somchai", code=2)
        q = json.loads(self.wf("add-question", "approval-system", "--question", "email or in-app?", "--owner", "somchai",
                               "--target-meeting", "MTG-006", "--tasks", "TASK-026", "--options", "email|in-app|both").stdout)
        self.assertEqual(q["id"], "OQ-006")
        self.assertEqual(q["options_presented"], ["email", "in-app", "both"])
        self.assertIn("OQ-006", self.task("approval-system", "TASK-026")["open_questions"])
        self.wf("update-question", "OQ-006", "--owner", "", code=2)
        self.wf("update-question", "OQ-006", "--answer", "email", "--decision", "DEC-004")
        q2 = next(x for x in self.backlog("approval-system")["open_questions"] if x["id"] == "OQ-006")
        self.assertEqual((q2["status"], q2["answer"]), ("answered", "email"))
        self.assertTrue(list((self.proj("approval-system") / "10-Data" / "revisions").glob("*_backlog.json")))

    def test_decision_new_updates_journey(self):
        out = json.loads(self.wf("decision-new", "approval-system", "--title", "Fixed second approver", "--context", "OQ",
                                 "--decision", "fixed", "--alternatives", "fixed|role|per-document", "--meetings", "MTG-005",
                                 "--modules", "approval", "--tasks", "TASK-023", "--stakeholders", "somchai",
                                 "--decided-by", "wirat").stdout)
        self.assertEqual(out["id"], "DEC-004")
        text = Path(out["file"]).read_text(encoding="utf-8")
        self.assertIn("1. fixed", text)
        self.assertIn("MTG-005", text)
        jr = json.loads((self.proj("approval-system") / "10-Data" / "journey.json").read_text(encoding="utf-8"))
        self.assertEqual(jr["recent"][-1]["decision"], "DEC-004")
        self.assertEqual(jr["recent"][-1]["meeting"], "MTG-005")
        self.assertTrue(jr["recent"][-1]["ref"].startswith("00-Project/decisions/"))  # long text lives in the record, not the journey
        ev = next(m for m in jr["modules"] if m["module"] == "approval")["current"]
        self.assertEqual((ev["decision"], ev["task"]), ("DEC-004", "TASK-023"))

    def test_journey_add_with_module_events_is_one_revision(self):
        data = self.proj("food-delivery") / "10-Data"
        self.wf("journey-add", "food-delivery", "--type", "milestone", "--title", "Payment sandbox ready",
                "--modules", "payment", "--module-event", "payment|unblocked|sandbox key received",
                "--module-event", "order|ready|can test end-to-end")
        ptr = json.loads((data / "latest.json").read_text(encoding="utf-8"))["journey.json"]
        jr = json.loads((data / "journey.json").read_text(encoding="utf-8"))
        self.assertEqual(next(m for m in jr["modules"] if m["module"] == "payment")["current"]["stage"], "unblocked")
        files = sorted((data / "journey-events").rglob("EV-*.json"))
        last = json.loads(files[-1].read_text(encoding="utf-8"))
        self.assertEqual([m["module"] for m in last["module_events"]], ["payment", "order"])  # both module events in ONE event file
        before = ptr["revision"]
        self.wf("journey-add", "food-delivery", "--type", "change", "--title", "again")
        self.assertEqual(json.loads((data / "latest.json").read_text(encoding="utf-8"))["journey.json"]["revision"], before + 1)



def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def make_repo(path, remote=None):
    Path(path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True, capture_output=True)
    if remote:
        _git(path, "remote", "add", "origin", remote)
    return Path(path)


class MoreWFTest(WFTest):
    def wfmod(self):
        """Import wf.py in-process (same env as the subprocess calls) for bulk operations."""
        import importlib.util
        env = {"WF_WORKSPACE": str(self.ws), "WF_TODAY": "2026-11-01", "WF_LOCAL_CONFIG": str(self.local)}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in old.items()])
        spec = importlib.util.spec_from_file_location(f"wf_{id(self)}", WF)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def local_json(self):
        return json.loads(self.local.read_text(encoding="utf-8")) if self.local.exists() else {}


class T13_JourneyScale(MoreWFTest):
    def fill(self, n=400):
        m = self.wfmod()
        long = "x" * 500
        for i in range(n):
            m.journey_append("food-delivery", {"date": f"2026-{(i % 3) + 8:02d}-{(i % 27) + 1:02d}", "type": "change",
                                               "title": f"event {i}", "summary": long, "modules": ["order" if i % 2 else "payment"]},
                             [{"module": "order" if i % 2 else "payment", "stage": f"s{i}", "change": f"step {i}"}])
        m.bundle(quiet=True)
        return m

    def test_digest_and_bundles_stay_small_however_long_the_journey(self):
        self.fill(400)
        data = self.proj("food-delivery") / "10-Data"
        dg = json.loads((data / "journey.json").read_text(encoding="utf-8"))
        self.assertEqual(dg["version"], 2)
        self.assertEqual(dg["total_events"], 404)  # 4 seeded + 400
        self.assertEqual(len(dg["recent"]), 15)
        self.assertLess(len((data / "journey.json").read_bytes()), 14000)
        self.assertTrue(all(len(e.get("summary", "")) <= 161 for e in dg["recent"]))
        self.assertLess(len((data / "data.js").read_bytes()), 90000)  # was O(history); now only the digest
        portfolio = (self.ws / "Portfolio" / "portfolio-data.js").read_bytes()
        self.assertLess(len(portfolio), 150000)
        self.assertTrue(list((data / "journey-data").glob("2026-*.js")))  # history is loaded lazily, per month
        for rev in (data / "revisions").glob("*_journey.json"):
            self.assertLess(len(rev.read_bytes()), 14000)  # no revision ever copies the whole history

    def test_events_are_immutable_files(self):
        m = self.fill(5)
        first = sorted((self.proj("food-delivery") / "10-Data" / "journey-events").rglob("EV-*.json"))[0]
        h = sha(first)
        for i in range(5):
            m.journey_append("food-delivery", {"type": "change", "title": f"more {i}"})
        self.assertEqual(sha(first), h)

    def test_queries_are_windowed_and_capped(self):
        self.fill(400)
        out = self.wf("journey", "food-delivery").stdout
        self.assertIn("showing 15 of 404", out)
        self.assertLess(len(out), 6500)
        big = self.wf("journey", "food-delivery", "--limit", "400", "--full").stdout
        self.assertLessEqual(len(big), 6500)
        self.assertIn("more line(s) not shown", big)
        self.assertIn("event 77", self.wf("journey", "food-delivery", "--search", "event 77").stdout)
        mod = self.wf("journey", "food-delivery", "--module", "payment", "--limit", "5").stdout
        self.assertIn("evolution step(s)", mod)
        self.assertEqual(len([ln for ln in mod.splitlines() if ln and not ln.startswith("#")]), 5)
        dig = self.wf("journey", "food-delivery", "--digest").stdout
        self.assertLess(len(dig), 14000)

    def test_long_text_is_refused_not_stored(self):
        r = self.wf("journey-add", "food-delivery", "--type", "meeting", "--title", "t", "--summary", "y" * 700, code=2)
        self.assertIn("--ref", r.stderr)
        self.wf("journey-add", "food-delivery", "--type", "meeting", "--title", "t", "--summary", "short",
                "--ref", "00-Project/meetings/20261020-100000_MTG-001_notes.md")
        self.wf("journey-add", "food-delivery", "--type", "meeting", "--title", "z" * 200, code=2)

    def test_legacy_journey_is_migrated_without_loss(self):
        out = self.wf("journey", "it-service-request", "--limit", "50").stdout
        self.assertIn("MTG-003 progress meeting", out)
        self.assertIn("DEC-002", out)
        mod = self.wf("journey", "it-service-request", "--module", "request").stdout
        self.assertIn("accepted: request API", mod)
        self.assertIn("idempotent", "idempotent" if "already v2" in self.wf("journey-compact", "it-service-request").stdout else "")
        revs = list((self.proj("it-service-request") / "10-Data" / "revisions").glob("*_journey.json"))
        self.assertTrue(any("timeline" in json.loads(r.read_text(encoding="utf-8")) for r in revs))  # single-file original kept as a revision

    def test_digest_rebuild_matches_incremental(self):
        m = self.fill(30)
        data = self.proj("food-delivery") / "10-Data" / "journey.json"
        inc = json.loads(data.read_text(encoding="utf-8"))
        self.wf("journey-compact", "food-delivery", "--rebuild")
        reb = json.loads(data.read_text(encoding="utf-8"))
        for k in ("total_events", "by_type", "periods", "recent"):
            self.assertEqual(inc[k], reb[k], k)
        self.assertEqual([(x["module"], x["event_count"], x["current"]["stage"]) for x in inc["modules"]],
                         [(x["module"], x["event_count"], x["current"]["stage"]) for x in reb["modules"]])

    def test_same_second_events_keep_order(self):
        m = self.wfmod()
        for i in range(25):
            m.journey_append("food-delivery", {"date": "2026-11-01", "type": "change", "title": f"burst {i:02d}"})
        titles = [e["title"] for e in m.journey_events("food-delivery") if e["title"].startswith("burst")]
        self.assertEqual(titles, [f"burst {i:02d}" for i in range(25)])


class T14_ProjectLocations(MoreWFTest):
    def test_map_unmap_which_and_no_absolute_paths_in_shared_data(self):
        repo = make_repo(self.tmp / "code" / "my-fd", "git@github.com:acme/food-delivery.git")
        (repo / "src").mkdir()
        self.wf("projects", "map", "food-delivery", "--repo", repo)
        self.assertEqual(self.local_json()["projects"]["food-delivery"]["repo"], str(repo).replace("\\", "/"))
        rows = {r["slug"]: r for r in json.loads(self.wf("projects", "list", "--json").stdout)}
        r = rows["food-delivery"]
        self.assertTrue(r["repo_exists"])
        self.assertEqual(r["branch"], "main")
        self.assertEqual(r["registry_remote"], "git@github.com:acme/food-delivery.git")
        self.assertEqual(self.wf("projects", "which", repo / "src").stdout.strip(), "food-delivery")
        # portable data must never carry this machine's paths
        needle = str(self.tmp).replace("\\", "/")
        for f in list((self.ws / "Portfolio").rglob("*.json")) + list((self.ws / "Projects").rglob("*.json")):
            if "plan-changes" in f.parts:
                continue
            self.assertNotIn(needle, f.read_text(encoding="utf-8").replace("\\\\", "/"), f"{f} contains a local path")
        self.wf("projects", "unmap", "food-delivery", "--repo")
        self.assertNotIn("repo", self.local_json().get("projects", {}).get("food-delivery", {}))
        self.assertTrue(repo.is_dir())  # unmap never deletes
        self.wf("projects", "which", repo / "src", code=1)

    def test_map_validates_and_warns_on_other_remote(self):
        self.wf("projects", "map", "food-delivery", "--repo", self.tmp / "nope", code=2)
        self.wf("projects", "map", "ghost", "--repo", self.tmp, code=2)
        a = make_repo(self.tmp / "a", "https://github.com/acme/fd.git")
        b = make_repo(self.tmp / "b", "https://github.com/other/different.git")
        self.wf("projects", "map", "food-delivery", "--repo", a)
        r = self.wf("projects", "map", "food-delivery", "--repo", b)
        self.assertIn("WARN", r.stdout)

    def test_check_distinguishes_warnings_from_errors(self):
        r = self.wf("projects", "check")  # nothing mapped -> warnings only
        self.assertIn("source folder not mapped", r.stdout)
        self.wf("projects", "map", "food-delivery", "--repo", self.tmp / "gone", "--force")
        r = self.wf("projects", "check", code=1)
        self.assertIn("mapped repo folder is missing", r.stdout)

    def test_workspace_in_another_folder(self):
        where = self.tmp / "elsewhere" / "ws-hr"
        self.wf("new-workspace", "hr-leave", "--name", "HR Leave", "--at", where)
        self.assertTrue((where / "10-Data" / "backlog.json").exists())
        self.assertFalse((self.ws / "Projects" / "hr-leave").exists())
        self.assertEqual(self.local_json()["projects"]["hr-leave"]["workspace"], str(where).replace("\\", "/"))
        self.assertIn("hr-leave", [r["slug"] for r in json.loads(self.wf("projects", "list", "--json").stdout)])
        self.assertTrue((where / "10-Data" / "portfolio-data.js").exists())  # views find the portfolio bundle without ../../../../
        self.wf("journey-add", "hr-leave", "--type", "milestone", "--title", "kickoff")
        self.assertIn("kickoff", self.wf("journey", "hr-leave").stdout)
        self.wf("validate")

    def test_add_existing_workspace_from_any_folder(self):
        src = self.proj("approval-system")
        moved = self.tmp / "synced-from-other-pc" / "approval"
        shutil.copytree(src, moved)
        shutil.rmtree(self.ws / "Projects" / "approval-system")  # this machine does not have it in the standard place
        self.assertNotIn("approval-system", self.wf("tasks", "--project", "approval-system").stdout.split("showing")[0] or "")
        self.wf("projects", "check", code=1)
        self.wf("projects", "add", "approval-system", "--workspace", moved)
        self.assertIn("TASK-023", self.wf("tasks", "--project", "approval-system", "--status", "all").stdout)
        self.wf("projects", "check")
        self.wf("projects", "add", "x", "--workspace", self.tmp, code=2)  # not a ProjectWorkspace

    def test_remove_and_restore_never_delete(self):
        self.wf("projects", "remove", "approval-system", code=3)  # has open tasks: needs --yes
        self.wf("projects", "remove", "approval-system", "--yes")
        self.assertTrue((self.proj("approval-system") / "10-Data" / "backlog.json").exists())
        self.assertNotIn("approval-system", self.wf("tasks", "--status", "all", "--limit", "100").stdout)
        self.assertEqual(self.wf("capacity").returncode, 0)
        self.wf("projects", "restore", "approval-system")
        self.assertIn("approval-system", self.wf("tasks", "--status", "all", "--limit", "100").stdout)

    def test_scan_matches_by_remote_then_folder_name(self):
        a = make_repo(self.tmp / "dev" / "client" / "renamed-folder", "https://github.com/acme/food-delivery.git")
        self.wf("projects", "map", "food-delivery", "--repo", a)
        self.wf("projects", "unmap", "food-delivery")
        make_repo(self.tmp / "other-pc" / "work" / "moved-repo", "git@github.com:acme/food-delivery.git")  # same remote, ssh spelling
        make_repo(self.tmp / "other-pc" / "work" / "it-service-request")                                   # matched by folder name
        r = self.wf("projects", "scan", self.tmp / "other-pc")
        self.assertIn("food-delivery", r.stdout)
        self.assertIn("matched by remote", r.stdout)
        self.assertIn("matched by folder name", r.stdout)
        self.assertNotIn("repo", self.local_json().get("projects", {}).get("food-delivery", {}))  # scan alone changes nothing
        self.wf("projects", "scan", self.tmp / "other-pc", "--apply")
        mapped = self.local_json()["projects"]
        self.assertTrue(mapped["food-delivery"]["repo"].endswith("moved-repo"))
        self.assertTrue(mapped["it-service-request"]["repo"].endswith("it-service-request"))

    def test_migrate_moves_old_absolute_paths_out_of_shared_data(self):
        self.wf("projects", "unmap", "food-delivery")
        m = self.wfmod()
        reg = m.registry()
        old_repo = make_repo(self.tmp / "old" / "fd")
        ent = next(p for p in reg["projects"] if p["slug"] == "food-delivery")
        ent["repo_path"] = str(old_repo)
        m.W.json(m.portfolio() / "projects.json", reg)
        bl = m.load_backlog("food-delivery")
        bl["repo_path"] = str(old_repo)
        m.W.json(m.data_path("food-delivery", "backlog.json"), bl)
        self.wf("projects", "migrate")
        self.assertNotIn("repo_path", json.dumps(m.registry()))
        self.assertNotIn("repo_path", json.dumps(m.load_backlog("food-delivery")))
        self.assertEqual(self.local_json()["projects"]["food-delivery"]["repo"], str(old_repo).replace("\\", "/"))
        self.assertIn("nothing to migrate", self.wf("projects", "migrate").stdout)

    def test_setup_on_a_new_machine(self):
        new_local = self.tmp / "other-machine-local.json"
        env = dict(os.environ, WF_LOCAL_CONFIG=str(new_local), PYTHONIOENCODING="utf-8")
        env.pop("WF_WORKSPACE", None)
        def run(*args, code=0):
            r = subprocess.run([sys.executable, "-I", str(WF), *map(str, args)], env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
            return r
        run("setup", "--workspace", self.tmp / "no-such-folder", code=2)
        scan_root = self.tmp / "devdir"
        make_repo(scan_root / "food-delivery")
        r = run("setup", "--workspace", self.ws, "--scan", scan_root)  # unmapped repos are warnings, not errors
        cfg = json.loads(new_local.read_text(encoding="utf-8"))
        self.assertEqual(Path(cfg["workspace"]), self.ws)
        self.assertTrue(cfg["projects"]["food-delivery"]["repo"].endswith("food-delivery"))
        out = run("projects", "list", "--json").stdout
        self.assertIn("food-delivery", out)

    def test_setup_init_creates_a_usable_empty_workspace(self):
        fresh = self.tmp / "fresh-ws"
        env = dict(os.environ, WF_LOCAL_CONFIG=str(self.tmp / "fresh-local.json"), PYTHONIOENCODING="utf-8")
        env.pop("WF_WORKSPACE", None)
        r = subprocess.run([sys.executable, "-I", str(WF), "setup", "--workspace", str(fresh), "--init"], env=env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for f in ("Portfolio/capacity.json", "Portfolio/projects.json", "Portfolio/delivery-metrics.json", "Portfolio/id-registry.json"):
            self.assertTrue((fresh / f).exists(), f)
        r = subprocess.run([sys.executable, "-I", str(WF), "new-workspace", "first", "--name", "First"], env=env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((fresh / "Projects" / "first" / "ProjectWorkspace" / "10-Data" / "journey.json").exists())


class T15_Kit(MoreWFTest):
    def pack(self):
        out = self.tmp / "kit.zip"
        self.wf("kit", "pack", "--out", out)
        return out

    def test_pack_contains_everything_and_no_machine_data(self):
        with zipfile.ZipFile(self.pack()) as z:
            names = z.namelist()
            self.assertIn("CLAUDE.md", names)
            self.assertIn("wirat-workflow/scripts/wf.py", names)
            self.assertIn("wirat-workflow/templates/ProjectWorkspace/20-Views/journey.html", names)
            for s in SKILLS:
                self.assertIn(f"skills/{s}/SKILL.md", names)
            self.assertFalse([n for n in names if "local.json" in n or "__pycache__" in n or n.endswith(".pyc")])
            manifest = json.loads(z.read("KIT.json"))
            self.assertEqual(manifest["files"]["wirat-workflow/scripts/wf.py"], sha(WF))

    def test_install_into_a_clean_home_and_it_runs(self):
        kit, home = self.pack(), self.tmp / "pc2" / ".claude"
        self.wf("kit", "install", kit, "--claude-home", home)
        self.assertEqual(sha(home / "wirat-workflow" / "scripts" / "wf.py"), sha(WF))
        self.assertTrue((home / "skills" / "uat-manager" / "SKILL.md").exists())
        self.assertEqual(sha(home / "CLAUDE.md"), sha(CLAUDE_HOME / "CLAUDE.md"))
        env = dict(os.environ, WF_WORKSPACE=str(self.ws), WF_LOCAL_CONFIG=str(self.tmp / "pc2-local.json"), PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "-I", str(home / "wirat-workflow" / "scripts" / "wf.py"), "validate"], env=env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        again = self.wf("kit", "install", kit, "--claude-home", home).stdout
        self.assertIn("unchanged: wirat-workflow", again)

    def test_update_backs_up_and_keeps_local_config_and_foreign_claude_md(self):
        kit, home = self.pack(), self.tmp / "pc2" / ".claude"
        self.wf("kit", "install", kit, "--claude-home", home)
        (home / "wirat-workflow" / "local.json").write_text('{"workspace": "D:/mine"}', encoding="utf-8")
        (home / "skills" / "clarify" / "SKILL.md").write_text("locally edited", encoding="utf-8")
        (home / "CLAUDE.md").write_text("my own rules", encoding="utf-8")
        (home / "skills" / "my-other-skill").mkdir()
        (home / "skills" / "my-other-skill" / "SKILL.md").write_text("keep me", encoding="utf-8")
        self.wf("--dry-run", "kit", "install", kit, "--claude-home", home)
        self.assertEqual((home / "skills" / "clarify" / "SKILL.md").read_text(encoding="utf-8"), "locally edited")  # dry-run changed nothing
        self.wf("kit", "install", kit, "--claude-home", home)
        self.assertNotEqual((home / "skills" / "clarify" / "SKILL.md").read_text(encoding="utf-8"), "locally edited")
        backups = list((home / "backups").glob("wirat-kit-*/skills/clarify/SKILL.md"))
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "locally edited")
        self.assertEqual((home / "CLAUDE.md").read_text(encoding="utf-8"), "my own rules")  # never overwritten
        self.assertEqual(sha(home / "CLAUDE.wirat.md"), sha(CLAUDE_HOME / "CLAUDE.md"))
        self.assertEqual((home / "skills" / "my-other-skill" / "SKILL.md").read_text(encoding="utf-8"), "keep me")
        self.assertIn("D:/mine", (home / "wirat-workflow" / "local.json").read_text(encoding="utf-8")) if (home / "wirat-workflow" / "local.json").exists() else None

    def test_unsafe_kit_is_rejected(self):
        bad = self.tmp / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("skills/../../evil.txt", "x")
        self.wf("kit", "install", bad, "--claude-home", self.tmp / "h", code=2)
        self.assertFalse((self.tmp / "evil.txt").exists())
        self.wf("kit", "pack", "--out", self.tmp / "kit.zip")
        self.wf("kit", "pack", "--out", self.tmp / "kit.zip", code=2)  # never overwrites a kit


class T16_Views(MoreWFTest):
    def test_views_are_current_templates_and_use_lazy_journey(self):
        v = self.proj("food-delivery") / "20-Views"
        for name in ("progress.html", "journey.html", "backlog.html"):
            self.assertEqual(view_ver(v / name), view_ver(TPL_VIEWS / name))
        j = (v / "journey.html").read_text(encoding="utf-8")
        self.assertIn("journey-data/", j)
        self.assertIn("WF_JOURNEY", j)
        p = (v / "progress.html").read_text(encoding="utf-8")
        self.assertIn("projstrip", p)
        self.assertIn("repo_mapped", p)

    def test_views_script_syntax(self):
        import shutil as sh
        node = sh.which("node")
        if not node:
            self.skipTest("node not available")
        for name in ("progress.html", "journey.html", "backlog.html"):
            html = (self.proj("food-delivery") / "20-Views" / name).read_text(encoding="utf-8")
            body = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
            f = self.tmp / f"{name}.js"
            f.write_text(body, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")

    def test_upgrade_keeps_a_backup_and_adds_no_html_files(self):
        v = self.proj("food-delivery") / "20-Views"
        old = re.sub(r"<!-- wf-view-version: \d+ -->", "", (v / "progress.html").read_text(encoding="utf-8"))
        (v / "progress.html").write_text(old, encoding="utf-8")
        self.assertIn("older than the template", self.wf("validate", "food-delivery").stdout)
        h = tree_hash(v)
        self.wf("--dry-run", "views", "--project", "food-delivery")
        self.assertEqual(h, tree_hash(v))
        out = self.wf("views", "--project", "food-delivery").stdout
        self.assertIn(f"progress.html: v0 -> v{view_ver(TPL_VIEWS / 'progress.html')}", out)
        self.assertIn("up to date", out)
        self.assertEqual(sorted(p.name for p in v.glob("*.html")), ["backlog.html", "journey.html", "progress.html"])
        baks = list((v / "_prev").glob("*_progress.html.bak"))
        self.assertEqual(len(baks), 1)
        self.assertEqual(baks[0].read_text(encoding="utf-8"), old)
        self.assertEqual(view_ver(v / "progress.html"), view_ver(TPL_VIEWS / "progress.html"))


class T17_CompactReads(MoreWFTest):
    def test_tasks_are_one_line_each_riskiest_first_and_capped(self):
        r = self.wf("tasks", "--limit", "6").stdout.splitlines()
        self.assertEqual(len(r), 7)  # header + 6
        self.assertRegex(r[1], r"^TASK-\d+ \| ")
        self.assertIn("delayed", r[1])
        only = self.wf("tasks", "--project", "food-delivery", "--status", "all", "--limit", "50").stdout
        self.assertNotIn("it-service-request", only)
        self.assertIn("accepted/done", only)

    def test_artifacts_list_current_revisions_only(self):
        p = self.proj("it-service-request") / "00-Project" / "decisions" / "20261020-120000_DEC-002_dec-002.md"
        rev = Path(self.wf("revise", p).stdout.strip())
        out = self.wf("artifacts", "it-service-request", "--kind", "decisions").stdout
        self.assertIn(rev.name, out)
        self.assertNotIn(p.name, out)
        self.assertIn("rev 2", out)


class T18_Repair(MoreWFTest):
    def test_validate_flags_and_repairs_a_hand_edited_mirror(self):
        data = self.proj("it-service-request") / "10-Data"
        self.wf("update-task", "TASK-014", "--set", "progress=71")
        good = (data / "backlog.json").read_text(encoding="utf-8")
        (data / "backlog.json").write_text(good.replace("Confirm SLA matrix", "HAND EDIT"), encoding="utf-8")
        r = self.wf("validate", code=1)
        self.assertIn("differs from its latest revision", r.stdout)
        self.assertIn("--repair", r.stdout)
        self.wf("--dry-run", "validate", "--repair", code=0)
        self.assertIn("HAND EDIT", (data / "backlog.json").read_text(encoding="utf-8"))  # dry-run changed nothing
        self.assertIn("repaired", self.wf("validate", "--repair").stdout)
        self.assertEqual((data / "backlog.json").read_text(encoding="utf-8"), good)
        self.wf("validate")


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1, argv=[sys.argv[0]])

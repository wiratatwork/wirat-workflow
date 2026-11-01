#!/usr/bin/env python3
"""Make a long-project copy of a workspace and report how big everything is.

    python -I stress_journey.py <workspace> <project-slug> [--events 500] [--out <folder>]

Works on a COPY (never on the workspace you give it, never on your machine config), fills the project's
journey with N long events, then prints what a reader (Claude, the HTML views, the bundles) has to load.
Open <copy>/Projects/<slug>/ProjectWorkspace/20-Views/journey.html to see the lazy loading.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / "scripts" / "wf.py"


def kb(p):
    return f"{Path(p).stat().st_size / 1024:.1f} KB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("slug")
    ap.add_argument("--events", type=int, default=500)
    ap.add_argument("--out")
    a = ap.parse_args()
    src = Path(a.workspace).expanduser()
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="wf-stress-")) / "ws"
    if out.exists():
        sys.exit(f"{out} already exists")
    shutil.copytree(src, out)
    os.environ.update(WF_WORKSPACE=str(out), WF_LOCAL_CONFIG=str(out.parent / "local-stress.json"), WF_TODAY="2026-11-01")
    spec = importlib.util.spec_from_file_location("wfm", WF)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if a.slug not in m.project_slugs():
        sys.exit(f"unknown project {a.slug}: {m.project_slugs()}")
    detail = "รายละเอียดการประชุมและเหตุผลที่ยาวมาก " * 12  # ~480 chars, near the 600 limit
    t0 = time.time()
    for i in range(a.events):
        mod = ["sla", "request", "report", "notification"][i % 4]
        m.journey_append(a.slug, {"date": f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}", "type": ["change", "meeting", "decision", "milestone"][i % 4],
                                  "title": f"เหตุการณ์ทดสอบที่ {i}", "summary": detail, "modules": [mod], "tasks": [f"TASK-{9 + i % 12:03d}"]},
                         [{"module": mod, "stage": f"stage-{i}", "change": f"ขั้นตอนที่ {i}"}])
    m.bundle(quiet=True)
    fill = time.time() - t0
    ws = m.pws(a.slug)
    data = ws / "10-Data"
    evs = list((data / "journey-events").rglob("EV-*.json"))
    total = sum(f.stat().st_size for f in evs)
    run = lambda *x: subprocess.run([sys.executable, "-I", str(WF), *x], capture_output=True, text=True, encoding="utf-8",
                                    env=dict(os.environ, PYTHONIOENCODING="utf-8")).stdout
    print(f"copy: {out}\nproject: {a.slug}, {len(evs)} event files, {total / 1024:.0f} KB of full history (filled in {fill:.0f}s)\n")
    print("what readers must load                      size")
    print(f"  10-Data/journey.json   (digest, Claude)   {kb(data / 'journey.json')}")
    print(f"  10-Data/data.js        (HTML bundle)      {kb(data / 'data.js')}")
    print(f"  Portfolio/portfolio-data.js               {kb(out / 'Portfolio' / 'portfolio-data.js')}")
    periods = sorted((data / 'journey-data').glob('*.js'))
    print(f"  journey.html loads 2 newest of {len(periods)} month files:  " + ", ".join(f"{p.stem} {kb(p)}" for p in periods[-2:]))
    print("\nwhat Claude gets from the commands (characters):")
    for label, args in (("journey (default, last 15)", ("journey", a.slug)), ("journey --digest", ("journey", a.slug, "--digest")),
                        ("journey --limit 500 --full", ("journey", a.slug, "--limit", "500", "--full")),
                        ("journey --module sla", ("journey", a.slug, "--module", "sla")),
                        ("tasks", ("tasks", "--limit", "40")), ("progress (summary)", ("progress", a.slug))):
        print(f"  {label:32} {len(run(*args)):>6}")
    print(f"\nfull history on disk {total / 1024:.0f} KB vs digest {Path(data / 'journey.json').stat().st_size / 1024:.1f} KB: "
          f"reading cost does not grow with the project.")
    print(f"To try it with Claude: wf.py projects set-workspace \"{out}\"  (and set it back afterwards)")


if __name__ == "__main__":
    main()

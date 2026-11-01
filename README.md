# Wirat Workflow Kit

ชุดเครื่องมือสำหรับ Claude Code ที่ช่วยจัดงานหลายโปรเจกต์: เก็บข้อมูลโปรเจกต์เป็นไฟล์ใน Obsidian, ตาม task/ความเสี่ยง/capacity,
บันทึกการตัดสินใจ และมีหน้า HTML (Progress, Backlog, Journey) ที่แสดง Gantt, KPI และไทม์ไลน์

> เขียนโดยและสำหรับ Wirat (Full Stack Developer) — ภาษาหลักในเอกสารคือภาษาไทย
> **ยังเป็นชุดส่วนตัว**: ชื่อ owner `wirat` และ path `~/Obsidian/Wirat-Workspace` ถูกฝังไว้ ดู "ปรับให้เป็นของคุณ" ด้านล่าง

## มีอะไรบ้าง
| โฟลเดอร์/ไฟล์ | ใช้ทำอะไร |
|---|---|
| `CLAUDE.md` | กติกาและตารางเลือก skill อัตโนมัติ (วางไว้ที่ `~/.claude/CLAUDE.md`) |
| `skills/` | workflow skills 14 ตัว: `project-onboarding`, `meeting-intake`, `clarify`, `project-memory`, `work-management`, `progress-view`, `delivery-metrics`, `capacity-planner`, `estimate-assistant`, `plan-change-control`, `build-loop`, `quality-gate`, `uat-manager`, `delivery-report` |
| `wirat-workflow/scripts/wf.py` | CLI หลัก (สร้าง/อ่าน/แก้ข้อมูลโปรเจกต์ทุกอย่างผ่านคำสั่งนี้) |
| `wirat-workflow/templates/` | เทมเพลต artifact และหน้า HTML (`20-Views/`) ที่ใช้ Tailwind CDN |
| `wirat-workflow/tests/` | ชุดทดสอบของ `wf.py` |
| `wirat-workflow/README.md` | คู่มือการทำงานเต็มของ workflow |

ไม่มีข้อมูลโปรเจกต์ และไม่มี `local.json` (ไฟล์ path ของแต่ละเครื่อง)

## ต้องมี
- Python 3 (ทดสอบกับ 3.12; ไม่ต้องติดตั้งแพ็กเกจเพิ่ม)
- [Claude Code](https://claude.com/claude-code)
- อินเทอร์เน็ตตอนเปิดหน้า HTML (Tailwind และฟอนต์ Noto Sans Thai โหลดจาก CDN)

## ติดตั้ง
สำรอง `~/.claude` ของคุณก่อน แล้ว:
```bash
git clone <URL ของ repo นี้> wirat-workflow-kit
cd wirat-workflow-kit

# 1) skills และ workflow (ไม่ทับ skill อื่นของคุณ)
cp -r skills/* ~/.claude/skills/
cp -r wirat-workflow ~/.claude/wirat-workflow

# 2) CLAUDE.md — อย่าเขียนทับของเดิม ให้นำเนื้อหามารวมกับ ~/.claude/CLAUDE.md เอง
#    (ถ้ายังไม่มีไฟล์นี้ คัดลอกได้เลย: cp CLAUDE.md ~/.claude/CLAUDE.md)

# 3) ผูกกับเครื่องนี้: โฟลเดอร์ workspace ของคุณ + โฟลเดอร์ที่เก็บ repo โปรเจกต์
python -I ~/.claude/wirat-workflow/scripts/wf.py setup --workspace <โฟลเดอร์ workspace> --scan <โฟลเดอร์ repo>
python -I ~/.claude/wirat-workflow/scripts/wf.py projects check
```
แล้วเปิด Claude Code ใหม่ ลองพิมพ์ "เริ่มโปรเจกต์ใหม่" เพื่อสร้าง ProjectWorkspace แรก

## ปรับให้เป็นของคุณ
- `wirat-workflow/config.json`: เปลี่ยน `owner`, `owner_display_name`, `workspace`
- `CLAUDE.md`: ส่วน "Who I work with" และ path ของ Obsidian
- หน้า `progress.html` ใน `templates/.../20-Views/`: ค่าคงที่ `OWNER = "wirat"` (ปุ่ม "ของฉัน")

## ทดสอบ
```bash
python -I wirat-workflow/tests/run_tests.py   # สร้างข้อมูลจำลองในโฟลเดอร์ชั่วคราว ไม่แตะ workspace จริง
```

## หมายเหตุ
- ยังไม่ได้กำหนด license — ผู้ใช้ควรถามเจ้าของก่อนนำไปแจกต่อ
- ถ้าใช้หลายเครื่อง อย่าแก้ workspace เดียวกันพร้อมกัน ดู `wirat-workflow/README.md` หัวข้อ "Several computers"

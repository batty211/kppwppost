# AGENTS.md

ไฟล์นี้เป็นคู่มือสำหรับ Coding Agent เช่น Codex ที่เข้ามาอ่าน แก้ไข หรือทดสอบ
repository นี้ โดยมีเป้าหมายให้ agent เข้าใจวิธีทำงานของโปรเจกต์ได้เร็วและไม่แก้
พฤติกรรมสำคัญโดยไม่ตั้งใจ

## Project Purpose

`kppost` เป็น Python CLI สำหรับ:

1. อ่านบทความ Markdown และรูปจาก batch directory
2. สร้างและตรวจ `batch.json`
3. อัปโหลดรูปเข้า WordPress Media Library
4. แปลง Markdown เป็น Gutenberg Core Blocks
5. สร้าง WordPress Posts ผ่าน REST API
6. เก็บ checkpoint เพื่อให้รันซ้ำได้โดยไม่สร้างข้อมูลซ้ำ

ขอบเขตรุ่นปัจจุบันคือ WordPress Posts เท่านั้น ไม่รวม Pages, Custom Post Types,
GUI, SEO plugin fields หรือการแก้ไขโพสต์เดิม

## Environment

ใช้ Python 3.12 ผ่าน Miniconda:

```bash
conda env create -f environment.yml
conda activate kppost
```

ถ้า environment มีอยู่แล้ว:

```bash
conda activate kppost
python -m pip install -e ".[dev]"
```

## Important Commands

```bash
kppost generate ./examples/sample-batch
kppost validate ./examples/sample-batch
kppost preflight ./path/to/batch
kppost import ./path/to/batch
pytest
python -m compileall -q src tests
python -m pip check
```

`preflight` และ `import` ต้องมี WordPress credentials ใน `.env` ส่วน tests ปกติ
ไม่ต้องเชื่อม WordPress จริง

## Repository Map

```text
src/kppost/              Python package
src/kppost/cli.py        Click command entry points
src/kppost/manifest.py   Folder scan, manifest generation and validation
src/kppost/markdown.py   Markdown parsing and Gutenberg rendering
src/kppost/importer.py   Import orchestration and resume behavior
src/kppost/wordpress.py  WordPress REST API client and retry policy
src/kppost/checkpoint.py Local import state
schemas/                 Development copy of JSON Schema
tests/                   Unit and mocked integration tests
examples/sample-batch/   Runnable local sample
```

อ่าน [ARCHITECTURE.md](ARCHITECTURE.md) สำหรับ data flow และอ่าน
[SPEC.md](SPEC.md) สำหรับพฤติกรรมที่ต้องรักษา

## Working Agreement

- ก่อนเริ่มใช้เครื่องมือ รันคำสั่ง แก้ไฟล์ หรือสร้างผลลัพธ์ ให้แจ้งผู้ใช้ก่อนว่า
  จะทำอะไร โดยสรุปเป็นรายการลำดับเลข `1. 2. 3.`
- ก่อนทำงานทุกครั้ง ให้บอกแนวทางที่จะทำแบบสั้นและชัดเจน เช่น จะอ่านไฟล์ใด
  จะรันคำสั่งใด หรือจะแก้ behavior ส่วนไหน เพื่อให้ผู้ใช้เห็นทิศทางก่อน
  agent ลงมือ
- หาก requirement, scope, output, version, data source, credentials, หรือ
  operation ที่อาจกระทบข้อมูลยังไม่ชัดเจน ให้ถามคำถามที่จำเป็นก่อน และต้องรอ
  ให้ผู้ใช้ตกลงหรือให้คำตอบก่อนดำเนินขั้นตอนนั้น
- หลังแจ้งแผนแล้วจึงเริ่มดำเนินงาน หากผู้ใช้ระบุให้สอบถามหรือรออนุมัติก่อนทำ
  ต้องหยุดรอคำยืนยันก่อนเสมอ
- หากขอบเขตงานเปลี่ยนระหว่างดำเนินการ ให้แจ้งแผนที่เปลี่ยนก่อนทำขั้นตอนใหม่

## Engineering Rules

- รักษา source layout และ naming rules ตาม `SPEC.md`
- ห้ามเปลี่ยนชื่อ ลบ หรือแก้รูปต้นฉบับระหว่าง import
- ห้ามเขียน WordPress ก่อน local validation และ taxonomy preflight สำเร็จ
- ห้ามอัปเดตโพสต์ที่ slug ชนกับข้อมูลนอก checkpoint
- Category/Tags เป็น existing-only: resolve ด้วย slug, ตรวจ parent และห้ามสร้างใหม่
- Post creation ต้องส่ง `comment_status=closed` และ `ping_status=closed` เสมอ
- checkpoint ต้องถูกบันทึกทันทีหลัง Media หรือ Post ถูกสร้างสำเร็จ
- ห้ามแสดง Application Password ใน log, exception หรือ report
- Path จาก Markdown และ manifest ต้องอยู่ภายใน batch directory
- ใช้ structured JSON parsing และ Markdown AST ห้าม parse ด้วย regex แบบเฉพาะกิจ
- การแก้ JSON Schema ต้องแก้ทั้ง `schemas/batch.schema.json` และ
  `src/kppost/schemas/batch.schema.json`
- เพิ่ม dependency เฉพาะเมื่อจำเป็น และอัปเดตทั้ง `pyproject.toml` กับ
  `environment.yml` หากขั้นตอนติดตั้งเปลี่ยน
- อย่าแก้ generated state ใน `.bulkpost/` เป็นส่วนหนึ่งของ source code

## Testing Expectations

ก่อนจบงานที่แตะ behavior ให้รันอย่างน้อย:

```bash
conda run -n kppost pytest
conda run -n kppost python -m compileall -q src tests
```

เพิ่มหรือแก้ tests เมื่อเปลี่ยน:

- filename/slug/department parsing
- Markdown หรือ Gutenberg output
- Media naming และ metadata
- WordPress request/response behavior
- retry, checkpoint หรือ resume behavior
- manifest schema หรือ validation

WordPress tests ควรใช้ mock เป็นค่าเริ่มต้น การทดสอบกับเว็บไซต์จริงต้องใช้ staging
และต้องไม่ใส่ credentials ลง repository

## Documentation Roles

- `README.md`: คู่มือใช้งานสำหรับผู้ใช้
- `SPEC.md`: ข้อกำหนดและ acceptance criteria ของระบบ
- `ARCHITECTURE.md`: โครงสร้างภายในและเหตุผลเชิงออกแบบ
- `AGENTS.md`: แนวทางให้ agent พัฒนา repository อย่างถูกต้อง

เมื่อ behavior เปลี่ยน ให้ปรับเอกสารที่เกี่ยวข้องในงานเดียวกัน

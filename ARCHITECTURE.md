# ARCHITECTURE.md

เอกสารนี้อธิบายว่า `kppost` ถูกแบ่งเป็นส่วนใด ข้อมูลไหลอย่างไร และ state ถูกเก็บ
ที่ไหน เหมาะสำหรับนักพัฒนาหรือ Coding Agent ที่ต้องแก้ implementation

## System Context

```text
Markdown + local images
          |
          v
   kppost Python CLI
          |
          | HTTPS + Application Password
          v
 WordPress REST API
   - Posts
   - Media
   - Categories
   - Tags
```

ระบบเป็น local CLI ไม่มี server หรือ database ของตัวเอง ไฟล์ต้นทางและ state ของ
แต่ละ batch อยู่ใน filesystem ส่วนข้อมูลปลายทางอยู่ใน WordPress

## Main Components

### CLI

`src/kppost/cli.py`

- ประกาศคำสั่ง `generate`, `validate`, `preflight`, `import`
- โหลด config และแปลง expected errors เป็นข้อความ CLI
- แสดง progress และคืน exit code `1` เมื่อ import มีรายการล้มเหลว

### Configuration

`src/kppost/config.py`

- อ่าน `.env` จาก working directory และ batch directory
- ต้องมี `WP_URL`, `WP_USERNAME`, `WP_APPLICATION_PASSWORD`
- บังคับ HTTPS
- รองรับ timeout และ SSL verification configuration

### Manifest

`src/kppost/manifest.py`

- อ่าน `departments.json`
- scan เฉพาะ `content/*.md`
- parse วันที่, department code และ post number จากชื่อไฟล์
- อ่าน title/excerpt และตรวจรูปผ่าน Markdown parser
- สร้าง slug และ taxonomy mapping จาก `departments.json`
- เก็บ WordPress Category slug, parent slug และ Tag slug ใน `batch.json`
- ตรวจ JSON Schema และตรวจว่า manifest ยังตรงกับ source files

`batch.json` เป็น derived manifest ไม่ใช่ source หลัก ยกเว้นค่า `status` ระดับ batch
ซึ่ง generator จะรักษาไว้หากเป็น `draft`, `pending` หรือ `publish`

### Markdown and Gutenberg

`src/kppost/markdown.py`

- ใช้ `markdown-it-py` สร้าง token/AST
- H1 แรกและ H1 เดียวเป็นชื่อโพสต์
- ย่อหน้าแรกเป็น excerpt
- ตรวจ inline image path และ file signature
- แปลง token เป็น Gutenberg block markup
- เปลี่ยน local image path เป็น Media URL ที่ WordPress ส่งกลับ

HTML ใน Markdown ถูกปิดไว้ รูปต้องอยู่ใน paragraph ของตัวเองเพื่อสร้าง
`core/image` block ที่แก้ไขใน Block Editor ได้

### Import Orchestration

`src/kppost/importer.py`

ลำดับงานหลัก:

1. Validate source และ `batch.json`
2. คำนวณเวลาโพสต์ด้วย timezone `Asia/Bangkok`
3. โหลด checkpoint
4. ทำ WordPress preflight และตรวจ taxonomy mapping แบบ read-only
5. ประมวลผลโพสต์ตามลำดับ manifest
6. ตรวจ slug collision
7. upload/reuse Media
8. resolve Category และ Tags เดิมด้วย slug
9. render Gutenberg content
10. create Post
11. attach Media เข้ากับ Post
12. บันทึก checkpoint และ report

ความล้มเหลวของโพสต์หนึ่งไม่หยุดโพสต์อื่น แต่ CLI จะคืน exit code ล้มเหลวหากมี
อย่างน้อยหนึ่งรายการที่ไม่สำเร็จ

### WordPress Client

`src/kppost/wordpress.py`

- ห่อ `requests.Session`
- ใช้ Basic Authentication กับ WordPress Application Password
- ติดต่อ `/wp-json/wp/v2`
- retry timeout, connection error, HTTP `429` และ `5xx` รวมสูงสุด 3 attempts
- ไม่ retry validation, authentication, permission และ slug collision errors
- ค้น Category/Tags ด้วย `context=view`
- ตรวจว่า Category ย่อยมี parent ตรงกับ Category ที่ระบุด้วย parent slug
- ไม่สร้าง แก้ไข หรือลบ Category/Tags
- อัปโหลด Media ด้วย `Content-Disposition` เพื่อกำหนด filename บน WordPress

### Checkpoint and Reports

`src/kppost/checkpoint.py`

```text
<batch>/.bulkpost/
├── state.json
├── generated-preview.json
└── reports/import-YYYYMMDD-HHMMSS.json
```

`state.json` เก็บ Media ID, URL, filename, SHA-256 และ WordPress Post ID
การเขียน JSON ใช้ temporary file แล้ว `os.replace` เพื่อให้เป็น atomic write

เมื่อรันซ้ำ:

- Post ที่ `success` ถูกข้าม
- Media ที่อัปโหลดแล้วถูกใช้ซ้ำ
- ถ้า source image เปลี่ยนหลัง upload ระบบหยุดรายการนั้นแทนการใช้ Media เดิมผิดไฟล์
- Post ที่สร้างแล้วแต่ attach Media ยังไม่ครบจะใช้ Post เดิมต่อ

## Data Flow

### Generate

```text
departments.json
content/*.md
content/<post-stem>/*
        |
        v
build_manifest()
        |
        v
JSON Schema validation
        |
        +--> batch.json
        |
        +--> .bulkpost/generated-preview.json เมื่อ manifest เดิมมีอยู่
```

### Import

```text
batch.json + source files
        |
        v
local validation
        |
        v
WordPress preflight
        |
        v
taxonomy lookup/verification
        |
        v
Media upload --> checkpoint
        |
        v
Gutenberg render
        |
        v
Post create --> checkpoint
        |
        v
Media attach --> success --> report
```

## Time Assignment

โพสต์ถูกจัดกลุ่มตามวันที่และ department code:

- post number สูงสุดใช้เวลาเริ่ม import
- post ก่อนหน้าถอยหลังครั้งละหนึ่งนาที
- วันที่ยังคงมาจากชื่อไฟล์
- หากการถอยเวลาข้ามไปวันก่อนหน้า validation จะล้มเหลว

ตัวอย่าง เมื่อเริ่ม import เวลา `10:00`:

```text
post03 = 10:00
post02 = 09:59
post01 = 09:58
```

## Security Boundaries

- WordPress URL ต้องเป็น HTTPS
- credentials อยู่ใน `.env` และไม่ถูก commit
- local paths ต้อง resolve อยู่ใต้ batch root
- remote/data URL images ไม่รองรับ
- source images ต้องเป็น JPG, JPEG, PNG หรือ WebP ที่ signature ตรงกับ extension
- ระบบไม่ลบหรือ rollback ข้อมูล WordPress อัตโนมัติ

## Design Constraints

- จำกัด 100 posts ต่อ batch
- ประมวลผลแบบลำดับ ไม่ใช้ parallel upload
- รองรับ WordPress Posts มาตรฐานเท่านั้น
- ไม่มี cross-batch Media deduplication
- ไม่มีการ sync การแก้ไข source กลับไปยังโพสต์ที่สำเร็จแล้ว

# SPEC.md

เอกสารนี้เป็นข้อกำหนดเชิงพฤติกรรมของ `kppost` หาก README, implementation หรือ
ความเข้าใจของผู้พัฒนาไม่ตรงกัน ให้ตรวจเอกสารนี้ร่วมกับ tests ก่อนเปลี่ยน behavior

## 1. Product Goal

ผู้ใช้ต้องสามารถเตรียมบทความและรูปใน directory แล้วสั่ง CLI เพื่อสร้าง WordPress
Posts จำนวนมากผ่าน REST API โดยไม่ใช้ปลั๊กอินเสียเงิน และสามารถรันซ้ำหลังเกิด
ความผิดพลาดได้โดยไม่สร้างข้อมูลซ้ำ

## 2. Supported Environment

- Python 3.12
- Miniconda environment ชื่อ `kppost`
- WordPress ที่เปิด REST API
- HTTPS
- WordPress Application Password
- Timezone สำหรับการคำนวณวันเวลา: `Asia/Bangkok`

## 3. Batch Input

โครงสร้างขั้นต่ำ:

```text
batch/
├── departments.json
└── content/
    ├── 2026-06-07-inv-post01.md
    └── 2026-06-07-inv-post01/
        ├── 1.jpg
        └── result.webp
```

หนึ่ง batch ต้องมี 1-100 Markdown files

### Markdown Filename

รูปแบบบังคับ:

```text
YYYY-MM-DD-DEPARTMENT_CODE-postNN.md
```

กฎ:

- วันที่ต้องเป็นวันที่จริง
- department code ใช้ตัวอักษรอังกฤษหรือตัวเลข
- code ถูก normalize เป็นตัวพิมพ์เล็ก
- `NN` อยู่ระหว่าง `01` ถึง `99`
- date + department code + post number ต้องไม่ซ้ำ

### Department Registry

`departments.json` ต้องมี:

```json
{
  "departments": [
    {
      "code": "inv",
      "id": "01",
      "name": "งานสืบสวนปราบปราม",
      "wordpress_category_slug": "investigation",
      "wordpress_category_parent_slug": "activities",
      "wordpress_tag_slug": "investigate"
    }
  ]
}
```

`code`, `id`, `name` และ WordPress slug mappings ต้องมีค่า `code`, `id` และ
`name` ต้องไม่ซ้ำกัน เก็บ `id` เป็น string เพื่อรักษาเลขศูนย์นำหน้า

- `wordpress_category_slug` ระบุ Category ย่อยที่มีอยู่แล้ว
- `wordpress_category_parent_slug` ระบุ Parent Category ที่มีอยู่แล้ว
- `wordpress_tag_slug` ระบุ Tag ประจำแผนกที่มีอยู่แล้ว
- taxonomy configuration ไม่อยู่ใน Markdown

## 4. Markdown Content

- Markdown block แรกต้องเป็น H1
- ต้องมี H1 เพียงหนึ่งรายการ
- ข้อความ H1 เป็น WordPress Post title
- H1 ถูกตัดออกจาก post content
- ย่อหน้าแรกหลัง H1 เป็น excerpt โดยตัด Markdown formatting
- HTML ที่เขียนใน Markdown ไม่ถูกเปิดใช้งาน
- รองรับ paragraph, heading, bold, italic, link, list, quote, code, table,
  separator และ image

รูปใน Markdown:

- ใช้ relative local path
- ต้องอยู่ภายใน batch directory
- ต้องเป็น JPG, JPEG, PNG หรือ WebP
- file signature ต้องตรงกับ extension
- แต่ละรูปต้องอยู่ใน paragraph ของตัวเอง
- remote URL, protocol-relative URL และ data URL ไม่รองรับ
- alt text มาจาก Markdown image alt
- caption มาจาก Markdown image title

## 5. Featured Image

แต่ละ Markdown file ต้องมี image directory ชื่อเดียวกับ filename stem

ตัวอย่าง:

```text
2026-06-07-inv-post01.md
2026-06-07-inv-post01/
```

ใน image directory ต้องพบ Featured Image เพียงหนึ่งไฟล์:

```text
1.jpg
1.jpeg
1.png
1.webp
```

ถ้าพบศูนย์ไฟล์หรือมากกว่าหนึ่ง extension ให้ validation ล้มเหลว

## 6. Generated Metadata

สำหรับ:

```text
2026-06-07-inv-post01.md
```

และ department:

```json
{
  "code": "inv",
  "id": "01",
  "name": "งานสืบสวนปราบปราม",
  "wordpress_category_slug": "investigation",
  "wordpress_category_parent_slug": "activities",
  "wordpress_tag_slug": "investigate"
}
```

ระบบต้องสร้าง:

```text
source_id: 2026-06-07-inv-post01
slug: 20260607-inv-01-post01
category: งานสืบสวนปราบปราม
tags:
  - 2026-06
  - งานสืบสวนปราบปราม
wordpress_category_slug: investigation
wordpress_category_parent_slug: activities
wordpress_tag_slugs:
  - 2026-06
  - investigate
```

รุ่นปัจจุบันไม่รองรับ tags เพิ่มรายโพสต์ Category และ Tags ทุกค่าต้องมีอยู่ใน
WordPress ก่อน import ระบบไม่สร้าง taxonomy term ใหม่

## 7. Manifest

`kppost generate <batch>` ต้อง:

- scan source files
- สร้างข้อมูลตาม JSON Schema version `1.0`
- default batch status เป็น `draft`
- รองรับ status `draft`, `pending`, `publish`
- เขียน `batch.json` เมื่อยังไม่มีไฟล์
- เขียน `.bulkpost/generated-preview.json` เมื่อ `batch.json` มีอยู่
- เขียนทับ `batch.json` เฉพาะเมื่อใช้ `--force`
- รักษา status ที่ถูกต้องจาก manifest เดิม

`kppost validate <batch>` ต้องตรวจว่า:

- manifest ผ่าน JSON Schema
- source files ทั้งหมดยังถูกต้อง
- manifest ที่ generate ใหม่ตรงกับ `batch.json`

ถ้า source เปลี่ยนจน manifest ไม่ตรง ต้องแจ้งว่า manifest stale

`kppost preflight <batch>` ต้องตรวจแบบ read-only ว่า:

- Category slug มีอยู่และชื่อตรงกับชื่อแผนก
- Parent Category slug มีอยู่
- Category ย่อยมี parent ID ตรงกับ Parent Category
- Tag เดือนและ Tag แผนกมีอยู่และชื่อตรง
- ไม่มีการสร้างหรือแก้ไข taxonomy ระหว่าง preflight

## 8. WordPress Media

ลำดับ Media ต่อโพสต์:

- `01` คือ Featured Image
- `02` เป็นต้นไปคือ inline images ตามการปรากฏครั้งแรกใน Markdown
- รูป local file เดียวกันที่อ้างหลายครั้ง upload เพียงครั้งเดียว

Filename ที่ส่งไป WordPress:

```text
<post-slug>-<sequence>.<extension>
```

ตัวอย่าง:

```text
20260607-inv-01-post01-01.jpg
20260607-inv-01-post01-02.webp
```

Media title:

```text
<department name> - <post title> - รูป NN
```

Featured Image ใช้ Post title เป็น alt text ส่วน inline images ใช้ alt/caption
จาก Markdown

ระบบต้องบันทึก Media ID, URL และ filename จริงที่ WordPress ส่งกลับ เพราะ
WordPress อาจเติม suffix เมื่อชื่อไฟล์ชน

## 9. WordPress Post

ก่อนสร้าง Post ระบบต้อง:

1. ทำ local validation ทั้ง batch
2. ทำ REST API preflight
3. ตรวจ slug collision
4. resolve Category และ Tags เดิมด้วย slug และตรวจ parent
5. อัปโหลดหรือ reuse Media
6. render Gutenberg blocks

Post payload ต้องมี:

- title
- slug
- Gutenberg content
- excerpt
- batch status
- assigned date/time
- Category IDs
- Tag IDs
- Featured Media ID
- `comment_status: closed`
- `ping_status: closed`

ทุก Post ที่ระบบสร้างต้องปิดความคิดเห็น รวมทั้ง pingbacks และ trackbacks
โดยตรงใน payload ห้ามอาศัยค่า default discussion settings ของ WordPress

หากพบ slug เดิมใน WordPress แต่ไม่มีใน checkpoint ระบบต้องไม่ update หรือ
overwrite Post นั้น

หาก Category/Tag ไม่มี ชื่อไม่ตรง หรือ parent ไม่ตรง ระบบต้องหยุดก่อน upload
Media ของโพสต์นั้น และห้ามสร้าง taxonomy ใหม่

## 10. Date and Ordering

- วันที่มาจาก Markdown filename
- เวลาอ้างอิงมาจากเวลาเริ่ม import ใน `Asia/Bangkok`
- แบ่งกลุ่มตาม date + department code
- post number สูงสุดใช้เวลาเริ่ม import
- post ก่อนหน้าถอยครั้งละหนึ่งนาที
- หากเวลาเลื่อนไปวันก่อนหน้าให้ validation ล้มเหลว

## 11. Checkpoint and Resume

checkpoint อยู่ที่:

```text
<batch>/.bulkpost/state.json
```

ระบบต้องบันทึก state หลัง:

- Media upload แต่ละไฟล์
- Post creation
- Post สำเร็จหรือล้มเหลว

เมื่อรันซ้ำ:

- รายการสำเร็จต้องถูกข้าม
- Media ที่มี checkpoint และ SHA-256 ตรงกันต้อง reuse
- ถ้า source image เปลี่ยนหลัง upload ให้รายการล้มเหลว
- Post ที่สร้างแล้วต้อง reuse เพื่อทำขั้น attach Media ต่อ

ไม่มี automatic rollback หรือ automatic deletion

## 12. Error Handling

retry สูงสุด 3 attempts สำหรับ:

- timeout
- connection error
- HTTP `429`
- HTTP `5xx`

ไม่ retry สำหรับ:

- local validation
- HTTP `400` ที่แก้ด้วยการ retry ไม่ได้
- HTTP `401`
- HTTP `403`
- slug collision

ความล้มเหลวของโพสต์หนึ่งต้องไม่หยุดโพสต์อื่น และ import report ต้องมีจำนวน
`success`, `skipped`, `failed`

## 13. Security Requirements

- `WP_URL` ต้องเป็น HTTPS
- credentials ต้องอยู่ใน `.env`
- `.env` และ `.bulkpost/` ต้องไม่ถูก commit
- Application Password ต้องไม่ปรากฏใน output หรือ report
- path traversal ออกจาก batch directory ต้องถูกปฏิเสธ
- source files ต้องไม่ถูก rename, edit หรือลบระหว่าง import

## 14. Acceptance Checks

งานเปลี่ยน behavior ถือว่าเสร็จเมื่อ:

```bash
conda run -n kppost pytest
conda run -n kppost python -m compileall -q src tests
conda run -n kppost kppost generate examples/sample-batch --force
conda run -n kppost kppost validate examples/sample-batch
```

ผ่านทั้งหมด และเอกสารที่เกี่ยวข้องถูกปรับให้ตรงกับ behavior ใหม่

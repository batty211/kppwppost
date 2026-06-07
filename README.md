# kppost

`kppost` is a Python CLI that generates WordPress post manifests from Markdown
files, uploads local images to the Media Library, converts Markdown to Gutenberg
core blocks, and creates posts through the WordPress REST API.

## Installation with Miniconda

```bash
conda env create -f environment.yml
conda activate kppost
kppost --version
```

Copy `.env.example` to `.env` and set:

```dotenv
WP_URL=https://wordpress.example.com
WP_USERNAME=your-username
WP_APPLICATION_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
WP_TIMEOUT_SECONDS=30
WP_VERIFY_SSL=true
```

The WordPress account needs permission to create posts, upload media, and
assign existing categories and tags. The importer never creates taxonomy terms.
Use HTTPS. Create an Application Password from the WordPress user profile page;
do not use the user's normal login password.

## Batch layout

```text
my-batch/
├── departments.json
└── content/
    ├── 2026-06-07-inv-post01.md
    └── 2026-06-07-inv-post01/
        ├── 1.jpg
        ├── operation.jpg
        └── result.webp
```

`departments.json`:

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

Markdown filenames must use:

```text
YYYY-MM-DD-DEPARTMENT_CODE-postNN.md
```

`postNN` starts at `post01` for each date and department. The matching image
directory has the same name as the Markdown file without `.md`. Exactly one
`1.jpg`, `1.jpeg`, `1.png`, or `1.webp` is required as the featured image.

WordPress taxonomy mapping belongs in `departments.json`, not Markdown. The
importer resolves the existing subcategory by `wordpress_category_slug`, checks
its parent against `wordpress_category_parent_slug`, and resolves the department
tag by `wordpress_tag_slug`. The generated monthly tag such as `2026-05` must
also already exist in WordPress.

## Markdown

```markdown
# ชื่อบทความ

ย่อหน้าแรกใช้เป็น Excerpt

เนื้อหามี **ตัวหนา**, *ตัวเอียง* และ [ลิงก์](https://example.com)

## หัวข้อย่อย

![คำอธิบายรูป](2026-06-07-inv-post01/result.webp "คำบรรยาย")
```

The first and only H1 becomes the WordPress title and is removed from post
content. Images must be local JPG, JPEG, PNG, or WebP files inside the batch.
Put each image on its own Markdown paragraph so it becomes a Gutenberg Image
block. The file signature must match its extension.

## Commands

```bash
kppost prepare ./69-05 ./batch-content-ready
kppost generate ./my-batch
kppost validate ./my-batch
kppost preflight ./my-batch
kppost import ./my-batch
```

## Prepare content from PowerPoint

`prepare` converts a directory of raw post folders into editable Markdown and
image folders:

```bash
kppost prepare ./69-05 ./batch-content-ready
```

Each source folder must begin with a Buddhist Era `YYMMDD` date and normally
contain one `.pptx` plus its original images. The command:

- extracts the original main heading and body text from PowerPoint text objects
- orders posts on the same date by the `เวลา HH.MM น.` value in the body
- writes `YYYY-MM-DD-inv-postNN.md` under `content/`
- copies original JPG, JPEG, PNG, and WebP files without renaming them
- converts HEIC copies to JPG with macOS `sips`
- creates an empty `<original folder name>.txt` marker in each image directory
- adds placeholder Markdown references for `1.jpg`, `2.jpg`, and `3.jpg`
- skips folders without a PPTX and records them in `prepare-report.json`

The subject from the source folder is bolded where it matches the body text. If
the spelling or spacing differs, a bold `ข้อมูลอ้างอิง` line is added before the
original body instead.

The output directory must not already exist. `prepare` never edits the source
folders. Its output is a working area: review the Markdown, process images in
Canva, save the final images as `1.jpg`, `2.jpg`, and `3.jpg`, and add
`departments.json` before running `generate` or `validate`.

## Real post example

ตัวอย่างบทความภาษาไทยพร้อมตำแหน่ง Featured Image และรูปแทรกอยู่ที่:

```text
examples/live-test-batch/
```

โครงสร้างรูปของตัวอย่าง:

```text
content/2026-05-22-inv-post01/
├── 1.jpg  Featured Image (ไม่ต้องเขียนใน Markdown)
├── 2.jpg  รูปแทรกรูปแรก
└── 3.jpg  รูปแทรกรูปที่สอง
```

ตัวอย่างการแทรกรูปใน Markdown:

```markdown
![คำอธิบายรูป](2026-05-22-inv-post01/2.jpg "คำบรรยายใต้รูป")

![คำอธิบายรูป](2026-05-22-inv-post01/3.jpg "คำบรรยายใต้รูป")
```

รูปแต่ละรูปต้องอยู่คนละย่อหน้า ห้ามวางข้อความอื่นในบรรทัดเดียวกับ image syntax
ระบบใช้ข้อความใน `[]` เป็น alt text และข้อความในเครื่องหมายคำพูดเป็น caption
ของ WordPress Media

The first `generate` writes `batch.json`. Later runs write
`.bulkpost/generated-preview.json` so manually reviewed manifests are not
overwritten. Use `--force` to replace `batch.json`.

`batch.json` has one status for the whole batch: `draft`, `pending`, or
`publish`. It defaults to `draft`. Change the status in `batch.json`, then run
`generate` again; the generator preserves a valid existing status.

The preflight command checks authentication, endpoints, existing Category/Tag
slugs, and the subcategory parent relationship without writing data. The import
command performs the same checks before uploading media. Progress state and
reports are stored under `.bulkpost/`. Successful posts are skipped on
subsequent runs, and previously uploaded media are reused.

Every post created by `kppost` explicitly sets comments and
pingbacks/trackbacks to `closed`. This does not depend on the WordPress site's
default discussion settings.

## WordPress naming

For slug `20260607-inv-01-post01`, uploaded files are named:

```text
20260607-inv-01-post01-01.jpg
20260607-inv-01-post01-02.jpg
```

Sequence `01` is the featured image. Inline images follow their first
appearance in Markdown. Media titles use:

```text
<department name> - <post title> - รูป NN
```

WordPress may add a suffix if a filename already exists. The actual filename,
Media ID, and URL returned by WordPress are recorded in the import report.

## Recovery and safety

- The entire batch is validated before any write request.
- HTTP 429, server errors, timeouts, and connection failures retry three times.
- Authentication, permission, validation, and slug collision errors do not retry.
- Existing WordPress slugs outside the local checkpoint are never overwritten.
- Source files are never renamed or deleted.
- There is no automatic rollback or deletion from WordPress.
- `.env` and `.bulkpost/` should not be committed.

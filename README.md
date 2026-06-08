# kppost

`kppost` is a Python CLI that generates WordPress post manifests from Markdown
files, uploads local images to the Media Library, converts Markdown to Gutenberg
core blocks, and creates posts through the WordPress REST API.

Current version: `0.2.5`. See [CHANGELOG.md](CHANGELOG.md).

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

Use a parent slug when the WordPress category is a child category. For a
top-level category, use JSON `null`:

```json
"wordpress_category_parent_slug": null
```

Do not use an empty string. During preflight, `null` requires WordPress to
report that category with `parent: 0`.

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
kppost prepare ./69-05
kppost canva export ./batch-69-05 ./canva-work
kppost canva import ./batch-69-05 \
  -f ./downloads/feature-design.zip \
  -nw ./downloads/news-watermark-design.zip
kppost generate ./my-batch
kppost validate ./my-batch
kppost preflight ./my-batch
kppost post ./my-batch
```

## Complete workflow

### 1. Prepare raw PowerPoint folders

```bash
kppost prepare ./69-05
```

This creates `./batch-69-05` by default, with Markdown, post image directories,
and `prepare-report.json`, without changing the raw source folders. It also
copies a completed cached `departments.json` when available, or creates a
starter file using the selected department code. Complete blank values before
`generate`; future prepare runs can reuse the completed file.

### 2. Review content and choose images

- Review and edit each Markdown file.
- Choose the Featured source image by assigning it `<post-stem>-01`.
- Arrange the remaining source images in the desired order. Their numbers may
  contain gaps because Canva export will normalize the final order.
- Add or verify `departments.json` in the batch root.
- Set `wordpress_category_parent_slug` to the parent slug, or `null` when the
  category is top-level.

### 3. Export Canva Sheets

```bash
kppost canva export ./batch-69-05 ./canva-work
```

Upload both generated XLSX files as Canva Sheets:

- `feature_images_YYMMDDHHMMSS.xlsx`
- `news_image_watermark_YYMMDDHHMMSS.xlsx`

Use `ชื่อไฟล์รูปภาพ` as the Bulk Create page name in each Canva design.

### 4. Design and download from Canva

Run Bulk Create for both designs and download each result as a ZIP. The ZIP
filenames themselves do not matter.

### 5. Import Canva results

```bash
kppost canva import ./batch-69-05 \
  -f "./downloads/(BULK) feature design.zip" \
  -nw "./downloads/(BULK) news watermark.zip"
```

The command validates both ZIP files before changing the batch. It writes
`1.jpg`, `2.jpg`, and so on, and updates Markdown so `1.jpg` is both the
Featured Image and the first inline image.

### 6. Generate and validate the manifest

```bash
kppost generate ./batch-69-05
kppost validate ./batch-69-05
```

If `batch.json` already exists, `generate` writes a preview unless `--force` is
used. Review the manifest status: `draft`, `pending`, or `publish`.

### 7. Check WordPress without writing

```bash
kppost preflight ./batch-69-05
```

This validates credentials, REST endpoints, categories, parent categories, and
tags. All taxonomy terms must already exist.

### 8. Post to WordPress

```bash
kppost post ./batch-69-05
```

Progress and reports are stored under `.bulkpost/`. Successful media and posts
are checkpointed so interrupted runs can resume without creating duplicates.
`kppost import` remains available as an alias.

## Prepare content from PowerPoint

`prepare` converts a directory of raw post folders into editable Markdown and
image folders. It supports PowerPoint folders and plain text folders:

```bash
kppost prepare ./69-05
kppost prepare ./69-04-txt-gen
kppost prepare ./posts
```

Each source folder must begin with a `YYMMDD` date. Years `60` and above are
treated as Buddhist Era years, so `690401` becomes `2026-04-01`; lower years are
treated as Gregorian two-digit years, so `260401` also becomes `2026-04-01`.
Folder names or TXT file names may include a time suffix such as `260401-1630`.
Folder names may include a department code after the date or time, such as
`260426-gen`, `260426-1630-gen`, or `260426-gen-1630`. When a folder name has a
department code, it overrides `--department-code`; otherwise the command uses the
option value, which defaults to `inv`.

Each source folder must contain either one `.pptx` or one `.txt` plus its
original images. The source root is only a raw group name and no longer infers
the department code. The command:

- extracts the original main heading and body text from PowerPoint text objects
- uses the first non-empty TXT line as the heading and the remaining text as the
  body
- orders posts on the same date by the `เวลา HH.MM น.` value in the body, or by
  the folder time suffix for TXT folders without a time in the body
- writes `YYYY-MM-DD-<department>-postNN.md` under `content/`
- copies original JPG, JPEG, PNG, and WebP files as
  `<post-stem>-01`, `<post-stem>-02`, and so on
- converts HEIC copies to JPG with macOS `sips`
- creates an empty `<original folder name>.txt` marker in each image directory
- adds Markdown placeholders for content images `2.jpg` onward based on the
  actual image count; `1.jpg` remains reserved for the Featured Image
- skips folders without a PPTX or TXT and records them in `prepare-report.json`
- reuses a completed `departments.json` from the source root, parent cache, or a
  previous sibling batch when available
- creates a starter `departments.json` if no completed mapping is available

The subject from the source folder is bolded where it matches the body text. If
the spelling or spacing differs, a bold `ข้อมูลอ้างอิง` line is added before the
original body instead.

When `output` is omitted, `prepare` creates a sibling folder named
`batch-YY-MM` for source roots that begin with `YY-MM`; otherwise it creates
`batch-<source-name>`. For example, `./69-04-txt-gen` creates `./batch-69-04`,
and `./posts` creates `./batch-posts`. The output directory must not already exist. `prepare` never
edits the source folders. Its output is a working area. Review the Markdown and
arrange the selected Featured Image as `<post-stem>-01`; the remaining images
use `-02`, `-03`, and so on.

After you complete `departments.json` once, later prepare runs reuse it
automatically. The cache is stored at `<source parent>/.kppost/departments.json`;
for example, preparing `./69-05` can reuse mappings from
`./batch-69-04/departments.json` and then save them to `./.kppost/departments.json`.
Blank starter templates are not cached.

After reviewing the content, create a separate Canva work package:

```bash
kppost canva export ./batch-69-05 ./canva-work
```

The command creates:

```text
canva-work/
├── feature_images_260409170503.xlsx
└── news_image_watermark_260409170503.xlsx
```

`feature_images_YYMMDDHHMMSS.xlsx` contains `หัวข้อ`, `ชื่อไฟล์รูปภาพ`, and an
Excel In-cell `รูปภาพ`. `news_image_watermark_YYMMDDHHMMSS.xlsx` contains
`ชื่อไฟล์รูปภาพ` and an In-cell `รูปภาพ`. Upload each workbook as a Canva Sheet
and use `ชื่อไฟล์รูปภาพ` to name each Bulk Create page. Source image numbers may
contain gaps.

Download the two completed Canva designs as ZIP files. The ZIP filenames do not
matter:

```bash
kppost canva import ./batch-69-05 \
  -f "./downloads/(BULK) feature design.zip" \
  -nw "./downloads/(BULK) news watermark.zip"
```

Both options are required. The command validates every expected image before
changing the batch, converts the results to JPEG, and writes:

```text
content/<post-stem>/
├── 1.jpg  Featured Image and first content image
├── 2.jpg
└── 3.jpg
```

It replaces standalone Markdown image paragraphs with references from `1.jpg`
through the final image while preserving the reviewed text. A report is written
under `.bulkpost/reports/`. Add `departments.json` before running `generate` or
`validate`.

## Real post example

ตัวอย่างบทความภาษาไทยพร้อมตำแหน่ง Featured Image และรูปแทรกอยู่ที่:

```text
examples/live-test-batch/
```

โครงสร้างรูปของตัวอย่าง:

```text
content/2026-05-22-inv-post01/
├── 1.jpg  Featured Image และรูปแทรกรูปแรก
├── 2.jpg  รูปแทรกรูปที่สอง
└── 3.jpg  รูปแทรกรูปที่สาม
```

ตัวอย่างการแทรกรูปใน Markdown:

```markdown
![คำอธิบายรูป](2026-05-22-inv-post01/1.jpg "รูป Featured ในเนื้อหา")

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

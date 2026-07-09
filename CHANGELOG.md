# Changelog

All notable changes to `kppost` are documented here.

## [0.2.7] - 2026-07-09

### Changed

- `prepare` now rejects folder-level department codes unless a reusable
  completed `departments.json` mapping covers every inferred code.
- Starter `departments.json` templates are now limited to the fallback
  `--department-code` path and are not created for department codes found in
  raw folder names.
- Added an agent-facing project summary and updated version metadata for a
  stable `0.2.7` release.

### Safety

- Prevents accidental new department tags/categories from raw folder names
  flowing into generated batches.

## [0.2.6a] - 2026-07-08

### Changed

- Updated package and CLI version metadata to `0.2.6a`.

## [0.2.5] - 2026-06-08

### Added

- `prepare` supports generic source root names and defaults them to
  `batch-<source-name>` when no output is supplied.
- `prepare` can derive department codes from source subfolder names such as
  `260426-gen`, `260426-1630-gen`, and `260426-gen-1630`.
- Added `kppost post <batch>` as the preferred command for creating WordPress
  posts while keeping `kppost import <batch>` as an alias.
- Root CLI help now shows the recommended numbered workflow, including optional
  Canva steps.

### Changed

- Prepared post numbering is grouped by date and department code.
- Source root names no longer infer department codes.

## [0.2.4] - 2026-06-08

### Changed

- New manifests no longer derive an excerpt from the first Markdown paragraph.
- WordPress post creation no longer sends an `excerpt`; all Markdown blocks
  after the H1 remain in Gutenberg content for the user to manage on the site.
- The batch schema no longer includes the derived `excerpt` field.

## [0.2.3] - 2026-06-08

### Added

- `prepare` reuses completed `departments.json` mappings from the source root,
  parent `.kppost` cache, or a previous sibling batch.
- Completed department mappings are synced to
  `<source_parent>/.kppost/departments.json` for later prepare runs.
- `prepare-report.json` now records the departments source and cache path.

### Changed

- Blank starter `departments.json` templates are not saved to the departments
  cache.

## [0.2.2] - 2026-06-08

### Added

- `prepare` can read plain TXT source folders in addition to PPTX folders.
- `prepare` supports BE and Gregorian two-digit source dates, TXT/folder time
  suffixes, and department-code inference from roots such as `69-04-txt-gen`.
- `prepare` can omit the output argument and create a sibling `batch-YY-MM`
  directory from the source root name.
- Canva export workbooks now include a `YYMMDDHHMMSS` timestamp in their
  filenames.
- Agent working rules now require describing planned actions before work and
  asking for confirmation when requirements are unclear.

### Changed

- Documentation now covers TXT preparation, default prepare output naming, and
  timestamped Canva workbook names.

## [0.2.1] - 2026-06-07

### Added

- `prepare` creates a starter `departments.json` when the file does not exist.
- The starter uses the selected `--department-code` and leaves required
  WordPress mapping values blank for the user to complete.
- Top-level WordPress categories are supported by setting
  `wordpress_category_parent_slug` to `null`.

### Changed

- Category preflight verifies `parent: 0` when the configured parent slug is
  `null`.
- Empty parent strings are rejected; use a real slug or JSON `null`.
- Both development and packaged batch schemas accept a string or `null` parent.

## [0.2.0] - 2026-06-07

### Added

- Added `kppost canva export <batch> <output>`.
- Added `feature_images.xlsx` with title, page name, and Excel In-cell images.
- Added `news_image_watermark.xlsx` with page names and Excel In-cell images.
- Added `kppost canva import <batch> -f <feature.zip> -nw <news.zip>`.
- Added automatic matching of Canva ZIP images by Bulk Create page name.
- Added JPEG conversion, image replacement, Markdown image regeneration, rollback,
  and Canva import reports.
- Added Pillow and XlsxWriter dependencies.
- Added Canva workflow tests, including incomplete ZIP and rollback cases.

### Changed

- `prepare` now names copied images `<post-stem>-01`, `-02`, and so on.
- `prepare-report.json` records original and prepared image names.
- Prepared Markdown reserves image `1` for the Featured Image and initially
  references content images from `2.jpg`.
- Canva import writes `1.jpg` as both the WordPress Featured Image and the first
  inline Markdown image.
- Canva export accepts prepared image numbers with gaps and final numbered files
  such as `1.jpg`, `2.jpg`, and `3.jpg`.
- Documentation now covers the complete PowerPoint-to-WordPress workflow.

### Safety

- Canva ZIP contents are validated and decoded before batch files are changed.
- Canva import preserves non-image marker files.
- Canva import restores all original images and Markdown if a write fails.

## [0.1.0] - 2026-06-07

### Added

- Initial Markdown batch generation and validation.
- PowerPoint content preparation.
- Gutenberg rendering and WordPress REST API import.
- Existing-only taxonomy preflight.
- Media/post checkpoint and resume behavior.

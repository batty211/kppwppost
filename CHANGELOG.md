# Changelog

All notable changes to `kppost` are documented here.

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

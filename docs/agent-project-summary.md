# Agent Project Summary

This file is a short orientation note for coding agents. User-facing usage
instructions belong in `README.md`; normative behavior belongs in `SPEC.md`;
internal design details belong in `ARCHITECTURE.md`.

## What kppost does

`kppost` prepares reviewed field-report content for WordPress Posts. It can turn
raw PowerPoint or text folders into editable Markdown batches, organize images
for Canva watermarking, validate local taxonomy mappings, upload media, and
create draft posts through the WordPress REST API with checkpointed resume
behavior.

The current scope is intentionally limited to WordPress Posts and existing
categories/tags. It does not create taxonomy terms, update existing posts
outside the checkpoint, manage Pages, manage custom post types, provide a GUI,
or write SEO plugin fields.

## Safety model

- Local validation and taxonomy preflight must pass before WordPress writes.
- Categories and tags are existing-only and resolved by slug.
- Application Password values must never appear in logs, exceptions, or reports.
- Source images must not be renamed, deleted, or modified during import.
- Checkpoints must be written immediately after successful Media or Post
  creation so reruns do not duplicate remote data.

## Prepare behavior to preserve

`kppost prepare` is a working-area generator, not a final import validator. It
reads immediate child folders, extracts text from one PPTX or TXT per folder,
copies image files into prepared post directories, writes Markdown, and records
the source-to-output mapping in `prepare-report.json`.

Folder-level department codes such as `260426-gen` override `--department-code`,
but every folder-level code must already have a complete reusable
`departments.json` mapping. If not, `prepare` must stop before writing output.
Starter `departments.json` templates are allowed only for the fallback
`--department-code` path, not for department codes inferred from folder names.

## First files to read

1. `AGENTS.md` for working rules and test expectations.
2. `SPEC.md` for behavior that must not drift.
3. `ARCHITECTURE.md` for data flow and module responsibilities.
4. `CHANGELOG.md` for recent behavior changes.

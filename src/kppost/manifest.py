from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import ValidationError
from .files import atomic_write_json, load_json, relative_posix
from .markdown import (
    SUPPORTED_IMAGE_EXTENSIONS,
    parse_markdown,
    validate_image_signature,
)
from .models import Department


FILENAME_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-"
    r"(?P<code>[a-zA-Z0-9]+)-post(?P<number>\d{2})\.md$"
)


def load_departments(batch_root: Path) -> dict[str, Department]:
    data = load_json(batch_root / "departments.json")
    if not isinstance(data, dict) or not isinstance(data.get("departments"), list):
        raise ValidationError("departments.json must contain a departments array")
    errors: list[str] = []
    departments: dict[str, Department] = {}
    ids: set[str] = set()
    names: set[str] = set()
    for index, item in enumerate(data["departments"], start=1):
        if not isinstance(item, dict):
            errors.append(f"departments[{index}] must be an object")
            continue
        code = str(item.get("code", "")).strip().lower()
        department_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        category_slug = str(item.get("wordpress_category_slug", "")).strip()
        category_parent_slug = str(
            item.get("wordpress_category_parent_slug", "")
        ).strip()
        tag_slug = str(item.get("wordpress_tag_slug", "")).strip()
        if not code or not re.fullmatch(r"[a-z0-9]+", code):
            errors.append(f"departments[{index}].code must use a-z and 0-9")
        if not department_id:
            errors.append(f"departments[{index}].id is required")
        if not name:
            errors.append(f"departments[{index}].name is required")
        if not category_slug:
            errors.append(
                f"departments[{index}].wordpress_category_slug is required"
            )
        if not category_parent_slug:
            errors.append(
                f"departments[{index}].wordpress_category_parent_slug is required"
            )
        if not tag_slug:
            errors.append(f"departments[{index}].wordpress_tag_slug is required")
        if code in departments:
            errors.append(f"Duplicate department code: {code}")
        if department_id in ids:
            errors.append(f"Duplicate department id: {department_id}")
        if name.casefold() in names:
            errors.append(f"Duplicate department name: {name}")
        departments[code] = Department(
            code=code,
            id=department_id,
            name=name,
            wordpress_category_slug=category_slug,
            wordpress_category_parent_slug=category_parent_slug,
            wordpress_tag_slug=tag_slug,
        )
        ids.add(department_id)
        names.add(name.casefold())
    if errors:
        raise ValidationError(errors)
    if not departments:
        raise ValidationError("departments.json must define at least one department")
    return departments


def _featured_image(image_dir: Path, md_name: str) -> Path:
    if not image_dir.is_dir():
        raise ValidationError(f"{md_name}: missing image directory: {image_dir.name}")
    matches = [
        path
        for path in image_dir.iterdir()
        if path.is_file()
        and path.stem == "1"
        and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    if len(matches) != 1:
        raise ValidationError(
            f"{md_name}: expected exactly one featured image named 1.jpg, "
            f"1.jpeg, 1.png, or 1.webp; found {len(matches)}"
        )
    validate_image_signature(matches[0])
    return matches[0]


def build_manifest(batch_root: Path, status: str = "draft") -> dict[str, Any]:
    batch_root = batch_root.resolve()
    content_dir = batch_root / "content"
    if not content_dir.is_dir():
        raise ValidationError(f"Missing content directory: {content_dir}")
    departments = load_departments(batch_root)
    markdown_files = sorted(content_dir.glob("*.md"))
    if not markdown_files:
        raise ValidationError("No Markdown files found in content/")
    if len(markdown_files) > 100:
        raise ValidationError("A batch may contain at most 100 Markdown files")

    posts: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_keys: set[tuple[str, str, int]] = set()
    for md_path in markdown_files:
        match = FILENAME_PATTERN.fullmatch(md_path.name)
        if not match:
            errors.append(
                f"{md_path.name}: expected YYYY-MM-DD-DEPARTMENT_CODE-postNN.md"
            )
            continue
        raw_date = match.group("date")
        code = match.group("code").lower()
        number = int(match.group("number"))
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            errors.append(f"{md_path.name}: invalid date: {raw_date}")
            continue
        if number < 1:
            errors.append(f"{md_path.name}: post number must be 01-99")
            continue
        department = departments.get(code)
        if department is None:
            errors.append(f"{md_path.name}: unknown department code: {code}")
            continue
        unique_key = (raw_date, code, number)
        if unique_key in seen_keys:
            errors.append(f"{md_path.name}: duplicate date/department/post number")
            continue
        seen_keys.add(unique_key)
        try:
            parsed = parse_markdown(md_path, batch_root)
            featured = _featured_image(md_path.with_suffix(""), md_path.name)
        except ValidationError as exc:
            errors.extend(exc.messages)
            continue

        source_id = md_path.stem
        slug = (
            f"{parsed_date:%Y%m%d}-{department.code}-{department.id}-post{number:02d}"
        )
        posts.append(
            {
                "source_id": source_id,
                "title": parsed.title,
                "date": raw_date,
                "department_code": department.code,
                "department_id": department.id,
                "department_name": department.name,
                "post_number": number,
                "slug": slug,
                "content_file": relative_posix(batch_root, md_path),
                "featured_image": relative_posix(batch_root, featured),
                "excerpt": parsed.excerpt,
                "categories": [department.name],
                "tags": [f"{parsed_date:%Y-%m}", department.name],
                "wordpress_category_slug": department.wordpress_category_slug,
                "wordpress_category_parent_slug": (
                    department.wordpress_category_parent_slug
                ),
                "wordpress_tag_slugs": [
                    f"{parsed_date:%Y-%m}",
                    department.wordpress_tag_slug,
                ],
            }
        )
    if errors:
        raise ValidationError(errors)
    posts.sort(key=lambda item: (item["date"], item["department_code"], item["post_number"]))
    return {
        "schema_version": "1.0",
        "batch_id": batch_root.name,
        "status": status,
        "posts": posts,
    }


def schema_path() -> Path:
    packaged = Path(__file__).resolve().parent / "schemas" / "batch.schema.json"
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / "batch.schema.json"


def validate_manifest_data(manifest: dict[str, Any]) -> None:
    schema = load_json(schema_path())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda item: list(item.path))
    if errors:
        messages = []
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "manifest"
            messages.append(f"{location}: {error.message}")
        raise ValidationError(messages)


def validate_batch(batch_root: Path) -> dict[str, Any]:
    batch_root = batch_root.resolve()
    manifest = load_json(batch_root / "batch.json")
    validate_manifest_data(manifest)
    generated = build_manifest(batch_root, status=manifest["status"])
    if manifest != generated:
        raise ValidationError(
            "batch.json is stale or was edited inconsistently; run `kppost generate "
            f"{batch_root}` and review the generated preview"
        )
    return manifest


def generate_manifest(batch_root: Path, force: bool = False) -> tuple[Path, dict[str, Any]]:
    batch_root = batch_root.resolve()
    destination = batch_root / "batch.json"
    existing_status = "draft"
    if destination.exists():
        existing = load_json(destination)
        if isinstance(existing, dict) and existing.get("status") in {
            "draft",
            "pending",
            "publish",
        }:
            existing_status = existing["status"]
    manifest = build_manifest(batch_root, status=existing_status)
    validate_manifest_data(manifest)
    if destination.exists() and not force:
        destination = batch_root / ".bulkpost" / "generated-preview.json"
    atomic_write_json(destination, manifest)
    return destination, manifest

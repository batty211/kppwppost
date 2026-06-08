from __future__ import annotations

import json
from pathlib import Path

import pytest

from kppost.errors import ValidationError
from kppost.manifest import (
    build_manifest,
    generate_manifest,
    validate_batch,
    validate_manifest_data,
)


def test_build_manifest_from_directory(batch: Path) -> None:
    manifest = validate_batch(batch)
    post = manifest["posts"][0]

    assert manifest["batch_id"] == "daily-news"
    assert manifest["status"] == "draft"
    assert post["source_id"] == "2026-06-07-inv-post01"
    assert post["title"] == "รายงานผลการปฏิบัติงาน"
    assert "excerpt" not in post
    assert post["slug"] == "20260607-inv-01-post01"
    assert post["categories"] == ["งานสืบสวนปราบปราม"]
    assert post["tags"] == ["2026-06", "งานสืบสวนปราบปราม"]
    assert post["wordpress_category_slug"] == "investigation"
    assert post["wordpress_category_parent_slug"] == "activities"
    assert post["wordpress_tag_slugs"] == ["2026-06", "investigate"]
    assert post["featured_image"].endswith("/1.jpg")


def test_generate_creates_preview_without_overwrite(batch: Path) -> None:
    original = (batch / "batch.json").read_text(encoding="utf-8")
    destination, _ = generate_manifest(batch)

    assert destination == batch / ".bulkpost" / "generated-preview.json"
    assert (batch / "batch.json").read_text(encoding="utf-8") == original


def test_validate_detects_stale_manifest(batch: Path) -> None:
    manifest_path = batch / "batch.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["posts"][0]["title"] = "แก้เฉพาะ JSON"
    manifest_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValidationError, match="stale"):
        validate_batch(batch)


def test_rejects_duplicate_featured_extensions(batch: Path) -> None:
    image_dir = batch / "content" / "2026-06-07-inv-post01"
    (image_dir / "1.png").write_bytes(b"png")

    with pytest.raises(ValidationError, match="exactly one featured"):
        build_manifest(batch)


def test_rejects_unknown_department(batch: Path) -> None:
    source = batch / "content" / "2026-06-07-inv-post01.md"
    source.rename(batch / "content" / "2026-06-07-ops-post01.md")

    with pytest.raises(ValidationError, match="unknown department"):
        build_manifest(batch)


def test_build_manifest_allows_top_level_category(batch: Path) -> None:
    departments_path = batch / "departments.json"
    departments = json.loads(departments_path.read_text(encoding="utf-8"))
    departments["departments"][0]["wordpress_category_parent_slug"] = None
    departments_path.write_text(
        json.dumps(departments, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest = build_manifest(batch)
    validate_manifest_data(manifest)

    assert manifest["posts"][0]["wordpress_category_parent_slug"] is None


def test_rejects_empty_parent_category_slug(batch: Path) -> None:
    departments_path = batch / "departments.json"
    departments = json.loads(departments_path.read_text(encoding="utf-8"))
    departments["departments"][0]["wordpress_category_parent_slug"] = ""
    departments_path.write_text(
        json.dumps(departments, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="slug or null"):
        build_manifest(batch)

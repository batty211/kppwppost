from __future__ import annotations

from pathlib import Path

import pytest

from kppost.errors import ValidationError
from kppost.markdown import (
    parse_markdown,
    replace_markdown_images,
    render_gutenberg,
)
from kppost.models import UploadedMedia


def test_parse_and_render_gutenberg(batch: Path) -> None:
    md_path = batch / "content" / "2026-06-07-inv-post01.md"
    parsed = parse_markdown(md_path, batch)
    media = UploadedMedia(
        id=42,
        source_url="https://example.com/uploads/result.png",
        filename="20260607-inv-01-post01-02.png",
        sequence=2,
        source_path="content/2026-06-07-inv-post01/result.png",
        sha256="abc",
    )

    output = render_gutenberg(
        parsed,
        {"2026-06-07-inv-post01/result.png": media},
    )

    assert parsed.title == "รายงานผลการปฏิบัติงาน"
    assert parsed.excerpt == "ย่อหน้าแรกสำหรับ excerpt มี ตัวหนา"
    assert "<h1>" not in output
    assert "<!-- wp:paragraph -->" in output
    assert "<!-- wp:heading" in output
    assert "<!-- wp:list -->" in output
    assert '<!-- wp:image {"id":42' in output
    assert "คำบรรยาย" in output
    assert "https://example.com/uploads/result.png" in output


def test_rejects_image_mixed_with_paragraph_text(batch: Path) -> None:
    md_path = batch / "content" / "2026-06-07-inv-post01.md"
    text = md_path.read_text(encoding="utf-8")
    md_path.write_text(
        text.replace(
            "![ภาพผลการปฏิบัติงาน]",
            "ข้อความก่อนรูป ![ภาพผลการปฏิบัติงาน]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="own paragraph"):
        parse_markdown(md_path, batch)


def test_replaces_only_standalone_markdown_image_paragraphs(tmp_path: Path) -> None:
    md_path = tmp_path / "post.md"
    md_path.write_text(
        """# หัวข้อ

ข้อความก่อนรูป

![รูปเดิม](old/2.jpg)

ข้อความหลังรูป
""",
        encoding="utf-8",
    )

    replace_markdown_images(
        md_path,
        ["post/1.jpg", "post/2.jpg"],
    )

    assert md_path.read_text(encoding="utf-8") == """# หัวข้อ

ข้อความก่อนรูป


ข้อความหลังรูป

![ภาพผลการปฏิบัติงาน](post/1.jpg)

![ภาพผลการปฏิบัติงาน](post/2.jpg)
"""

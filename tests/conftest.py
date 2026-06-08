from __future__ import annotations

import json
from pathlib import Path

import pytest

from kppost.manifest import generate_manifest


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


@pytest.fixture
def batch(tmp_path: Path) -> Path:
    root = tmp_path / "daily-news"
    content = root / "content"
    image_dir = content / "2026-06-07-inv-post01"
    image_dir.mkdir(parents=True)
    (root / "departments.json").write_text(
        json.dumps(
            {
                "departments": [
                    {
                        "code": "inv",
                        "id": "01",
                        "name": "งานสืบสวนปราบปราม",
                        "wordpress_category_slug": "investigation",
                        "wordpress_category_parent_slug": "activities",
                        "wordpress_tag_slug": "investigate",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "2026-06-07-inv-post01.md").write_text(
        """# รายงานผลการปฏิบัติงาน

ย่อหน้าแรกของเนื้อหามี **ตัวหนา**

## รายละเอียด

- หนึ่ง
- สอง

![ภาพผลการปฏิบัติงาน](2026-06-07-inv-post01/result.png "คำบรรยาย")
""",
        encoding="utf-8",
    )
    (image_dir / "1.jpg").write_bytes(b"\xff\xd8\xff\xe0featured")
    (image_dir / "result.png").write_bytes(PNG_BYTES)
    generate_manifest(root)
    return root

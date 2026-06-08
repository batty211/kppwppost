from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from zipfile import ZipFile

import pytest

from kppost.errors import ValidationError
from kppost.prepare import (
    _write_department_template,
    default_output_root,
    extract_presentation_text,
    extract_plain_text,
    prepare_content,
)


def _write_pptx(path: Path, heading: str, body: str) -> None:
    slide = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="1" name="Heading"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="100"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:t>{heading}</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Body"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="200"/></a:xfrm></p:spPr>
        <p:txBody><a:p>
          <a:r><a:t>{body[:20]}</a:t></a:r>
          <a:r><a:t>{body[20:]}</a:t></a:r>
        </a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", slide)


def _source_folder(
    root: Path,
    name: str,
    heading: str,
    body: str,
    image_name: str = "original.jpg",
) -> Path:
    folder = root / name
    folder.mkdir()
    _write_pptx(folder / "report.pptx", heading, body)
    (folder / image_name).write_bytes(b"\xff\xd8\xff\xe0image")
    return folder


def test_extracts_text_runs_and_event_time(tmp_path: Path) -> None:
    pptx = tmp_path / "sample.pptx"
    _write_pptx(
        pptx,
        "2. การดำเนินการตาม มาตรา 38",
        "ภายใต้การอำนวยการ ทดสอบ เวลา 11.00 น. ณ ลลิดา รีสอร์ท",
    )

    extracted = extract_presentation_text(pptx)

    assert extracted.heading == "2. การดำเนินการตาม มาตรา 38"
    assert extracted.body == (
        "ภายใต้การอำนวยการ ทดสอบ เวลา 11.00 น. ณ ลลิดา รีสอร์ท"
    )
    assert extracted.event_time.isoformat() == "11:00:00"


def test_extracts_plain_text_heading_body_and_event_time(tmp_path: Path) -> None:
    text_file = tmp_path / "260401-1630.txt"
    text_file.write_text(
        "\ufeffหัวข้อข่าว\n\nภายใต้การอำนวยการ เวลา 16.30 น.\nตรวจสอบเรียบร้อย\n",
        encoding="utf-8",
    )

    extracted = extract_plain_text(text_file, fallback_time=time(0, 0))

    assert extracted.heading == "หัวข้อข่าว"
    assert extracted.body == "ภายใต้การอำนวยการ เวลา 16.30 น.\nตรวจสอบเรียบร้อย"
    assert extracted.event_time.isoformat() == "16:30:00"


def test_default_output_root_uses_source_month(tmp_path: Path) -> None:
    assert default_output_root(tmp_path / "69-04-txt-gen") == tmp_path / "batch-69-04"
    assert default_output_root(tmp_path / "26-04") == tmp_path / "batch-26-04"


def test_default_output_root_requires_source_month(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="YY-MM"):
        default_output_root(tmp_path / "source")


def test_prepares_posts_in_event_time_order_and_reports_skips(
    tmp_path: Path,
) -> None:
    source = tmp_path / "69-05"
    source.mkdir()
    _source_folder(
        source,
        "690507-ม38 รอบสาย",
        "2. การดำเนินการตาม มาตรา 38",
        "ภายใต้การอำนวยการ เวลา 11.00 น. ตรวจสอบ รอบสาย เรียบร้อย",
    )
    morning = _source_folder(
        source,
        "690507-ม38 รอบเช้า",
        "2. การดำเนินการตาม มาตรา 38",
        "ภายใต้การอำนวยการ เวลา 09.30 น. ตรวจสอบ รอบเช้า เรียบร้อย",
        image_name="photo.png",
    )
    (morning / "second.jpg").write_bytes(b"\xff\xd8\xff\xe0image")
    (morning / "third.webp").write_bytes(b"RIFFxxxxWEBPimage")
    skipped = source / "690508-ม38 ไม่มีสไลด์"
    skipped.mkdir()
    (skipped / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0image")
    output = tmp_path / "batch-content-ready"

    report = prepare_content(source, output)

    assert report["prepared"] == 2
    assert report["skipped"] == [
        {
            "source_folder": "690508-ม38 ไม่มีสไลด์",
            "reason": "no PPTX or TXT file",
        }
    ]
    posts = report["posts"]
    assert [post["source_folder"] for post in posts] == [
        "690507-ม38 รอบเช้า",
        "690507-ม38 รอบสาย",
    ]
    assert [post["post_stem"] for post in posts] == [
        "2026-05-07-inv-post01",
        "2026-05-07-inv-post02",
    ]
    assert [post["subject_highlight"] for post in posts] == ["inline", "inline"]

    content = output / "content"
    first_dir = content / "2026-05-07-inv-post01"
    marker = first_dir / "690507-ม38 รอบเช้า.txt"
    assert marker.is_file()
    assert marker.read_bytes() == b""
    assert (first_dir / "2026-05-07-inv-post01-01.png").is_file()
    assert (first_dir / "2026-05-07-inv-post01-02.jpg").is_file()
    assert (first_dir / "2026-05-07-inv-post01-03.webp").is_file()
    assert posts[0]["copied_images"] == [
        {
            "source": "photo.png",
            "prepared": "2026-05-07-inv-post01-01.png",
        },
        {
            "source": "second.jpg",
            "prepared": "2026-05-07-inv-post01-02.jpg",
        },
        {
            "source": "third.webp",
            "prepared": "2026-05-07-inv-post01-03.webp",
        },
    ]

    markdown = (content / "2026-05-07-inv-post01.md").read_text(
        encoding="utf-8"
    )
    assert markdown.startswith("# 2. การดำเนินการตาม มาตรา 38\n")
    assert "**รอบเช้า**" in markdown
    assert "(2026-05-07-inv-post01/2.jpg)" in markdown
    assert "(2026-05-07-inv-post01/3.jpg)" in markdown
    assert "(2026-05-07-inv-post01/1.jpg)" not in markdown

    saved_report = json.loads(
        (output / "prepare-report.json").read_text(encoding="utf-8")
    )
    assert saved_report["prepared"] == 2
    assert saved_report["departments_file"] == str(output / "departments.json")
    assert json.loads(
        (output / "departments.json").read_text(encoding="utf-8")
    ) == {
        "departments": [
            {
                "code": "inv",
                "id": "",
                "name": "",
                "wordpress_category_slug": "",
                "wordpress_category_parent_slug": None,
                "wordpress_tag_slug": "",
            }
        ]
    }


def test_prepares_plain_text_sources_and_infers_department_from_source_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "69-04-txt-gen"
    source.mkdir()
    first = source / "260401"
    first.mkdir()
    (first / "260401-1630.txt").write_text(
        "ประกาศผลการตรวจ\n\nภายใต้การอำนวยการ เวลา 16.30 น. ตรวจสอบเรียบร้อย\n",
        encoding="utf-8",
    )
    (first / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0image")
    second = source / "690401"
    second.mkdir()
    (second / "690401.txt").write_text(
        "รายงานไม่มีเวลา\n\nเนื้อหาจากไฟล์ข้อความธรรมดา\n",
        encoding="utf-8",
    )
    (second / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    skipped = source / "690402-empty"
    skipped.mkdir()

    output = tmp_path / "ready"
    report = prepare_content(source, output)

    assert report["department_code"] == "gen"
    assert report["prepared"] == 2
    assert report["skipped"] == [
        {
            "source_folder": "690402-empty",
            "reason": "no PPTX or TXT file",
        }
    ]
    assert [post["source_folder"] for post in report["posts"]] == [
        "690401",
        "260401",
    ]
    assert [post["post_stem"] for post in report["posts"]] == [
        "2026-04-01-gen-post01",
        "2026-04-01-gen-post02",
    ]
    assert report["posts"][0]["txt"] == "690401.txt"
    assert report["posts"][1]["txt"] == "260401-1630.txt"

    markdown = (output / "content/2026-04-01-gen-post02.md").read_text(
        encoding="utf-8"
    )
    assert markdown.startswith("# ประกาศผลการตรวจ\n\n")
    assert "ภายใต้การอำนวยการ เวลา 16.30 น. ตรวจสอบเรียบร้อย" in markdown
    assert (output / "content/2026-04-01-gen-post02/260401.txt").is_file()
    assert (
        output / "content/2026-04-01-gen-post02/2026-04-01-gen-post02-01.jpg"
    ).is_file()


def test_department_template_does_not_overwrite_existing_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "departments.json"
    destination.write_text('{"existing": true}\n', encoding="utf-8")

    result = _write_department_template(tmp_path, "ops")

    assert result == destination
    assert destination.read_text(encoding="utf-8") == '{"existing": true}\n'


def test_converts_heic_copy_to_jpg(tmp_path: Path) -> None:
    source = tmp_path / "69-05"
    source.mkdir()
    folder = _source_folder(
        source,
        "690521_ปรับ ม38 1 THA",
        "2. การดำเนินการตาม มาตรา 38",
        "ภายใต้การอำนวยการ เวลา 10.00 น. ตรวจสอบ 1 THA",
    )
    (folder / "camera.HEIC").write_bytes(b"heic")
    conversions: list[tuple[Path, Path]] = []

    def convert_heic(source_path: Path, destination: Path) -> None:
        conversions.append((source_path, destination))
        destination.write_bytes(b"\xff\xd8\xff\xe0converted")

    output = tmp_path / "ready"
    prepare_content(source, output, heic_converter=convert_heic)

    assert conversions == [
        (
            folder / "camera.HEIC",
            output
            / "content/2026-05-21-inv-post01/2026-05-21-inv-post01-01.jpg",
        )
    ]
    assert (
        output / "content/2026-05-21-inv-post01/2026-05-21-inv-post01-01.jpg"
    ).read_bytes().startswith(b"\xff\xd8\xff")
    assert not (
        output / "content/2026-05-21-inv-post01/camera.HEIC"
    ).exists()
    markdown = (
        output / "content/2026-05-21-inv-post01.md"
    ).read_text(encoding="utf-8")
    assert "**1 THA**" in markdown


def test_adds_reference_when_folder_subject_does_not_match_body(
    tmp_path: Path,
) -> None:
    source = tmp_path / "69-05"
    source.mkdir()
    _source_folder(
        source,
        "690507-ม38 โรงแรมจัสมิน ลอดจ์",
        "2. การดำเนินการตาม มาตรา 38",
        "ภายใต้การอำนวยการ เวลา 09.00 น. ตรวจสอบ Jasmine Lodge",
    )
    output = tmp_path / "ready"

    report = prepare_content(source, output)

    markdown = (
        output / "content/2026-05-07-inv-post01.md"
    ).read_text(encoding="utf-8")
    assert "**ข้อมูลอ้างอิง: โรงแรมจัสมิน ลอดจ์**" in markdown
    assert report["posts"][0]["subject_highlight"] == "reference"


def test_refuses_to_overwrite_output_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "ready"
    output.mkdir()

    with pytest.raises(ValidationError, match="already exists"):
        prepare_content(source, output)

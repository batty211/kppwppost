from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from kppost.errors import ValidationError
from kppost.prepare import extract_presentation_text, prepare_content


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
            "reason": "no PPTX file",
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

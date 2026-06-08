from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

import kppost.canva
from kppost.canva import export_canva_assets, import_canva_assets
from kppost.errors import ValidationError


def _image_bytes(
    image_format: str = "PNG",
    color: tuple[int, int, int] = (30, 90, 150),
) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(output, format=image_format)
    return output.getvalue()


def _post(
    content: Path,
    stem: str,
    title: str,
    image_numbers: tuple[int, ...],
) -> None:
    (content / f"{stem}.md").write_text(
        f"# {title}\n\nเนื้อหาที่ตรวจแล้ว\n\n"
        f"![รูปเดิม]({stem}/old.jpg)\n",
        encoding="utf-8",
    )
    image_dir = content / stem
    image_dir.mkdir()
    stem_color = sum(stem.encode("utf-8")) % 255
    for number in image_numbers:
        (image_dir / f"{stem}-{number:02d}.png").write_bytes(
            _image_bytes(color=(number, 90, stem_color))
        )
    (image_dir / "source-folder.txt").write_text("", encoding="utf-8")


def _xlsx_text(path: Path) -> str:
    with ZipFile(path) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith(".xml")
        )


def _xlsx_media_count(path: Path) -> int:
    with ZipFile(path) as archive:
        return len(
            [name for name in archive.namelist() if name.startswith("xl/media/")]
        )


def _write_zip(path: Path, images: dict[str, bytes]) -> None:
    with ZipFile(path, "w") as archive:
        for name, data in images.items():
            archive.writestr(f"Canva export/{name}.png", data)


def test_exports_two_workbooks_with_in_cell_images(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    content = batch / "content"
    content.mkdir(parents=True)
    _post(content, "2026-05-07-inv-post02", "หัวข้อที่สอง", (1, 6))
    _post(content, "2026-05-07-inv-post01", "หัวข้อแรก", (1, 8, 10))
    output = tmp_path / "canva"

    result = export_canva_assets(
        batch,
        output,
        exported_at=datetime(2026, 4, 9, 17, 5, 3),
    )

    feature_path = output / "feature_images_260409170503.xlsx"
    news_path = output / "news_image_watermark_260409170503.xlsx"
    assert result == {
        "posts": 2,
        "news_images": 3,
        "feature_workbook": str(feature_path),
        "news_workbook": str(news_path),
    }
    assert _xlsx_media_count(feature_path) == 2
    assert _xlsx_media_count(news_path) == 3
    feature_xml = _xlsx_text(feature_path)
    news_xml = _xlsx_text(news_path)
    assert "หัวข้อ" in feature_xml
    assert "ชื่อไฟล์รูปภาพ" in feature_xml
    assert "รูปภาพ" in feature_xml
    assert "2026-05-07-inv-post01-01" in feature_xml
    assert "2026-05-07-inv-post02-01" in feature_xml
    assert "2026-05-07-inv-post01-02" in news_xml
    assert "2026-05-07-inv-post01-03" in news_xml
    assert "2026-05-07-inv-post02-02" in news_xml
    with ZipFile(feature_path) as archive:
        assert any(name.startswith("xl/richData/") for name in archive.namelist())


def test_imports_two_zips_replaces_images_and_markdown(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    content = batch / "content"
    content.mkdir(parents=True)
    stem = "2026-05-07-inv-post01"
    _post(content, stem, "หัวข้อ", (1, 8, 10))
    feature_zip = tmp_path / "(BULK) feature.zip"
    news_zip = tmp_path / "anything.zip"
    _write_zip(feature_zip, {f"{stem}-01": _image_bytes(color=(255, 0, 0))})
    _write_zip(
        news_zip,
        {
            f"{stem}-02": _image_bytes(color=(0, 255, 0)),
            f"{stem}-03": _image_bytes(color=(0, 0, 255)),
        },
    )

    result = import_canva_assets(batch, feature_zip, news_zip)

    image_dir = content / stem
    assert sorted(path.name for path in image_dir.iterdir()) == [
        "1.jpg",
        "2.jpg",
        "3.jpg",
        "source-folder.txt",
    ]
    for number in range(1, 4):
        with Image.open(image_dir / f"{number}.jpg") as image:
            assert image.format == "JPEG"
    markdown = (content / f"{stem}.md").read_text(encoding="utf-8")
    assert "เนื้อหาที่ตรวจแล้ว" in markdown
    assert "old.jpg" not in markdown
    assert f"({stem}/1.jpg)" in markdown
    assert f"({stem}/2.jpg)" in markdown
    assert f"({stem}/3.jpg)" in markdown
    assert result["posts"] == [
        {
            "post_stem": stem,
            "images": ["1.jpg", "2.jpg", "3.jpg"],
        }
    ]
    assert Path(result["report_path"]).is_file()


def test_rejects_incomplete_zip_before_changing_batch(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    content = batch / "content"
    content.mkdir(parents=True)
    stem = "2026-05-07-inv-post01"
    _post(content, stem, "หัวข้อ", (1, 2))
    markdown_path = content / f"{stem}.md"
    image_path = content / stem / f"{stem}-01.png"
    original_markdown = markdown_path.read_bytes()
    original_image = image_path.read_bytes()
    feature_zip = tmp_path / "feature.zip"
    news_zip = tmp_path / "news.zip"
    _write_zip(feature_zip, {f"{stem}-01": _image_bytes()})
    _write_zip(news_zip, {"wrong-name": _image_bytes()})

    with pytest.raises(ValidationError, match="missing images"):
        import_canva_assets(batch, feature_zip, news_zip)

    assert markdown_path.read_bytes() == original_markdown
    assert image_path.read_bytes() == original_image


def test_rolls_back_every_post_when_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = tmp_path / "batch"
    content = batch / "content"
    content.mkdir(parents=True)
    stems = ("2026-05-07-inv-post01", "2026-05-07-inv-post02")
    for stem in stems:
        _post(content, stem, f"หัวข้อ {stem}", (1, 2))
    original_files = {
        path: path.read_bytes()
        for path in content.rglob("*")
        if path.is_file()
    }
    feature_zip = tmp_path / "feature.zip"
    news_zip = tmp_path / "news.zip"
    _write_zip(
        feature_zip,
        {f"{stem}-01": _image_bytes() for stem in stems},
    )
    _write_zip(
        news_zip,
        {f"{stem}-02": _image_bytes() for stem in stems},
    )

    def fail_replace(path: Path, sources: list[str]) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(kppost.canva, "replace_markdown_images", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        import_canva_assets(batch, feature_zip, news_zip)

    assert {
        path: path.read_bytes()
        for path in content.rglob("*")
        if path.is_file()
    } == original_files


def test_can_export_again_after_import_uses_final_numbered_images(
    tmp_path: Path,
) -> None:
    batch = tmp_path / "batch"
    content = batch / "content"
    content.mkdir(parents=True)
    stem = "2026-05-07-inv-post01"
    _post(content, stem, "หัวข้อ", (1, 2))
    feature_zip = tmp_path / "feature.zip"
    news_zip = tmp_path / "news.zip"
    _write_zip(feature_zip, {f"{stem}-01": _image_bytes()})
    _write_zip(news_zip, {f"{stem}-02": _image_bytes()})
    import_canva_assets(batch, feature_zip, news_zip)

    result = export_canva_assets(batch, tmp_path / "canva-again")

    assert result["posts"] == 1
    assert result["news_images"] == 1
    assert re.search(
        r"feature_images_\d{12}\.xlsx$",
        result["feature_workbook"],
    )
    assert re.search(
        r"news_image_watermark_\d{12}\.xlsx$",
        result["news_workbook"],
    )


def test_rejects_post_without_featured_image_number_one(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    content = batch / "content"
    content.mkdir(parents=True)
    stem = "2026-05-07-inv-post01"
    _post(content, stem, "หัวข้อ", (2,))

    with pytest.raises(ValidationError, match="missing Featured Image"):
        export_canva_assets(batch, tmp_path / "canva")


def test_refuses_to_overwrite_canva_output(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    (batch / "content").mkdir(parents=True)
    output = tmp_path / "canva"
    output.mkdir()

    with pytest.raises(ValidationError, match="already exists"):
        export_canva_assets(batch, output)

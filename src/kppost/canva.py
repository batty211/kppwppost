from __future__ import annotations

import io
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import xlsxwriter
from PIL import Image, UnidentifiedImageError

from .errors import ValidationError
from .files import atomic_write_json
from .markdown import parse_markdown_title, replace_markdown_images


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class CanvaPost:
    stem: str
    markdown_path: Path
    title: str
    images: list[Path]


def _ordered_images(image_dir: Path, post_stem: str) -> list[Path]:
    prepared_pattern = re.compile(
        rf"^{re.escape(post_stem)}-(?P<number>\d{{2}})"
        rf"(?P<extension>\.jpe?g|\.png|\.webp)$",
        re.IGNORECASE,
    )
    final_pattern = re.compile(
        r"^(?P<number>\d+)(?P<extension>\.jpe?g|\.png|\.webp)$",
        re.IGNORECASE,
    )
    numbered: list[tuple[int, Path]] = []
    for path in image_dir.iterdir():
        if not path.is_file():
            continue
        match = prepared_pattern.fullmatch(path.name)
        if match:
            numbered.append((int(match.group("number")), path))
    if not numbered:
        for path in image_dir.iterdir():
            if not path.is_file():
                continue
            match = final_pattern.fullmatch(path.name)
            if match:
                numbered.append((int(match.group("number")), path))

    numbered.sort(key=lambda item: item[0])
    if not numbered:
        raise ValidationError(
            f"{post_stem}: no prepared images named {post_stem}-01, -02, ... were found"
        )
    if numbered[0][0] != 1:
        raise ValidationError(
            f"{post_stem}: missing Featured Image named {post_stem}-01"
        )
    numbers = [number for number, _ in numbered]
    if len(numbers) != len(set(numbers)):
        raise ValidationError(f"{post_stem}: duplicate image sequence number")
    return [path for _, path in numbered]


def _collect_posts(batch_root: Path) -> list[CanvaPost]:
    content_root = batch_root / "content"
    if not content_root.is_dir():
        raise ValidationError(f"Missing content directory: {content_root}")
    markdown_files = sorted(content_root.glob("*.md"), key=lambda path: path.name)
    if not markdown_files:
        raise ValidationError(f"No Markdown files found in: {content_root}")

    posts: list[CanvaPost] = []
    errors: list[str] = []
    for markdown_path in markdown_files:
        post_stem = markdown_path.stem
        try:
            image_dir = content_root / post_stem
            if not image_dir.is_dir():
                raise ValidationError(
                    f"{markdown_path.name}: missing image directory: {post_stem}"
                )
            posts.append(
                CanvaPost(
                    stem=post_stem,
                    markdown_path=markdown_path,
                    title=parse_markdown_title(markdown_path),
                    images=_ordered_images(image_dir, post_stem),
                )
            )
        except ValidationError as exc:
            errors.extend(exc.messages)
    if errors:
        raise ValidationError(errors)
    return posts


def _xlsx_image(path: Path, image_name: str) -> tuple[str, io.BytesIO]:
    try:
        with Image.open(path) as image:
            image.load()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                output = io.BytesIO(path.read_bytes())
                filename = f"{image_name}{path.suffix.lower()}"
            else:
                output = io.BytesIO()
                image.convert("RGBA").save(output, format="PNG")
                filename = f"{image_name}.png"
    except (OSError, UnidentifiedImageError) as exc:
        raise ValidationError(f"Cannot embed image in XLSX: {path}") from exc
    output.seek(0)
    return filename, output


def _write_feature_workbook(path: Path, posts: list[CanvaPost]) -> None:
    workbook = xlsxwriter.Workbook(path)
    try:
        sheet = workbook.add_worksheet("Feature Images")
        header = workbook.add_format({"bold": True, "bg_color": "#E2E8F0"})
        sheet.write_row(0, 0, ["หัวข้อ", "ชื่อไฟล์รูปภาพ", "รูปภาพ"], header)
        sheet.set_column("A:A", 60)
        sheet.set_column("B:B", 38)
        sheet.set_column("C:C", 24)
        sheet.freeze_panes(1, 0)
        for row, post in enumerate(posts, start=1):
            image_name = f"{post.stem}-01"
            sheet.write(row, 0, post.title)
            sheet.write(row, 1, image_name)
            sheet.set_row(row, 120)
            image_filename, image_data = _xlsx_image(post.images[0], image_name)
            sheet.embed_image(
                row,
                2,
                image_filename,
                {
                    "image_data": image_data,
                    "description": image_name,
                    "x_scale": 0.25,
                    "y_scale": 0.25,
                },
            )
    finally:
        workbook.close()


def _write_news_workbook(path: Path, posts: list[CanvaPost]) -> int:
    workbook = xlsxwriter.Workbook(path)
    count = 0
    try:
        sheet = workbook.add_worksheet("News Watermarks")
        header = workbook.add_format({"bold": True, "bg_color": "#E2E8F0"})
        sheet.write_row(0, 0, ["ชื่อไฟล์รูปภาพ", "รูปภาพ"], header)
        sheet.set_column("A:A", 38)
        sheet.set_column("B:B", 24)
        sheet.freeze_panes(1, 0)
        for post in posts:
            for image_number, source in enumerate(post.images[1:], start=2):
                image_name = f"{post.stem}-{image_number:02d}"
                row = count + 1
                sheet.write(row, 0, image_name)
                sheet.set_row(row, 120)
                image_filename, image_data = _xlsx_image(source, image_name)
                sheet.embed_image(
                    row,
                    1,
                    image_filename,
                    {
                        "image_data": image_data,
                        "description": image_name,
                        "x_scale": 0.25,
                        "y_scale": 0.25,
                    },
                )
                count += 1
    finally:
        workbook.close()
    return count


def _timestamp_suffix(value: datetime) -> str:
    return value.strftime("%y%m%d%H%M%S")


def export_canva_assets(
    batch_root: Path,
    output_root: Path,
    exported_at: datetime | None = None,
) -> dict[str, object]:
    batch_root = batch_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise ValidationError(f"Output directory already exists: {output_root}")

    posts = _collect_posts(batch_root)
    output_root.mkdir(parents=True)
    timestamp = _timestamp_suffix(exported_at or datetime.now())
    feature_path = output_root / f"feature_images_{timestamp}.xlsx"
    news_path = output_root / f"news_image_watermark_{timestamp}.xlsx"
    try:
        _write_feature_workbook(feature_path, posts)
        news_count = _write_news_workbook(news_path, posts)
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise
    return {
        "posts": len(posts),
        "news_images": news_count,
        "feature_workbook": str(feature_path),
        "news_workbook": str(news_path),
    }


def _zip_images(path: Path) -> dict[str, bytes]:
    images: dict[str, bytes] = {}
    try:
        with ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename.startswith("__MACOSX/"):
                    continue
                member_path = Path(member.filename)
                if member_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                key = member_path.stem.casefold()
                if key in images:
                    raise ValidationError(
                        f"{path.name}: duplicate image name in ZIP: {member_path.stem}"
                    )
                images[key] = archive.read(member)
    except (BadZipFile, OSError) as exc:
        raise ValidationError(f"Cannot read ZIP file: {path}") from exc
    if not images:
        raise ValidationError(f"{path.name}: ZIP contains no supported images")
    return images


def _jpeg_bytes(data: bytes, label: str) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            converted = image.convert("RGB")
            output = io.BytesIO()
            converted.save(output, format="JPEG", quality=95)
    except (OSError, UnidentifiedImageError) as exc:
        raise ValidationError(f"Cannot decode Canva image: {label}") from exc
    return output.getvalue()


def _final_markdown_sources(post_stem: str, image_count: int) -> list[str]:
    return [f"{post_stem}/{number}.jpg" for number in range(1, image_count + 1)]


def _require_exact_images(
    provided: dict[str, bytes],
    expected: list[str],
    label: str,
) -> dict[str, bytes]:
    expected_keys = {name.casefold(): name for name in expected}
    missing = [
        name for key, name in expected_keys.items() if key not in provided
    ]
    unexpected = [
        key for key in provided if key not in expected_keys
    ]
    errors: list[str] = []
    if missing:
        errors.append(f"{label}: missing images: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{label}: unexpected images: {', '.join(unexpected)}")
    if errors:
        raise ValidationError(errors)
    return {
        expected_keys[key]: _jpeg_bytes(provided[key], expected_keys[key])
        for key in expected_keys
    }


def import_canva_assets(
    batch_root: Path,
    feature_zip: Path,
    news_zip: Path,
) -> dict[str, object]:
    batch_root = batch_root.resolve()
    posts = _collect_posts(batch_root)
    feature_names = [f"{post.stem}-01" for post in posts]
    news_names = [
        f"{post.stem}-{number:02d}"
        for post in posts
        for number in range(2, len(post.images) + 1)
    ]
    feature_images = _require_exact_images(
        _zip_images(feature_zip.resolve()),
        feature_names,
        "Feature ZIP",
    )
    news_images = _require_exact_images(
        _zip_images(news_zip.resolve()),
        news_names,
        "News watermark ZIP",
    )

    with tempfile.TemporaryDirectory(prefix=".canva-import-", dir=batch_root) as temp:
        staging_root = Path(temp)
        for post in posts:
            post_stage = staging_root / post.stem
            post_stage.mkdir()
            (post_stage / "1.jpg").write_bytes(
                feature_images[f"{post.stem}-01"]
            )
            for number in range(2, len(post.images) + 1):
                name = f"{post.stem}-{number:02d}"
                (post_stage / f"{number}.jpg").write_bytes(news_images[name])

        backups: dict[Path, bytes] = {
            post.markdown_path: post.markdown_path.read_bytes() for post in posts
        }
        old_images: dict[Path, bytes] = {
            path: path.read_bytes()
            for post in posts
            for path in (batch_root / "content" / post.stem).iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        }
        try:
            for post in posts:
                image_dir = batch_root / "content" / post.stem
                for path in image_dir.iterdir():
                    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                        path.unlink()
                staged = staging_root / post.stem
                for source in sorted(staged.iterdir()):
                    shutil.copy2(source, image_dir / source.name)
                # Normalize prepared Markdown references to final numbered images.
                replace_markdown_images(
                    post.markdown_path,
                    _final_markdown_sources(post.stem, len(post.images)),
                )
        except Exception:
            for post in posts:
                image_dir = batch_root / "content" / post.stem
                for path in image_dir.iterdir():
                    if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                        path.unlink()
                for path, data in old_images.items():
                    if path.parent == image_dir:
                        path.write_bytes(data)
                post.markdown_path.write_bytes(backups[post.markdown_path])
            raise

    report = {
        "feature_zip": str(feature_zip.resolve()),
        "news_zip": str(news_zip.resolve()),
        "posts": [
            {
                "post_stem": post.stem,
                "images": [f"{number}.jpg" for number in range(1, len(post.images) + 1)],
            }
            for post in posts
        ],
    }
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = (
        batch_root / ".bulkpost" / "reports" / f"canva-import-{timestamp}.json"
    )
    atomic_write_json(report_path, report)
    report["report_path"] = str(report_path)
    return report

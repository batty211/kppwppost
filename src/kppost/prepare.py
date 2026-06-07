from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .errors import ValidationError


DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": DRAWING_NS, "p": PRESENTATION_NS}
RAW_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
BODY_PREFIX = "ภายใต้การอำนวยการ"
TIME_PATTERN = re.compile(r"เวลา\s*(\d{1,2})[.:](\d{2})\s*น\.")
SOURCE_NAME_PATTERN = re.compile(
    r"^(?P<year>\d{2})(?P<month>\d{2})(?P<day>\d{2})(?:[-_ ]|$)"
)
SUBJECT_PREFIXES = (
    "ปรับ ม38",
    "สุ่มตรวจ",
    "ท้องถิ่น",
    "ม38",
)


@dataclass(frozen=True)
class PresentationText:
    heading: str
    body: str
    event_time: time


@dataclass(frozen=True)
class PreparedSource:
    source_dir: Path
    post_date: date
    presentation: Path
    text: PresentationText


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _slide_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"slide(\d+)\.xml$", name)
    return (int(match.group(1)) if match else 0, name)


def _shape_position(shape: ElementTree.Element) -> tuple[int, int]:
    offset = shape.find("p:spPr/a:xfrm/a:off", NS)
    if offset is None:
        return (0, 0)
    return (int(offset.get("y", "0")), int(offset.get("x", "0")))


def extract_presentation_text(path: Path) -> PresentationText:
    try:
        with ZipFile(path) as archive:
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                ),
                key=_slide_sort_key,
            )
            shape_texts: list[str] = []
            for slide_name in slide_names:
                root = ElementTree.fromstring(archive.read(slide_name))
                shapes = sorted(root.findall(".//p:sp", NS), key=_shape_position)
                for shape in shapes:
                    text = _normalize_text(
                        "".join(
                            node.text or ""
                            for node in shape.findall(".//a:t", NS)
                        )
                    )
                    if text:
                        shape_texts.append(text)
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValidationError(f"Cannot read PowerPoint file {path}: {exc}") from exc

    body = next(
        (text for text in shape_texts if text.startswith(BODY_PREFIX)),
        "",
    )
    if not body:
        raise ValidationError(
            f"{path.name}: cannot find body text beginning with {BODY_PREFIX!r}"
        )

    body_index = shape_texts.index(body)
    heading_candidates = [
        text
        for text in shape_texts[:body_index]
        if text != "ตม.จว.กำแพงเพชร"
    ]
    if not heading_candidates:
        raise ValidationError(f"{path.name}: cannot find the main heading")
    heading = max(heading_candidates, key=len)

    time_match = TIME_PATTERN.search(body)
    if time_match is None:
        raise ValidationError(f"{path.name}: cannot find an event time in body text")
    hour, minute = (int(value) for value in time_match.groups())
    try:
        event_time = time(hour, minute)
    except ValueError as exc:
        raise ValidationError(f"{path.name}: invalid event time {hour}:{minute:02d}") from exc
    return PresentationText(heading=heading, body=body, event_time=event_time)


def _source_date(name: str) -> date:
    match = SOURCE_NAME_PATTERN.match(name)
    if match is None:
        raise ValidationError(
            f"{name}: expected folder name to begin with a YYMMDD date"
        )
    buddhist_year = 2500 + int(match.group("year"))
    try:
        return date(
            buddhist_year - 543,
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError as exc:
        raise ValidationError(f"{name}: invalid date prefix") from exc


def _subject_from_folder(name: str) -> str:
    subject = SOURCE_NAME_PATTERN.sub("", name, count=1).strip(" -_")
    for prefix in SUBJECT_PREFIXES:
        if subject.startswith(prefix):
            subject = subject[len(prefix) :].strip(" -_")
            break
    return _normalize_text(subject)


def _emphasize_subject(body: str, folder_name: str) -> tuple[str, str]:
    subject = _subject_from_folder(folder_name)
    if not subject:
        return body, "none"
    words = subject.split()
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE)
    match = pattern.search(body)
    if match is None:
        return f"**ข้อมูลอ้างอิง: {subject}**\n\n{body}", "reference"
    return (
        f"{body[:match.start()]}**{match.group()}**{body[match.end():]}",
        "inline",
    )


def _convert_heic_with_sips(source: Path, destination: Path) -> None:
    command = shutil.which("sips")
    if command is None:
        raise ValidationError(
            f"Cannot convert HEIC without macOS sips: {source}"
        )
    result = subprocess.run(
        [command, "-s", "format", "jpeg", source, "--out", destination],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValidationError(f"HEIC conversion failed for {source}: {detail}")


def _markdown(heading: str, body: str, post_stem: str, image_count: int) -> str:
    image_blocks = "\n\n".join(
        f"![ภาพผลการปฏิบัติงาน]({post_stem}/{number}.jpg)"
        for number in range(2, image_count + 1)
    )
    suffix = f"\n\n{image_blocks}" if image_blocks else ""
    return f"# {heading}\n\n{body}{suffix}\n"


def _scan_sources(source_root: Path) -> tuple[list[PreparedSource], list[dict[str, str]]]:
    prepared: list[PreparedSource] = []
    skipped: list[dict[str, str]] = []
    errors: list[str] = []
    for source_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        presentations = sorted(source_dir.glob("*.pptx"))
        if not presentations:
            skipped.append(
                {"source_folder": source_dir.name, "reason": "no PPTX file"}
            )
            continue
        if len(presentations) > 1:
            errors.append(f"{source_dir.name}: expected one PPTX, found {len(presentations)}")
            continue
        try:
            prepared.append(
                PreparedSource(
                    source_dir=source_dir,
                    post_date=_source_date(source_dir.name),
                    presentation=presentations[0],
                    text=extract_presentation_text(presentations[0]),
                )
            )
        except ValidationError as exc:
            errors.extend(exc.messages)
    if errors:
        raise ValidationError(errors)
    prepared.sort(
        key=lambda item: (
            item.post_date,
            item.text.event_time,
            item.source_dir.name.casefold(),
        )
    )
    return prepared, skipped


def prepare_content(
    source_root: Path,
    output_root: Path,
    department_code: str = "inv",
    heic_converter: Callable[[Path, Path], None] = _convert_heic_with_sips,
) -> dict[str, object]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if not source_root.is_dir():
        raise ValidationError(f"Source directory does not exist: {source_root}")
    if not re.fullmatch(r"[a-z0-9]+", department_code):
        raise ValidationError("Department code must use lowercase a-z and 0-9")
    if output_root.exists():
        raise ValidationError(f"Output directory already exists: {output_root}")

    sources, skipped = _scan_sources(source_root)
    if not sources:
        raise ValidationError("No folders with a readable PPTX file were found")

    content_root = output_root / "content"
    content_root.mkdir(parents=True)
    sequence_by_date: defaultdict[date, int] = defaultdict(int)
    posts: list[dict[str, object]] = []

    for source in sources:
        sequence_by_date[source.post_date] += 1
        post_number = sequence_by_date[source.post_date]
        post_stem = (
            f"{source.post_date.isoformat()}-{department_code}-post{post_number:02d}"
        )
        image_dir = content_root / post_stem
        image_dir.mkdir()
        (image_dir / f"{source.source_dir.name}.txt").touch()

        copied_images: list[dict[str, str]] = []
        source_images = sorted(
            (
                path
                for path in source.source_dir.iterdir()
                if path.is_file() and path.suffix.lower() in RAW_IMAGE_EXTENSIONS
            ),
            key=lambda path: path.name.casefold(),
        )
        for image_number, image in enumerate(source_images, start=1):
            extension = ".jpg" if image.suffix.lower() == ".heic" else image.suffix.lower()
            destination = image_dir / f"{post_stem}-{image_number:02d}{extension}"
            if image.suffix.lower() == ".heic":
                heic_converter(image, destination)
            else:
                shutil.copy2(image, destination)
            copied_images.append(
                {
                    "source": image.name,
                    "prepared": destination.name,
                }
            )

        body, highlight_method = _emphasize_subject(
            source.text.body,
            source.source_dir.name,
        )
        markdown_path = content_root / f"{post_stem}.md"
        markdown_path.write_text(
            _markdown(source.text.heading, body, post_stem, len(source_images)),
            encoding="utf-8",
        )
        posts.append(
            {
                "source_folder": source.source_dir.name,
                "pptx": source.presentation.name,
                "post_stem": post_stem,
                "event_time": source.text.event_time.strftime("%H:%M"),
                "subject_highlight": highlight_method,
                "copied_images": copied_images,
            }
        )

    report: dict[str, object] = {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "department_code": department_code,
        "prepared": len(posts),
        "skipped": skipped,
        "posts": posts,
    }
    (output_root / "prepare-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report

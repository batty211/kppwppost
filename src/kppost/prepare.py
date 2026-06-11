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
SOURCE_TIME_PATTERN = re.compile(
    r"^\d{6}[-_ ](?P<hour>\d{2})(?P<minute>\d{2})(?:[-_ ]|$)"
)
SOURCE_ROOT_MONTH_PATTERN = re.compile(r"^(?P<year>\d{2})-(?P<month>\d{2})(?:-|$)")
DEPARTMENT_CODE_PATTERN = re.compile(r"^(?=.*[a-z])[a-z0-9]+$")
SUBJECT_PREFIXES = (
    "ปรับ ม38",
    "สุ่มตรวจ",
    "ท้องถิ่น",
    "ม38",
)


def _department_item_template(department_code: str) -> dict[str, object]:
    return {
        "code": department_code,
        "id": "",
        "name": "",
        "wordpress_category_slug": "",
        "wordpress_category_parent_slug": None,
        "wordpress_tag_slug": "",
    }


def _department_template(department_code: str) -> dict[str, object]:
    return _departments_template([department_code])


def _departments_template(department_codes: list[str]) -> dict[str, object]:
    return {
        "departments": [
            _department_item_template(department_code)
            for department_code in department_codes
        ]
    }


def _write_department_template(output_root: Path, department_code: str) -> Path:
    destination = output_root / "departments.json"
    if not destination.exists():
        destination.write_text(
            json.dumps(
                _department_template(department_code),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return destination


def _department_cache_path(source_root: Path) -> Path:
    return source_root.parent / ".kppost" / "departments.json"


def _read_departments_file(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    departments = data.get("departments")
    if not isinstance(departments, list):
        return None
    return data


def _complete_department_codes(data: dict[str, object]) -> set[str]:
    departments = data.get("departments")
    if not isinstance(departments, list):
        return set()
    complete: set[str] = set()
    for item in departments:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if not isinstance(code, str) or not code.strip():
            continue
        required_strings = (
            "id",
            "name",
            "wordpress_category_slug",
            "wordpress_tag_slug",
        )
        valid = True
        for key in required_strings:
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                valid = False
                break
        if not valid:
            continue
        if "wordpress_category_parent_slug" not in item:
            continue
        parent_slug = item["wordpress_category_parent_slug"]
        if parent_slug is not None and (
            not isinstance(parent_slug, str) or not parent_slug.strip()
        ):
            continue
        complete.add(code.strip())
    return complete


def _has_complete_departments(
    data: dict[str, object],
    department_codes: set[str],
) -> bool:
    return department_codes.issubset(_complete_department_codes(data))


def _complete_multi_departments_file(
    path: Path,
    department_codes: set[str],
) -> Path | None:
    data = _read_departments_file(path)
    if data is None:
        return None
    if not _has_complete_departments(data, department_codes):
        return None
    return path


def _sibling_batch_department_files(
    source_root: Path,
    output_root: Path,
) -> list[Path]:
    output_resolved = output_root.resolve()
    candidates: list[Path] = []
    for path in source_root.parent.glob("batch-[0-9][0-9]-[0-9][0-9]"):
        if not path.is_dir() or path.resolve() == output_resolved:
            continue
        departments_path = path / "departments.json"
        if departments_path.is_file():
            candidates.append(departments_path)
    return sorted(candidates, key=lambda path: path.parent.name, reverse=True)


def _resolve_multi_departments_source(
    source_root: Path,
    output_root: Path,
    department_codes: set[str],
) -> tuple[Path | None, str, Path]:
    parent_cache = _department_cache_path(source_root)
    source_file = source_root / "departments.json"
    if source_file.is_file() and _complete_multi_departments_file(
        source_file,
        department_codes,
    ):
        return source_file, "source_root", parent_cache
    if parent_cache.is_file() and _complete_multi_departments_file(
        parent_cache,
        department_codes,
    ):
        return parent_cache, "parent_cache", parent_cache
    for candidate in _sibling_batch_department_files(source_root, output_root):
        if _complete_multi_departments_file(candidate, department_codes):
            return candidate, "sibling_batch", parent_cache
    return None, "template", parent_cache


def _write_multi_departments_file(
    source_root: Path,
    output_root: Path,
    department_codes: set[str],
) -> tuple[Path, str, Path]:
    destination = output_root / "departments.json"
    source_file, departments_source, parent_cache = _resolve_multi_departments_source(
        source_root,
        output_root,
        department_codes,
    )
    if source_file is None:
        destination.write_text(
            json.dumps(
                _departments_template(sorted(department_codes)),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return destination, departments_source, parent_cache

    shutil.copy2(source_file, destination)
    parent_cache.parent.mkdir(parents=True, exist_ok=True)
    if source_file.resolve() != parent_cache.resolve():
        shutil.copy2(source_file, parent_cache)
    return destination, departments_source, parent_cache


@dataclass(frozen=True)
class SourceText:
    heading: str
    body: str
    event_time: time


@dataclass(frozen=True)
class PreparedSource:
    source_dir: Path
    post_date: date
    department_code: str
    subject_folder_name: str
    source_file: Path
    source_kind: str
    text: SourceText


@dataclass(frozen=True)
class SourceName:
    post_date: date
    department_code: str
    subject_name: str
    event_time: time


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


def extract_presentation_text(path: Path) -> SourceText:
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
    return SourceText(heading=heading, body=body, event_time=event_time)


def extract_plain_text(path: Path, fallback_time: time) -> SourceText:
    body_text = (
        path.read_text(encoding="utf-8-sig")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    lines = [line.strip() for line in body_text.split("\n")]
    heading = next((line for line in lines if line), "")
    if not heading:
        raise ValidationError(f"{path.name}: text file is empty")

    heading_index = lines.index(heading)
    body = "\n".join(lines[heading_index + 1 :]).strip()
    if not body:
        body = heading

    time_match = TIME_PATTERN.search(body) or TIME_PATTERN.search(heading)
    event_time = fallback_time
    if time_match is not None:
        hour, minute = (int(value) for value in time_match.groups())
        try:
            event_time = time(hour, minute)
        except ValueError as exc:
            raise ValidationError(
                f"{path.name}: invalid event time {hour}:{minute:02d}"
            ) from exc
    return SourceText(heading=heading, body=body, event_time=event_time)


def _source_date(name: str) -> date:
    match = SOURCE_NAME_PATTERN.match(name)
    if match is None:
        raise ValidationError(
            f"{name}: expected folder name to begin with a YYMMDD date"
        )
    raw_year = int(match.group("year"))
    gregorian_year = 2500 + raw_year - 543 if raw_year >= 60 else 2000 + raw_year
    try:
        return date(
            gregorian_year,
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError as exc:
        raise ValidationError(f"{name}: invalid date prefix") from exc


def _source_time(name: str) -> time:
    match = SOURCE_TIME_PATTERN.match(name)
    if match is None:
        return time(0, 0)
    hour, minute = (int(value) for value in match.groups())
    try:
        return time(hour, minute)
    except ValueError as exc:
        raise ValidationError(
            f"{name}: invalid time suffix {hour}:{minute:02d}"
        ) from exc


def _source_name(name: str, fallback_department_code: str) -> SourceName:
    post_date = _source_date(name)
    match = SOURCE_NAME_PATTERN.match(name)
    assert match is not None
    remainder = name[match.end() :].strip(" -_")
    department_code = fallback_department_code
    event_time = time(0, 0)
    subject_tokens: list[str] = []
    for token in re.split(r"[-_ ]+", remainder):
        if not token:
            continue
        if re.fullmatch(r"\d{4}", token):
            hour = int(token[:2])
            minute = int(token[2:])
            try:
                event_time = time(hour, minute)
            except ValueError as exc:
                raise ValidationError(
                    f"{name}: invalid time suffix {hour}:{minute:02d}"
                ) from exc
            continue
        if department_code == fallback_department_code and DEPARTMENT_CODE_PATTERN.fullmatch(token):
            department_code = token
            continue
        subject_tokens.append(token)
    return SourceName(
        post_date=post_date,
        department_code=department_code,
        subject_name=" ".join(subject_tokens),
        event_time=event_time,
    )


def default_output_root(source_root: Path) -> Path:
    match = SOURCE_ROOT_MONTH_PATTERN.match(source_root.name)
    if match is None:
        return source_root.parent / f"batch-{source_root.name}"
    return source_root.parent / f"batch-{match.group('year')}-{match.group('month')}"


def _emphasize_subject(body: str, subject_name: str) -> tuple[str, str]:
    subject = _normalize_text(subject_name)
    for prefix in SUBJECT_PREFIXES:
        if subject.startswith(prefix):
            subject = subject[len(prefix) :].strip(" -_")
            break
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


def _markdown(heading: str, body: str, image_sources: list[str]) -> str:
    image_blocks = "\n\n".join(
        f"![ภาพผลการปฏิบัติงาน]({source})" for source in image_sources
    )
    suffix = f"\n\n{image_blocks}" if image_blocks else ""
    return f"# {heading}\n\n{body}{suffix}\n"


def _scan_sources(
    source_root: Path,
    fallback_department_code: str,
) -> tuple[list[PreparedSource], list[dict[str, str]]]:
    prepared: list[PreparedSource] = []
    skipped: list[dict[str, str]] = []
    errors: list[str] = []
    for source_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
        presentations = sorted(source_dir.glob("*.pptx"))
        text_files = sorted(source_dir.glob("*.txt"))
        if not presentations and not text_files:
            skipped.append(
                {"source_folder": source_dir.name, "reason": "no PPTX or TXT file"}
            )
            continue
        if len(presentations) > 1:
            errors.append(f"{source_dir.name}: expected one PPTX, found {len(presentations)}")
            continue
        if len(text_files) > 1 and not presentations:
            errors.append(f"{source_dir.name}: expected one TXT, found {len(text_files)}")
            continue
        if presentations and text_files:
            errors.append(
                f"{source_dir.name}: expected either one PPTX or one TXT, found both"
            )
            continue
        try:
            source_name = _source_name(source_dir.name, fallback_department_code)
            if presentations:
                source_file = presentations[0]
                source_kind = "pptx"
                text = extract_presentation_text(source_file)
            else:
                source_file = text_files[0]
                source_kind = "txt"
                source_time = _source_time(source_file.stem)
                if source_time == time(0, 0):
                    source_time = source_name.event_time
                text = extract_plain_text(source_file, source_time)
            prepared.append(
                PreparedSource(
                    source_dir=source_dir,
                    post_date=source_name.post_date,
                    department_code=source_name.department_code,
                    subject_folder_name=source_name.subject_name,
                    source_file=source_file,
                    source_kind=source_kind,
                    text=text,
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
            item.department_code,
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

    sources, skipped = _scan_sources(source_root, department_code)
    if not sources:
        raise ValidationError("No folders with a readable PPTX file were found")

    content_root = output_root / "content"
    content_root.mkdir(parents=True)
    sequence_by_key: defaultdict[tuple[date, str], int] = defaultdict(int)
    posts: list[dict[str, object]] = []

    for source in sources:
        sequence_key = (source.post_date, source.department_code)
        sequence_by_key[sequence_key] += 1
        post_number = sequence_by_key[sequence_key]
        post_stem = (
            f"{source.post_date.isoformat()}-{source.department_code}-post{post_number:02d}"
        )
        image_dir = content_root / post_stem
        image_dir.mkdir()
        (image_dir / f"{source.source_dir.name}.txt").touch()

        copied_images: list[dict[str, str]] = []
        markdown_image_sources: list[str] = []
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
            if image_number > 1:
                markdown_image_sources.append(f"{post_stem}/{destination.name}")

        body, highlight_method = _emphasize_subject(
            source.text.body,
            source.subject_folder_name,
        )
        markdown_path = content_root / f"{post_stem}.md"
        markdown_path.write_text(
            _markdown(source.text.heading, body, markdown_image_sources),
            encoding="utf-8",
        )
        posts.append(
            {
                "source_folder": source.source_dir.name,
                source.source_kind: source.source_file.name,
                "post_stem": post_stem,
                "department_code": source.department_code,
                "event_time": source.text.event_time.strftime("%H:%M"),
                "subject_highlight": highlight_method,
                "copied_images": copied_images,
            }
        )

    department_codes = {source.department_code for source in sources}
    department_file, departments_source, departments_cache_file = _write_multi_departments_file(
        source_root,
        output_root,
        department_codes,
    )
    report: dict[str, object] = {
        "source_root": str(source_root),
        "output_root": str(output_root),
        "department_code": department_code,
        "department_codes": sorted(department_codes),
        "departments_file": str(department_file),
        "departments_source": departments_source,
        "departments_cache_file": str(departments_cache_file),
        "prepared": len(posts),
        "skipped": skipped,
        "posts": posts,
    }
    (output_root / "prepare-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report

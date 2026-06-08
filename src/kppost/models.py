from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Department:
    code: str
    id: str
    name: str
    wordpress_category_slug: str
    wordpress_category_parent_slug: str | None
    wordpress_tag_slug: str


@dataclass(frozen=True)
class ImageReference:
    path: Path
    source: str
    alt: str = ""
    title: str = ""


@dataclass
class ParsedMarkdown:
    title: str
    body_tokens: list
    images: list[ImageReference] = field(default_factory=list)


@dataclass
class UploadedMedia:
    id: int
    source_url: str
    filename: str
    sequence: int
    source_path: str
    sha256: str

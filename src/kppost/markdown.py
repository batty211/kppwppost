from __future__ import annotations

import copy
import html
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from .errors import ValidationError
from .files import ensure_within
from .models import ImageReference, ParsedMarkdown, UploadedMedia


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def markdown_parser() -> MarkdownIt:
    return MarkdownIt("commonmark", {"html": False}).enable("table")


def _plain_inline_text(token: Token) -> str:
    parts: list[str] = []
    for child in token.children or []:
        if child.type in {"text", "code_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
        elif child.type == "image":
            parts.append(child.content)
    return " ".join("".join(parts).split())


def _image_reference(md_path: Path, batch_root: Path, token: Token) -> ImageReference:
    source = token.attrGet("src") or ""
    if not source:
        raise ValidationError(f"{md_path.name}: image is missing a source path")
    if source.startswith(("http://", "https://", "//", "data:")):
        raise ValidationError(
            f"{md_path.name}: remote images are not supported: {source}"
        )
    image_path = ensure_within(batch_root, md_path.parent / source)
    if not image_path.is_file():
        raise ValidationError(f"{md_path.name}: missing inline image: {source}")
    if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"{md_path.name}: unsupported inline image type: {source}"
        )
    validate_image_signature(image_path)
    return ImageReference(
        path=image_path,
        source=source,
        alt=token.content.strip(),
        title=(token.attrGet("title") or "").strip(),
    )


def validate_image_signature(path: Path) -> None:
    header = path.read_bytes()[:16]
    suffix = path.suffix.lower()
    valid = (
        (suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
        or (suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
        or (
            suffix == ".webp"
            and len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        )
    )
    if not valid:
        raise ValidationError(
            f"Image content does not match its JPG/PNG/WebP extension: {path}"
        )


def parse_markdown(md_path: Path, batch_root: Path) -> ParsedMarkdown:
    text = md_path.read_text(encoding="utf-8")
    tokens = markdown_parser().parse(text)
    h1_indexes = [
        index
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.tag == "h1"
    ]
    if len(h1_indexes) != 1:
        raise ValidationError(
            f"{md_path.name}: expected exactly one H1 title, found {len(h1_indexes)}"
        )
    first_visible = next(
        (index for index, token in enumerate(tokens) if token.type != "front_matter"),
        None,
    )
    h1_index = h1_indexes[0]
    if first_visible != h1_index:
        raise ValidationError(f"{md_path.name}: the first Markdown block must be H1")
    if h1_index + 2 >= len(tokens) or tokens[h1_index + 1].type != "inline":
        raise ValidationError(f"{md_path.name}: invalid H1 title")
    title = _plain_inline_text(tokens[h1_index + 1])
    if not title:
        raise ValidationError(f"{md_path.name}: H1 title cannot be empty")

    body_tokens = tokens[:h1_index] + tokens[h1_index + 3 :]
    excerpt = ""
    images: list[ImageReference] = []
    for index, token in enumerate(body_tokens):
        if token.type != "inline":
            continue
        if (
            not excerpt
            and index > 0
            and body_tokens[index - 1].type == "paragraph_open"
        ):
            excerpt = _plain_inline_text(token)
        image_children = [
            child for child in token.children or [] if child.type == "image"
        ]
        if image_children and _is_standalone_image(token) is None:
            raise ValidationError(
                f"{md_path.name}: each Markdown image must be on its own paragraph"
            )
        for child in token.children or []:
            if child.type == "image":
                images.append(_image_reference(md_path, batch_root, child))

    return ParsedMarkdown(
        title=title,
        excerpt=excerpt,
        body_tokens=body_tokens,
        images=images,
    )


def _matching_close(tokens: list[Token], start: int) -> int:
    opening = tokens[start]
    if not opening.type.endswith("_open"):
        return start
    closing_type = opening.type.removesuffix("_open") + "_close"
    depth = 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token.type == opening.type:
            depth += 1
        elif token.type == closing_type:
            depth -= 1
            if depth == 0:
                return index
    raise ValidationError(f"Unclosed Markdown block: {opening.type}")


def _block(comment: str, markup: str, attrs: str = "") -> str:
    opening = f"<!-- wp:{comment}{(' ' + attrs) if attrs else ''} -->"
    return f"{opening}\n{markup.rstrip()}\n<!-- /wp:{comment} -->"


def _is_standalone_image(inline: Token) -> Token | None:
    meaningful = [
        token
        for token in inline.children or []
        if not (token.type == "text" and not token.content.strip())
    ]
    return meaningful[0] if len(meaningful) == 1 and meaningful[0].type == "image" else None


def _render_image_block(token: Token, media: UploadedMedia) -> str:
    alt = html.escape(token.content or "", quote=True)
    caption = token.attrGet("title") or ""
    attrs = f'{{"id":{media.id},"sizeSlug":"full","linkDestination":"none"}}'
    markup = (
        '<figure class="wp-block-image size-full">'
        f'<img src="{html.escape(media.source_url, quote=True)}" '
        f'alt="{alt}" class="wp-image-{media.id}"/>'
    )
    if caption:
        markup += (
            '<figcaption class="wp-element-caption">'
            f"{html.escape(caption)}"
            "</figcaption>"
        )
    markup += "</figure>"
    return _block("image", markup, attrs)


def render_gutenberg(
    parsed: ParsedMarkdown,
    media_by_source: dict[str, UploadedMedia],
) -> str:
    tokens = copy.deepcopy(parsed.body_tokens)
    parser = markdown_parser()
    renderer = parser.renderer

    def render_tokens(items: list[Token]) -> str:
        return renderer.render(items, parser.options, {})

    for token in tokens:
        if token.type != "inline":
            continue
        for child in token.children or []:
            if child.type != "image":
                continue
            source = child.attrGet("src") or ""
            media = media_by_source[source]
            child.attrSet("src", media.source_url)
            child.attrSet("class", f"wp-image-{media.id}")

    blocks: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "paragraph_open":
            close = _matching_close(tokens, index)
            inline = next(
                (item for item in tokens[index : close + 1] if item.type == "inline"),
                None,
            )
            image = _is_standalone_image(inline) if inline else None
            if image is not None:
                source = next(
                    ref.source
                    for ref in parsed.images
                    if media_by_source[ref.source].source_url == image.attrGet("src")
                )
                blocks.append(_render_image_block(image, media_by_source[source]))
            else:
                markup = render_tokens(tokens[index : close + 1])
                blocks.append(_block("paragraph", markup))
            index = close + 1
            continue
        if token.type == "heading_open":
            close = _matching_close(tokens, index)
            level = int(token.tag[1:])
            markup = render_tokens(tokens[index : close + 1])
            blocks.append(_block("heading", markup, f'{{"level":{level}}}'))
            index = close + 1
            continue
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            close = _matching_close(tokens, index)
            markup = render_tokens(tokens[index : close + 1])
            attrs = '{"ordered":true}' if token.type == "ordered_list_open" else ""
            blocks.append(_block("list", markup, attrs))
            index = close + 1
            continue
        if token.type == "blockquote_open":
            close = _matching_close(tokens, index)
            markup = render_tokens(tokens[index : close + 1])
            markup = markup.replace("<blockquote>", '<blockquote class="wp-block-quote">', 1)
            blocks.append(_block("quote", markup))
            index = close + 1
            continue
        if token.type == "table_open":
            close = _matching_close(tokens, index)
            table = render_tokens(tokens[index : close + 1])
            blocks.append(_block("table", f'<figure class="wp-block-table">{table}</figure>'))
            index = close + 1
            continue
        if token.type in {"fence", "code_block"}:
            code = html.escape(token.content)
            language = (token.info or "").strip().split(maxsplit=1)[0]
            attrs = f' class="language-{html.escape(language, quote=True)}"' if language else ""
            blocks.append(_block("code", f"<pre class=\"wp-block-code\"><code{attrs}>{code}</code></pre>"))
            index += 1
            continue
        if token.type == "hr":
            blocks.append(_block("separator", '<hr class="wp-block-separator has-alpha-channel-opacity"/>'))
            index += 1
            continue
        if token.type.endswith("_close"):
            index += 1
            continue
        markup = render_tokens([token])
        if markup.strip():
            blocks.append(_block("html", markup))
        index += 1
    return "\n\n".join(blocks)

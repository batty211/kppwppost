from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .checkpoint import Checkpoint
from .errors import ValidationError, WordPressError
from .files import atomic_write_json, ensure_within, relative_posix, sha256_file
from .manifest import validate_batch
from .markdown import parse_markdown, render_gutenberg
from .models import UploadedMedia
from .wordpress import WordPressClient


BANGKOK = ZoneInfo("Asia/Bangkok")


def resolve_post_taxonomies(
    client: WordPressClient,
    post: dict[str, Any],
) -> tuple[list[int], list[int]]:
    category_ids = [
        client.resolve_category(
            post["wordpress_category_slug"],
            post["wordpress_category_parent_slug"],
            post["categories"][0],
        )
    ]
    tag_ids = [
        client.resolve_tag(slug, name)
        for slug, name in zip(
            post["wordpress_tag_slugs"],
            post["tags"],
            strict=True,
        )
    ]
    return category_ids, tag_ids


def assign_post_datetimes(
    manifest: dict[str, Any], started_at: datetime
) -> dict[str, datetime]:
    local_start = started_at.astimezone(BANGKOK)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for post in manifest["posts"]:
        groups[(post["date"], post["department_code"])].append(post)
    assigned: dict[str, datetime] = {}
    errors: list[str] = []
    for (raw_date, _code), posts in groups.items():
        posts.sort(key=lambda item: item["post_number"])
        base = datetime.fromisoformat(
            f"{raw_date}T{local_start:%H:%M:%S}"
        ).replace(tzinfo=BANGKOK)
        for offset, post in enumerate(reversed(posts)):
            post_time = base - timedelta(minutes=offset)
            if post_time.date().isoformat() != raw_date:
                errors.append(
                    f"{post['source_id']}: calculated post time crosses into "
                    f"{post_time.date().isoformat()}"
                )
            assigned[post["source_id"]] = post_time
    if errors:
        raise ValidationError(errors)
    return assigned


def _media_from_checkpoint(data: dict[str, Any]) -> UploadedMedia:
    return UploadedMedia(
        id=int(data["id"]),
        source_url=data["source_url"],
        filename=data["filename"],
        sequence=int(data["sequence"]),
        source_path=data["source_path"],
        sha256=data["sha256"],
    )


class Importer:
    def __init__(
        self,
        batch_root: Path,
        client: WordPressClient,
        progress: Callable[[str], None] | None = None,
    ):
        self.batch_root = batch_root.resolve()
        self.client = client
        self.progress = progress or (lambda _message: None)

    def _upload_post_media(
        self,
        post: dict[str, Any],
        parsed: Any,
        checkpoint: Checkpoint,
    ) -> tuple[UploadedMedia, dict[str, UploadedMedia], list[UploadedMedia]]:
        source_id = post["source_id"]
        state = checkpoint.post(source_id)
        featured_path = ensure_within(
            self.batch_root, self.batch_root / post["featured_image"]
        )
        ordered: list[tuple[Path, str, str, str]] = [
            (featured_path, "__featured__", post["title"], "")
        ]
        seen_paths = {featured_path.resolve()}
        for image in parsed.images:
            resolved = image.path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            ordered.append((resolved, image.source, image.alt, image.title))

        uploaded: list[UploadedMedia] = []
        media_by_path: dict[Path, UploadedMedia] = {}
        for sequence, (path, source, alt, caption) in enumerate(ordered, start=1):
            key = relative_posix(self.batch_root, path)
            digest = sha256_file(path)
            saved = state["media"].get(key)
            if saved:
                if saved.get("sha256") != digest:
                    raise ValidationError(
                        f"{source_id}: source image changed after upload: {key}"
                    )
                media = _media_from_checkpoint(saved)
            else:
                extension = path.suffix.lower()
                upload_filename = f"{post['slug']}-{sequence:02d}{extension}"
                media_title = (
                    f"{post['department_name']} - {post['title']} - รูป {sequence:02d}"
                )
                result = self.client.upload_media(
                    path=path,
                    upload_filename=upload_filename,
                    title=media_title,
                    alt_text=alt,
                    caption=caption,
                )
                saved = {
                    **result,
                    "sequence": sequence,
                    "source_path": key,
                    "sha256": digest,
                }
                checkpoint.save_media(source_id, key, saved)
                media = _media_from_checkpoint(saved)
            uploaded.append(media)
            media_by_path[path.resolve()] = media

        featured = media_by_path[featured_path.resolve()]
        media_by_source = {
            image.source: media_by_path[image.path.resolve()] for image in parsed.images
        }
        return featured, media_by_source, uploaded

    def run(self, started_at: datetime | None = None) -> dict[str, Any]:
        manifest = validate_batch(self.batch_root)
        started_at = started_at or datetime.now(tz=BANGKOK)
        assigned_times = assign_post_datetimes(manifest, started_at)
        checkpoint = Checkpoint(self.batch_root, manifest["batch_id"])
        preflight = self.client.preflight()
        report: dict[str, Any] = {
            "batch_id": manifest["batch_id"],
            "started_at": started_at.isoformat(),
            "preflight": preflight,
            "posts": [],
            "summary": {"success": 0, "skipped": 0, "failed": 0},
        }

        total = len(manifest["posts"])
        for position, post in enumerate(manifest["posts"], start=1):
            source_id = post["source_id"]
            self.progress(f"[{position}/{total}] {source_id}")
            state = checkpoint.post(source_id)
            if state.get("status") == "success":
                report["posts"].append(
                    {
                        "source_id": source_id,
                        "status": "skipped",
                        "post": state.get("post"),
                        "media": list(state.get("media", {}).values()),
                    }
                )
                report["summary"]["skipped"] += 1
                self.progress("  skipped: already completed")
                continue
            try:
                existing_post = state.get("post")
                if existing_post is None:
                    collision = self.client.find_post_by_slug(post["slug"])
                    if collision:
                        raise WordPressError(
                            f"Slug already exists outside this checkpoint: "
                            f"{post['slug']} (post {collision['id']})"
                        )
                    category_ids, tag_ids = resolve_post_taxonomies(
                        self.client, post
                    )

                md_path = ensure_within(
                    self.batch_root, self.batch_root / post["content_file"]
                )
                parsed = parse_markdown(md_path, self.batch_root)
                featured, media_by_source, uploaded = self._upload_post_media(
                    post, parsed, checkpoint
                )
                if existing_post is None:
                    content = render_gutenberg(parsed, media_by_source)
                    created = self.client.create_post(
                        {
                            "title": post["title"],
                            "slug": post["slug"],
                            "content": content,
                            "status": manifest["status"],
                            "date": assigned_times[source_id].isoformat(),
                            "categories": category_ids,
                            "tags": tag_ids,
                            "featured_media": featured.id,
                            "comment_status": "closed",
                            "ping_status": "closed",
                        }
                    )
                    existing_post = {
                        "id": int(created["id"]),
                        "link": created.get("link", ""),
                        "slug": created.get("slug", post["slug"]),
                        "status": created.get("status", manifest["status"]),
                    }
                    checkpoint.save_post(source_id, existing_post)

                for media in uploaded:
                    self.client.attach_media(media.id, int(existing_post["id"]))
                checkpoint.mark_success(source_id)
                report["posts"].append(
                    {
                        "source_id": source_id,
                        "status": "success",
                        "post": existing_post,
                        "media": [
                            checkpoint.post(source_id)["media"][key]
                            for key in checkpoint.post(source_id)["media"]
                        ],
                    }
                )
                report["summary"]["success"] += 1
                self.progress(
                    f"  success: post {existing_post['id']} ({existing_post['slug']})"
                )
            except Exception as exc:
                message = str(exc)
                checkpoint.mark_failure(source_id, message)
                report["posts"].append(
                    {
                        "source_id": source_id,
                        "status": "failed",
                        "error": message,
                    }
                )
                report["summary"]["failed"] += 1
                self.progress(f"  failed: {message}")

        finished_at = datetime.now(tz=BANGKOK)
        report["finished_at"] = finished_at.isoformat()
        report_path = (
            self.batch_root
            / ".bulkpost"
            / "reports"
            / f"import-{finished_at:%Y%m%d-%H%M%S}.json"
        )
        atomic_write_json(report_path, report)
        report["report_path"] = str(report_path)
        return report

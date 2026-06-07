from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from kppost.importer import Importer, assign_post_datetimes
from kppost.manifest import validate_batch


class FakeWordPressClient:
    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.created_posts: list[dict[str, Any]] = []
        self.attachments: list[tuple[int, int]] = []
        self.next_media_id = 100

    def preflight(self) -> dict[str, Any]:
        return {"site_name": "Test", "user_id": 1}

    def find_post_by_slug(self, slug: str) -> None:
        return None

    def resolve_category(
        self, slug: str, parent_slug: str, expected_name: str
    ) -> int:
        assert slug == "investigation"
        assert parent_slug == "activities"
        assert expected_name == "งานสืบสวนปราบปราม"
        return 90

    def resolve_tag(self, slug: str, expected_name: str) -> int:
        expected = {
            "2026-06": ("2026-06", 140),
            "investigate": ("งานสืบสวนปราบปราม", 64),
        }
        name, tag_id = expected[slug]
        assert expected_name == name
        return tag_id

    def upload_media(self, **kwargs: Any) -> dict[str, Any]:
        self.next_media_id += 1
        media_id = self.next_media_id
        self.uploads.append(kwargs)
        return {
            "id": media_id,
            "source_url": f"https://example.com/uploads/{kwargs['upload_filename']}",
            "filename": kwargs["upload_filename"],
        }

    def create_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created_posts.append(payload)
        return {
            "id": 501,
            "link": "https://example.com/post",
            "slug": payload["slug"],
            "status": payload["status"],
        }

    def attach_media(self, media_id: int, post_id: int) -> None:
        self.attachments.append((media_id, post_id))


def test_assign_times_ends_at_import_time(batch: Path) -> None:
    manifest = validate_batch(batch)
    manifest["posts"].append(
        {
            **manifest["posts"][0],
            "source_id": "2026-06-07-inv-post02",
            "post_number": 2,
            "slug": "20260607-inv-01-post02",
        }
    )
    started = datetime(2026, 6, 8, 9, 30, 45, tzinfo=ZoneInfo("Asia/Bangkok"))
    assigned = assign_post_datetimes(manifest, started)

    assert assigned["2026-06-07-inv-post02"].isoformat() == "2026-06-07T09:30:45+07:00"
    assert assigned["2026-06-07-inv-post01"].isoformat() == "2026-06-07T09:29:45+07:00"


def test_import_and_resume(batch: Path) -> None:
    client = FakeWordPressClient()
    importer = Importer(batch, client)
    started = datetime(2026, 6, 8, 10, 0, tzinfo=ZoneInfo("Asia/Bangkok"))

    first = importer.run(started_at=started)

    assert first["summary"] == {"success": 1, "skipped": 0, "failed": 0}
    assert [item["upload_filename"] for item in client.uploads] == [
        "20260607-inv-01-post01-01.jpg",
        "20260607-inv-01-post01-02.png",
    ]
    assert client.uploads[0]["title"].endswith("รูป 01")
    assert client.uploads[0]["alt_text"] == "รายงานผลการปฏิบัติงาน"
    assert client.uploads[1]["alt_text"] == "ภาพผลการปฏิบัติงาน"
    assert client.created_posts[0]["featured_media"] == 101
    assert client.created_posts[0]["date"] == "2026-06-07T10:00:00+07:00"
    assert client.created_posts[0]["comment_status"] == "closed"
    assert client.created_posts[0]["ping_status"] == "closed"
    assert "<!-- wp:image" in client.created_posts[0]["content"]
    assert client.attachments == [(101, 501), (102, 501)]

    second = importer.run(started_at=started)

    assert second["summary"] == {"success": 0, "skipped": 1, "failed": 0}
    assert len(client.uploads) == 2
    assert len(client.created_posts) == 1

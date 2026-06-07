from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import ValidationError
from .files import atomic_write_json, load_json


class Checkpoint:
    def __init__(self, batch_root: Path, batch_id: str):
        self.path = batch_root / ".bulkpost" / "state.json"
        self.batch_id = batch_id
        if self.path.exists():
            data = load_json(self.path)
            if data.get("batch_id") != batch_id:
                raise ValidationError(
                    f"Checkpoint batch_id does not match {batch_id}: {self.path}"
                )
            self.data: dict[str, Any] = data
        else:
            self.data = {
                "version": 1,
                "batch_id": batch_id,
                "posts": {},
            }

    def post(self, source_id: str) -> dict[str, Any]:
        return self.data["posts"].setdefault(
            source_id,
            {
                "status": "pending",
                "media": {},
            },
        )

    def save(self) -> None:
        atomic_write_json(self.path, self.data)

    def save_media(self, source_id: str, key: str, media: dict[str, Any]) -> None:
        self.post(source_id)["media"][key] = media
        self.save()

    def save_post(self, source_id: str, post: dict[str, Any]) -> None:
        entry = self.post(source_id)
        entry["post"] = post
        entry["status"] = "post_created"
        self.save()

    def mark_success(self, source_id: str) -> None:
        self.post(source_id)["status"] = "success"
        self.save()

    def mark_failure(self, source_id: str, message: str) -> None:
        entry = self.post(source_id)
        entry["last_error"] = message
        if entry.get("status") != "post_created":
            entry["status"] = "failed"
        self.save()


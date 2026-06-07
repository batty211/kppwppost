from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from .errors import WordPressError


class WordPressClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        application_password: str,
        timeout: float = 30,
        verify_ssl: bool = True,
        session: requests.Session | None = None,
    ):
        if not base_url.lower().startswith("https://"):
            raise WordPressError("WP_URL must use HTTPS")
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/wp-json/wp/v2"
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.session = session or requests.Session()
        self.session.auth = (username, application_password)
        self.session.headers.update(
            {"User-Agent": "kppost/0.1 (+WordPress REST API importer)"}
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200,),
        **kwargs: Any,
    ) -> Any:
        url = path if path.startswith("http") else f"{self.api_url}{path}"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                    **kwargs,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                time.sleep(2**attempt)
                continue
            if response.status_code in expected:
                if not response.content:
                    return None
                try:
                    return response.json()
                except ValueError as exc:
                    raise WordPressError(
                        f"WordPress returned invalid JSON for {method} {path}",
                        response.status_code,
                    ) from exc
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    time.sleep(min(delay, 30))
                    continue
            try:
                payload = response.json()
                detail = payload.get("message") or payload.get("code") or response.text
            except ValueError:
                detail = response.text
            raise WordPressError(
                f"WordPress {method} {path} failed: {detail}",
                response.status_code,
            )
        raise WordPressError(
            f"WordPress {method} {path} failed after 3 attempts: {last_error}"
        )

    def preflight(self) -> dict[str, Any]:
        discovery = self._request(
            "GET", f"{self.base_url}/wp-json/", expected=(200,)
        )
        user = self._request("GET", "/users/me", params={"context": "edit"})
        self._request("OPTIONS", "/posts", expected=(200,))
        self._request("OPTIONS", "/media", expected=(200,))
        return {
            "site_name": discovery.get("name", ""),
            "site_url": discovery.get("url", self.base_url),
            "user_id": user["id"],
            "user_name": user.get("name", ""),
        }

    def get_term_by_slug(
        self, taxonomy: str, slug: str
    ) -> dict[str, Any] | None:
        results = self._request(
            "GET",
            f"/{taxonomy}",
            params={
                "slug": slug,
                "per_page": 1,
                "context": "view",
                "hide_empty": "false",
            },
        )
        return results[0] if results else None

    def resolve_category(
        self,
        slug: str,
        parent_slug: str | None,
        expected_name: str,
    ) -> int:
        category = self.get_term_by_slug("categories", slug)
        if category is None:
            raise WordPressError(
                f"Required WordPress category does not exist: {slug}"
            )
        if category.get("name", "").casefold() != expected_name.casefold():
            raise WordPressError(
                f"Category slug {slug} has unexpected name "
                f"{category.get('name')!r}; expected {expected_name!r}"
            )
        category_parent = int(category.get("parent", 0))
        if parent_slug is None:
            if category_parent != 0:
                raise WordPressError(
                    f"Category {slug} must be a top-level category"
                )
            return int(category["id"])

        parent = self.get_term_by_slug("categories", parent_slug)
        if parent is None:
            raise WordPressError(
                f"Required parent WordPress category does not exist: {parent_slug}"
            )
        if category_parent != int(parent["id"]):
            raise WordPressError(
                f"Category {slug} is not a child of {parent_slug}"
            )
        return int(category["id"])

    def resolve_tag(self, slug: str, expected_name: str) -> int:
        tag = self.get_term_by_slug("tags", slug)
        if tag is None:
            raise WordPressError(f"Required WordPress tag does not exist: {slug}")
        if tag.get("name", "").casefold() != expected_name.casefold():
            raise WordPressError(
                f"Tag slug {slug} has unexpected name {tag.get('name')!r}; "
                f"expected {expected_name!r}"
            )
        return int(tag["id"])

    def find_post_by_slug(self, slug: str) -> dict[str, Any] | None:
        posts = self._request(
            "GET",
            "/posts",
            params={
                "slug": slug,
                "context": "edit",
                "status": [
                    "publish",
                    "future",
                    "draft",
                    "pending",
                    "private",
                    "trash",
                ],
                "per_page": 1,
            },
        )
        return posts[0] if posts else None

    def upload_media(
        self,
        path: Path,
        upload_filename: str,
        title: str,
        alt_text: str,
        caption: str = "",
    ) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers = {
            "Content-Type": mime_type,
            "Content-Disposition": f'attachment; filename="{upload_filename}"',
        }
        created = self._request(
            "POST",
            "/media",
            expected=(201,),
            headers=headers,
            data=path.read_bytes(),
        )
        metadata = {
            "title": title,
            "alt_text": alt_text,
            "caption": caption,
        }
        updated = self._request(
            "POST", f"/media/{created['id']}", json=metadata, expected=(200,)
        )
        source_url = updated.get("source_url") or created["source_url"]
        actual_filename = Path(unquote(urlparse(source_url).path)).name
        return {
            "id": int(created["id"]),
            "source_url": source_url,
            "filename": actual_filename,
        }

    def create_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/posts", expected=(201,), json=payload)

    def attach_media(self, media_id: int, post_id: int) -> None:
        self._request(
            "POST",
            f"/media/{media_id}",
            expected=(200,),
            json={"post": post_id},
        )

from __future__ import annotations

from pathlib import Path

import pytest
import responses

from kppost.errors import WordPressError
from kppost.wordpress import WordPressClient


@responses.activate
def test_upload_media_renames_and_sets_metadata(tmp_path: Path) -> None:
    source = tmp_path / "1.jpg"
    source.write_bytes(b"image")
    responses.post(
        "https://example.com/wp-json/wp/v2/media",
        json={
            "id": 10,
            "source_url": "https://example.com/uploads/requested.jpg",
        },
        status=201,
    )
    responses.post(
        "https://example.com/wp-json/wp/v2/media/10",
        json={
            "id": 10,
            "source_url": "https://example.com/uploads/requested-1.jpg",
        },
        status=200,
    )
    client = WordPressClient("https://example.com", "user", "app-password")

    result = client.upload_media(
        source,
        "requested.jpg",
        "Media title",
        "Alternative text",
        "Caption",
    )

    assert result == {
        "id": 10,
        "source_url": "https://example.com/uploads/requested-1.jpg",
        "filename": "requested-1.jpg",
    }
    upload_request = responses.calls[0].request
    assert upload_request.headers["Content-Disposition"] == (
        'attachment; filename="requested.jpg"'
    )
    assert responses.calls[1].request.body is not None


@responses.activate
def test_resolve_existing_subcategory_with_view_context() -> None:
    responses.get(
        "https://example.com/wp-json/wp/v2/categories",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "slug": "investigation",
                    "per_page": "1",
                    "context": "view",
                    "hide_empty": "false",
                }
            )
        ],
        json=[
            {
                "id": 90,
                "name": "งานสืบสวนปราบปราม",
                "slug": "investigation",
                "parent": 7,
            }
        ],
        status=200,
    )
    responses.get(
        "https://example.com/wp-json/wp/v2/categories",
        match=[
            responses.matchers.query_param_matcher(
                {
                    "slug": "activities",
                    "per_page": "1",
                    "context": "view",
                    "hide_empty": "false",
                }
            )
        ],
        json=[
            {
                "id": 7,
                "name": "กิจกรรม",
                "slug": "activities",
                "parent": 0,
            }
        ],
        status=200,
    )
    client = WordPressClient("https://example.com", "user", "app-password")

    category_id = client.resolve_category(
        "investigation",
        "activities",
        "งานสืบสวนปราบปราม",
    )

    assert category_id == 90


@responses.activate
def test_rejects_category_with_wrong_parent() -> None:
    responses.get(
        "https://example.com/wp-json/wp/v2/categories",
        json=[
            {
                "id": 90,
                "name": "งานสืบสวนปราบปราม",
                "slug": "investigation",
                "parent": 99,
            }
        ],
        status=200,
    )
    responses.get(
        "https://example.com/wp-json/wp/v2/categories",
        json=[{"id": 7, "name": "กิจกรรม", "slug": "activities", "parent": 0}],
        status=200,
    )
    client = WordPressClient("https://example.com", "user", "app-password")

    with pytest.raises(WordPressError, match="not a child"):
        client.resolve_category(
            "investigation",
            "activities",
            "งานสืบสวนปราบปราม",
        )


@responses.activate
def test_resolves_top_level_category_without_parent_slug() -> None:
    responses.get(
        "https://example.com/wp-json/wp/v2/categories",
        json=[
            {
                "id": 90,
                "name": "งานสืบสวนปราบปราม",
                "slug": "investigation",
                "parent": 0,
            }
        ],
        status=200,
    )
    client = WordPressClient("https://example.com", "user", "app-password")

    category_id = client.resolve_category(
        "investigation",
        None,
        "งานสืบสวนปราบปราม",
    )

    assert category_id == 90
    assert len(responses.calls) == 1


@responses.activate
def test_rejects_child_category_when_parent_slug_is_null() -> None:
    responses.get(
        "https://example.com/wp-json/wp/v2/categories",
        json=[
            {
                "id": 90,
                "name": "งานสืบสวนปราบปราม",
                "slug": "investigation",
                "parent": 7,
            }
        ],
        status=200,
    )
    client = WordPressClient("https://example.com", "user", "app-password")

    with pytest.raises(WordPressError, match="top-level"):
        client.resolve_category(
            "investigation",
            None,
            "งานสืบสวนปราบปราม",
        )

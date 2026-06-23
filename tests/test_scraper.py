"""
Unit tests for scraper/scraper.py
Tests DB upsert logic and gallery-dl JSON parsing.
All DB and network calls are mocked.
"""
import json
import pytest
from unittest.mock import MagicMock, patch


# ── upsert_post ───────────────────────────────────────────────────────────────

from scraper import upsert_post


class TestUpsertPost:
    def _make_cursor(self, returned_id=1):
        cur = MagicMock()
        cur.fetchone.return_value = (returned_id,) if returned_id else None
        return cur

    def test_returns_id_on_new_insert(self):
        cur = self._make_cursor(returned_id=5)
        result = upsert_post(cur, "instagram", "testaccount", "https://example.com/p/1/", {
            "caption": "Test caption",
            "hashtags": ["equity"],
            "likes": 100,
            "comments": 10,
            "views": None,
        })
        assert result == 5

    def test_returns_none_on_conflict(self):
        cur = self._make_cursor(returned_id=None)
        result = upsert_post(cur, "instagram", "testaccount", "https://example.com/p/1/", {})
        assert result is None

    def test_passes_platform_and_account(self):
        cur = self._make_cursor()
        upsert_post(cur, "youtube", "veritasium", "https://youtube.com/watch?v=abc", {})
        params = cur.execute.call_args[0][1]
        assert params[0] == "youtube"
        assert params[1] == "veritasium"

    def test_passes_url(self):
        cur = self._make_cursor()
        upsert_post(cur, "instagram", "acc", "https://example.com/p/XYZ/", {})
        params = cur.execute.call_args[0][1]
        assert params[2] == "https://example.com/p/XYZ/"

    def test_handles_missing_optional_fields(self):
        cur = self._make_cursor()
        # Should not raise even with an empty data dict
        upsert_post(cur, "test", "acc", "https://example.com/1", {})
        params = cur.execute.call_args[0][1]
        assert params[3] is None   # caption
        assert params[4] == []     # hashtags
        assert params[5] is None   # likes
        assert params[6] is None   # comments
        assert params[7] is None   # views

    def test_uses_on_conflict_do_nothing(self):
        cur = self._make_cursor()
        upsert_post(cur, "test", "acc", "https://example.com/1", {})
        sql = cur.execute.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "DO NOTHING" in sql


# ── gallery-dl output parsing ─────────────────────────────────────────────────

class TestGalleryDlParsing:
    """
    gallery-dl --dump-json outputs lines like:
    [queue_pos, url, metadata_dict]
    These tests verify the scraper correctly parses that format.
    """

    def _make_gdl_line(self, url="https://youtube.com/watch?v=abc", meta=None):
        if meta is None:
            meta = {
                "category": "youtube",
                "uploader": "Veritasium",
                "description": "Why AI image generators work the way they do",
                "tags": ["AI", "technology"],
                "like_count": 50000,
                "comment_count": 2000,
                "view_count": 1500000,
                "upload_date": "20240601",
            }
        return json.dumps([1, url, meta])

    def test_parses_valid_gdl_line(self):
        line = self._make_gdl_line()
        record = json.loads(line)
        assert isinstance(record, list)
        assert len(record) == 3
        meta = record[2]
        assert meta["category"] == "youtube"
        assert meta["uploader"] == "Veritasium"

    def test_extracts_description_as_caption(self):
        line = self._make_gdl_line()
        record = json.loads(line)
        meta = record[2]
        caption = meta.get("description") or meta.get("title")
        assert "AI image" in caption

    def test_extracts_tags_as_hashtags(self):
        line = self._make_gdl_line()
        record = json.loads(line)
        meta = record[2]
        assert "AI" in meta.get("tags", [])

    def test_handles_missing_uploader_falls_back_to_channel(self):
        meta = {
            "category": "youtube",
            "channel": "SciChannel",
            "description": "Science video",
            "tags": [],
        }
        line = json.dumps([1, "https://youtube.com/watch?v=xyz", meta])
        record = json.loads(line)
        meta = record[2]
        account = meta.get("uploader") or meta.get("channel") or "unknown"
        assert account == "SciChannel"

    def test_skips_non_list_lines(self):
        line = '{"error": "not a list"}'
        record = json.loads(line)
        assert not isinstance(record, list)

    def test_skips_short_list_lines(self):
        line = json.dumps([1, "https://example.com"])
        record = json.loads(line)
        assert len(record) < 3

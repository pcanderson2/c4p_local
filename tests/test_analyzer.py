"""
Unit tests for analyzer/analyzer.py
Tests JSON extraction, think-tag stripping, DB writes, and audit flagging.
All Ollama and DB calls are mocked.
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call


# ── extract_json ──────────────────────────────────────────────────────────────

from analyzer import extract_json


class TestExtractJson:
    def test_parses_clean_json(self, sample_analysis_json):
        raw = json.dumps(sample_analysis_json)
        result = extract_json(raw)
        assert result["trend_score"] == 8.5
        assert "visual_hooks" in result

    def test_strips_think_tags(self, sample_analysis_json):
        raw = f"<think>Internal reasoning step.</think>\n{json.dumps(sample_analysis_json)}"
        result = extract_json(raw)
        assert result["trend_score"] == 8.5

    def test_strips_multiline_think_tags(self, sample_analysis_json):
        raw = f"<think>\nLine one.\nLine two.\n</think>\n{json.dumps(sample_analysis_json)}"
        result = extract_json(raw)
        assert result["pain_points"] == sample_analysis_json["pain_points"]

    def test_extracts_json_with_surrounding_text(self, sample_analysis_json):
        raw = f"Here is my analysis:\n{json.dumps(sample_analysis_json)}\nHope that helps."
        result = extract_json(raw)
        assert result["summary"] == sample_analysis_json["summary"]

    def test_raises_on_no_json(self):
        with pytest.raises(ValueError, match="No JSON found"):
            extract_json("This response has no JSON in it at all.")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_raises_on_only_think_tags(self):
        with pytest.raises(ValueError):
            extract_json("<think>Thinking...</think>")


# ── call_ollama ───────────────────────────────────────────────────────────────

class TestCallOllama:
    def test_sends_correct_payload(self, sample_analysis_json):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": json.dumps(sample_analysis_json)}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("analyzer.httpx.post", return_value=mock_response) as mock_post:
            from analyzer import call_ollama
            result = call_ollama("Test prompt")

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "phi3:mini"
        assert payload["stream"] is False
        assert any(m["role"] == "system" for m in payload["messages"])
        assert any(m["role"] == "user" for m in payload["messages"])
        assert result == json.dumps(sample_analysis_json)

    def test_raises_on_http_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")

        with patch("analyzer.httpx.post", return_value=mock_response):
            from analyzer import call_ollama
            with pytest.raises(Exception, match="HTTP 500"):
                call_ollama("Test prompt")


# ── _save_analysis ────────────────────────────────────────────────────────────

class TestSaveAnalysis:
    def test_always_sets_ai_flagged_true(self, sample_analysis_json):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        from analyzer import _save_analysis
        _save_analysis(mock_conn, post_id=1, result=sample_analysis_json)

        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        # ai_flagged is the 8th parameter (index 7) in the INSERT
        assert params[7] is True  # ai_flagged must always be TRUE

    def test_strict_mode_sets_pending_status(self, sample_analysis_json, monkeypatch):
        monkeypatch.setenv("AI_AUDIT_MODE", "strict")
        import importlib
        import analyzer as a
        importlib.reload(a)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        a._save_analysis(mock_conn, post_id=1, result=sample_analysis_json)

        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        assert params[8] == "pending"

    def test_auto_mode_sets_auto_approved_status(self, sample_analysis_json, monkeypatch):
        monkeypatch.setenv("AI_AUDIT_MODE", "auto")
        import importlib
        import analyzer as a
        importlib.reload(a)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        a._save_analysis(mock_conn, post_id=1, result=sample_analysis_json)

        call_args = mock_cur.execute.call_args
        params = call_args[0][1]
        assert params[8] == "auto_approved"


# ── _mark_no_caption ──────────────────────────────────────────────────────────

class TestMarkNoCaption:
    def test_inserts_skipped_status(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        from analyzer import _mark_no_caption
        _mark_no_caption(mock_conn, post_id=42)

        sql = mock_cur.execute.call_args[0][0]
        params = mock_cur.execute.call_args[0][1]
        assert "skipped" in sql or "skipped" in str(params)
        assert params[0] == 42

    def test_sets_ai_flagged_true_on_skip(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        from analyzer import _mark_no_caption
        _mark_no_caption(mock_conn, post_id=42)

        sql = mock_cur.execute.call_args[0][0]
        # ai_flagged = TRUE must appear in the SQL literal (not as a param)
        assert "TRUE" in sql

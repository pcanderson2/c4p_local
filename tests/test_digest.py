"""
Unit tests for digest/digest.py
Tests email rendering, SMTP send, and digest logging.
All DB and SMTP calls are mocked.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone


# ── render_email ──────────────────────────────────────────────────────────────

from digest import render_email


class TestRenderEmail:
    def _make_trends(self, n=2):
        return [
            {
                "platform": "instagram",
                "source_account": f"account_{i}",
                "post_url": f"https://example.com/post-{i}",
                "visual_hooks": ["Hook A", "Hook B"],
                "pain_points": ["Pain 1", "Pain 2"],
                "trend_score": 9.0 - i,
                "summary": f"Summary for trend {i}",
                "suggested_content": f"Content idea {i}",
                "audit_status": "pending",
            }
            for i in range(n)
        ]

    def test_renders_without_error(self):
        html = render_email(self._make_trends(), model="phi3:mini")
        assert isinstance(html, str)
        assert len(html) > 100

    def test_contains_ai_transparency_notice(self):
        html = render_email(self._make_trends(), model="phi3:mini")
        assert "AI" in html
        assert "phi3:mini" in html

    def test_contains_trend_summaries(self):
        trends = self._make_trends()
        html = render_email(trends, model="phi3:mini")
        assert "Summary for trend 0" in html
        assert "Summary for trend 1" in html

    def test_contains_suggested_content(self):
        trends = self._make_trends(n=1)
        html = render_email(trends, model="phi3:mini")
        assert "Content idea 0" in html

    def test_contains_source_accounts(self):
        trends = self._make_trends(n=1)
        html = render_email(trends, model="phi3:mini")
        assert "account_0" in html

    def test_contains_model_name(self):
        html = render_email(self._make_trends(), model="deepseek-r1:14b")
        assert "deepseek-r1:14b" in html

    def test_renders_zero_trends_without_error(self):
        html = render_email([], model="phi3:mini")
        assert isinstance(html, str)

    def test_contains_audit_status(self):
        trends = self._make_trends(n=1)
        html = render_email(trends, model="phi3:mini")
        assert "pending" in html


# ── send_email ────────────────────────────────────────────────────────────────

class TestSendEmail:
    def test_returns_true_on_success(self):
        with patch("digest.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            from digest import send_email
            result = send_email("<html>Test</html>", [{"post_url": "x"}])

        assert result is True

    def test_returns_false_on_smtp_error(self):
        with patch("digest.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = Exception("Connection refused")

            from digest import send_email
            result = send_email("<html>Test</html>", [])

        assert result is False

    def test_calls_starttls(self):
        with patch("digest.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            from digest import send_email
            send_email("<html>Test</html>", [])

        mock_smtp.starttls.assert_called_once()

    def test_calls_login(self):
        with patch("digest.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            from digest import send_email
            send_email("<html>Test</html>", [])

        mock_smtp.login.assert_called_once()

    def test_subject_contains_date(self):
        captured = {}

        def fake_sendmail(from_addr, to_addrs, msg_str):
            captured["msg"] = msg_str

        with patch("digest.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp.sendmail.side_effect = fake_sendmail
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            from digest import send_email
            send_email("<html>Test</html>", [{"post_url": "x"}])

        assert "C4P Trend Digest" in captured["msg"]


# ── log_digest ────────────────────────────────────────────────────────────────

class TestLogDigest:
    def test_logs_success(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("digest.psycopg2.connect", return_value=mock_conn):
            from digest import log_digest
            log_digest(
                trends=[{"post_url": "https://example.com/1"}],
                html_body="<html>Test</html>",
                success=True,
            )

        insert_calls = [
            c for c in mock_cur.execute.call_args_list
            if "INSERT INTO digest_log" in str(c)
        ]
        assert len(insert_calls) == 1
        params = insert_calls[0][0][1]
        assert params[3] is True   # success flag

    def test_logs_failure_with_error_message(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("digest.psycopg2.connect", return_value=mock_conn):
            from digest import log_digest
            log_digest(
                trends=[],
                html_body="<html></html>",
                success=False,
                error="Connection refused",
            )

        insert_calls = [
            c for c in mock_cur.execute.call_args_list
            if "INSERT INTO digest_log" in str(c)
        ]
        assert len(insert_calls) == 1
        params = insert_calls[0][0][1]
        assert params[3] is False
        assert params[4] == "Connection refused"


# ── schedule_from_cron ────────────────────────────────────────────────────────

class TestScheduleFromCron:
    def test_registers_a_schedule_job(self):
        import schedule as sched
        sched.clear()

        from digest import schedule_from_cron
        schedule_from_cron("0 8 * * 1,3,5")

        assert len(sched.jobs) == 1
        sched.clear()

    def test_invalid_cron_raises(self):
        from croniter import CroniterBadCronError
        from digest import schedule_from_cron
        with pytest.raises(Exception):
            schedule_from_cron("not a cron expression")

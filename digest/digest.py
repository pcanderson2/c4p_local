"""
C4P Email Digest — MWF (Mon/Wed/Fri) 8 AM
Queries the top 5 mission-aligned trends from the past 7 days and emails them.
"""
import logging
import os
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import psycopg2
import psycopg2.extras
import schedule
from croniter import croniter
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [digest] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL  = os.environ["DATABASE_URL"]
SMTP_HOST     = os.environ["SMTP_HOST"]
SMTP_PORT     = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER     = os.environ["SMTP_USER"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]
DIGEST_FROM   = os.environ["DIGEST_FROM"]
DIGEST_TO     = [r.strip() for r in os.environ["DIGEST_TO"].split(",") if r.strip()]
DIGEST_CRON   = os.environ.get("DIGEST_CRON", "0 8 * * 1,3,5")

jinja = Environment(loader=FileSystemLoader("/app"))


def fetch_top_trends(limit: int = 5) -> list[dict]:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    sp.platform,
                    sp.source_account,
                    sp.post_url,
                    pa.visual_hooks,
                    pa.pain_points,
                    pa.trend_score,
                    pa.summary,
                    pa.suggested_content,
                    pa.model_used,
                    pa.audit_status
                FROM post_analysis pa
                JOIN scraped_posts sp ON sp.id = pa.post_id
                WHERE pa.analyzed_at >= NOW() - INTERVAL '7 days'
                  AND pa.trend_score IS NOT NULL
                  AND pa.audit_status != 'rejected'
                ORDER BY pa.trend_score DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def render_email(trends: list[dict], model: str) -> str:
    template = jinja.get_template("template.html")
    return template.render(
        date=datetime.now(timezone.utc).strftime("%A, %B %-d %Y"),
        trends=trends,
        model=model,
    )


def send_email(html_body: str, trends: list[dict]) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"C4P Trend Digest — {datetime.now(timezone.utc).strftime('%b %-d')}: Top {len(trends)} Digital Literacy Trends"
    msg["From"]    = DIGEST_FROM
    msg["To"]      = ", ".join(DIGEST_TO)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(DIGEST_FROM, DIGEST_TO, msg.as_string())
        log.info("Digest sent to %s", DIGEST_TO)
        return True
    except Exception as exc:
        log.error("SMTP send failed: %s", exc)
        return False


def log_digest(trends: list[dict], html_body: str, success: bool, error: str | None = None):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        post_ids = []
        for t in trends:
            # post_url is unique — look up the id
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM scraped_posts WHERE post_url = %s", (t.get("post_url"),))
                row = cur.fetchone()
                if row:
                    post_ids.append(row[0])
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO digest_log (recipients, top_post_ids, email_body, success, error_msg)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (DIGEST_TO, post_ids, html_body, success, error),
                )
    finally:
        conn.close()


def run_digest():
    log.info("Running digest...")
    trends = fetch_top_trends()
    if not trends:
        log.info("No analyzed trends found — skipping digest.")
        return

    model = trends[0].get("model_used", "unknown") if trends else "unknown"
    html  = render_email(trends, model)
    ok    = send_email(html, trends)
    log_digest(trends, html, ok)


def schedule_from_cron(cron_expr: str):
    """Convert a cron expression to a schedule job using croniter."""
    base = datetime.now(timezone.utc)
    cron = croniter(cron_expr, base)

    def _tick():
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        next_run = cron.get_next(datetime).replace(tzinfo=timezone.utc, second=0, microsecond=0)
        if now >= next_run:
            run_digest()
            cron.get_next()  # advance iterator

    schedule.every(60).seconds.do(_tick)


if __name__ == "__main__":
    log.info("Digest service starting. Cron: %s | Recipients: %s", DIGEST_CRON, DIGEST_TO)
    schedule_from_cron(DIGEST_CRON)
    while True:
        schedule.run_pending()
        time.sleep(30)

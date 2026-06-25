"""
C4P Email Digest — MWF (Mon/Wed/Fri) 8 AM
Sends a sectioned email separated by source and genre.
Sections:
  - YouTube Tech & Education (analyzed posts)
  - YouTube Music Trending
  - Last.fm Genre Charts
  - Billboard Charts
  - Tech & Education News (RSS)
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


def fetch_section(cur, platform, limit=8, genre=None):
    """Fetch top analyzed posts for a given platform (and optional genre)."""
    genre_filter = "AND sp.raw_json->>'genre' = %s" if genre else ""
    params = [platform] + ([genre] if genre else []) + [limit]
    cur.execute(
        f"""
        SELECT
            sp.platform,
            sp.source_account,
            sp.post_url,
            sp.caption,
            sp.views,
            sp.likes,
            sp.raw_json->>'title' AS title,
            sp.raw_json->>'genre' AS genre,
            sp.raw_json->>'artist' AS artist,
            pa.trend_score,
            pa.summary,
            pa.suggested_content,
            pa.audit_status,
            pa.visual_hooks,
            pa.pain_points
        FROM scraped_posts sp
        LEFT JOIN post_analysis pa ON pa.post_id = sp.id
        WHERE sp.platform = %s
          AND sp.scraped_at >= NOW() - INTERVAL '7 days'
          {genre_filter}
          AND (pa.audit_status IS NULL OR pa.audit_status != 'rejected')
        ORDER BY COALESCE(pa.trend_score, 0) DESC, sp.views DESC NULLS LAST
        LIMIT %s
        """,
        params,
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_lastfm_by_genre(cur, limit=5):
    """Fetch Last.fm top tracks grouped by genre."""
    cur.execute(
        """
        SELECT
            sp.source_account AS genre,
            sp.raw_json->>'artist' AS artist,
            sp.raw_json->>'title' AS title,
            sp.post_url,
            sp.views AS playcount,
            sp.raw_json->>'rank' AS rank
        FROM scraped_posts sp
        WHERE sp.platform = 'lastfm'
          AND sp.scraped_at >= NOW() - INTERVAL '7 days'
        ORDER BY sp.source_account, (sp.raw_json->>'rank')::int NULLS LAST
        LIMIT 100
        """,
    )
    rows = cur.fetchall()
    # Group by genre
    genres = {}
    for r in rows:
        g = r["genre"]
        if g not in genres:
            genres[g] = []
        if len(genres[g]) < limit:
            genres[g].append(dict(r))
    return genres


def fetch_billboard(cur, limit=5):
    """Fetch Billboard entries grouped by genre."""
    cur.execute(
        """
        SELECT
            sp.source_account AS chart,
            sp.raw_json->>'title' AS title,
            sp.post_url,
            sp.scraped_at
        FROM scraped_posts sp
        WHERE sp.platform = 'billboard'
          AND sp.scraped_at >= NOW() - INTERVAL '7 days'
        ORDER BY sp.source_account, sp.scraped_at DESC
        LIMIT 100
        """,
    )
    rows = cur.fetchall()
    charts = {}
    for r in rows:
        chart = r["chart"]
        if chart not in charts:
            charts[chart] = []
        if len(charts[chart]) < limit:
            charts[chart].append({"chart": r["chart"], "title": r["title"], "url": r["post_url"]})
    return charts


def fetch_creator_music(cur, limit=20):
    """Fetch music credits extracted from tech creator videos."""
    cur.execute(
        """
        SELECT
            sp.source_account AS channel,
            sp.raw_json->>'title' AS credit,
            sp.raw_json->>'video_title' AS video_title,
            sp.raw_json->>'video_url' AS video_url,
            sp.scraped_at
        FROM scraped_posts sp
        WHERE sp.platform = 'yt-creator-music'
          AND sp.scraped_at >= NOW() - INTERVAL '7 days'
        ORDER BY sp.source_account, sp.scraped_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    # Group by channel
    channels = {}
    for r in rows:
        ch = r["channel"]
        if ch not in channels:
            channels[ch] = []
        channels[ch].append(dict(r))
    return channels



    """Fetch top RSS articles."""
    cur.execute(
        """
        SELECT
            sp.source_account,
            sp.raw_json->>'title' AS title,
            sp.post_url,
            sp.raw_json->>'source' AS source_name,
            pa.trend_score,
            pa.summary
        FROM scraped_posts sp
        LEFT JOIN post_analysis pa ON pa.post_id = sp.id
        WHERE sp.platform = 'rss'
          AND sp.scraped_at >= NOW() - INTERVAL '7 days'
          AND (pa.audit_status IS NULL OR pa.audit_status != 'rejected')
        ORDER BY COALESCE(pa.trend_score, 0) DESC, sp.scraped_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_rss(cur, limit=8):
    """Fetch top RSS articles."""
    cur.execute(
        """
        SELECT
            sp.source_account,
            sp.raw_json->>'title' AS title,
            sp.post_url,
            sp.raw_json->>'source' AS source_name,
            pa.trend_score,
            pa.summary
        FROM scraped_posts sp
        LEFT JOIN post_analysis pa ON pa.post_id = sp.id
        WHERE sp.platform = 'rss'
          AND sp.scraped_at >= NOW() - INTERVAL '7 days'
          AND (pa.audit_status IS NULL OR pa.audit_status != 'rejected')
        ORDER BY COALESCE(pa.trend_score, 0) DESC, sp.scraped_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_all_sections():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            return {
                "yt_tech": fetch_section(cur, "youtube", limit=8),
                "yt_music": fetch_section(cur, "youtube-music", limit=10),
                "creator_music": fetch_creator_music(cur, limit=30),
                "lastfm": fetch_lastfm_by_genre(cur, limit=5),
                "billboard": fetch_billboard(cur, limit=5),
                "rss": fetch_rss(cur, limit=8),
            }
    finally:
        conn.close()


def render_email(sections: dict) -> str:
    template = jinja.get_template("template.html")
    return template.render(
        date=datetime.now(timezone.utc).strftime("%A, %B %-d %Y"),
        **sections,
    )


def send_email(html_body: str, subject: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = DIGEST_FROM
    msg["To"] = ", ".join(DIGEST_TO)
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


def log_digest(html_body: str, success: bool, error: str = None):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO digest_log (recipients, email_body, success, error_msg)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (DIGEST_TO, html_body, success, error),
                )
    finally:
        conn.close()


def run_digest():
    log.info("Running digest...")
    sections = fetch_all_sections()
    total = (
        len(sections["yt_tech"]) + len(sections["yt_music"]) +
        sum(len(v) for v in sections["creator_music"].values()) +
        sum(len(v) for v in sections["lastfm"].values()) +
        sum(len(v) for v in sections["billboard"].values()) +
        len(sections["rss"])
    )
    if total == 0:
        log.info("No content found — skipping digest.")
        return

    date_str = datetime.now(timezone.utc).strftime("%b %-d")
    subject = f"C4P Digest — {date_str}: Tech, Education & Music Trends"
    html = render_email(sections)
    ok = send_email(html, subject)
    log_digest(html, ok)


def schedule_from_cron(cron_expr: str):
    base = datetime.now(timezone.utc)
    cron = croniter(cron_expr, base)

    def _tick():
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        next_run = cron.get_next(datetime).replace(tzinfo=timezone.utc, second=0, microsecond=0)
        if now >= next_run:
            run_digest()
            cron.get_next()

    schedule.every(60).seconds.do(_tick)


if __name__ == "__main__":
    log.info("Digest service starting. Cron: %s | Recipients: %s", DIGEST_CRON, DIGEST_TO)
    schedule_from_cron(DIGEST_CRON)
    while True:
        schedule.run_pending()
        time.sleep(30)





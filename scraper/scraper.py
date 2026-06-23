"""
C4P Social Scraper
Polls public profiles via Instaloader (Instagram) and gallery-dl (everything else).
Writes raw post metadata to PostgreSQL. Respects rate limits.
"""
import os
import json
import time
import logging
import subprocess
import tempfile
from datetime import datetime, timezone

import schedule
import instaloader
import psycopg2
from psycopg2.extras import Json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scraper] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL    = os.environ["DATABASE_URL"]
IG_TARGETS      = [t.strip() for t in os.environ.get("INSTAGRAM_TARGETS", "").split(",") if t.strip()]
GDL_TARGETS     = [t.strip() for t in os.environ.get("GALLERY_DL_TARGETS", "").split(",") if t.strip()]
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", 21600))
CACHE_DIR       = "/app/cache"

os.makedirs(CACHE_DIR, exist_ok=True)


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def upsert_post(cur, platform: str, account: str, url: str, data: dict):
    cur.execute(
        """
        INSERT INTO scraped_posts
            (platform, source_account, post_url, caption, hashtags,
             likes, comments, views, raw_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (post_url) DO NOTHING
        RETURNING id
        """,
        (
            platform,
            account,
            url,
            data.get("caption"),
            data.get("hashtags", []),
            data.get("likes"),
            data.get("comments"),
            data.get("views"),
            Json(data),
        ),
    )
    row = cur.fetchone()
    return row[0] if row else None


# ── Instagram via Instaloader ─────────────────────────────────────────────────

def scrape_instagram():
    if not IG_TARGETS:
        return
    log.info("Starting Instagram scrape for: %s", IG_TARGETS)
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
        max_connection_attempts=3,
    )

    conn = get_conn()
    for username in IG_TARGETS:
        try:
            profile = instaloader.Profile.from_username(loader.context, username)
            log.info("Scraping @%s (%d posts)", username, profile.mediacount)
            count = 0
            for post in profile.get_posts():
                if count >= 20:   # cap per run to avoid rate-limits
                    break
                hashtags = [t.lstrip("#") for t in (post.caption or "").split() if t.startswith("#")]
                data = {
                    "shortcode": post.shortcode,
                    "caption": post.caption,
                    "hashtags": hashtags,
                    "likes": post.likes,
                    "comments": post.comments,
                    "views": getattr(post, "video_view_count", None),
                    "timestamp": post.date_utc.isoformat(),
                    "typename": post.typename,
                    "is_video": post.is_video,
                }
                url = f"https://www.instagram.com/p/{post.shortcode}/"
                with conn:
                    with conn.cursor() as cur:
                        pid = upsert_post(cur, "instagram", username, url, data)
                        if pid:
                            log.info("  Saved new post id=%s from @%s", pid, username)
                count += 1
                time.sleep(2)   # be polite
        except Exception as exc:
            log.warning("Instagram error for @%s: %s", username, exc)
    conn.close()


# ── Generic sources via gallery-dl ────────────────────────────────────────────

def scrape_gallery_dl():
    if not GDL_TARGETS:
        return
    log.info("Starting gallery-dl scrape for %d targets", len(GDL_TARGETS))
    conn = get_conn()
    for url in GDL_TARGETS:
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
                out_path = tf.name

            result = subprocess.run(
                [
                    "gallery-dl",
                    "--dump-json",
                    "--no-download",
                    "--range", "1-15",   # first 15 items per target
                    "--write-metadata",
                    "-o", "filename=-",  # no file writes
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode not in (0, 1):
                log.warning("gallery-dl non-zero exit %d for %s", result.returncode, url)

            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or not line.startswith("["):
                    continue
                try:
                    record = json.loads(line)
                    # gallery-dl outputs [queue_pos, url, metadata_dict]
                    if not isinstance(record, list) or len(record) < 3:
                        continue
                    meta = record[2] if isinstance(record[2], dict) else {}
                    post_url = record[1] if isinstance(record[1], str) else str(record[1])
                    platform = meta.get("category", "unknown")
                    account  = meta.get("uploader") or meta.get("channel") or url
                    data = {
                        "caption": meta.get("description") or meta.get("title"),
                        "hashtags": meta.get("tags", []),
                        "likes": meta.get("like_count"),
                        "comments": meta.get("comment_count"),
                        "views": meta.get("view_count"),
                        "timestamp": meta.get("upload_date"),
                    }
                    data.update(meta)
                    with conn:
                        with conn.cursor() as cur:
                            pid = upsert_post(cur, platform, account, post_url, data)
                            if pid:
                                log.info("  Saved new post id=%s from %s", pid, platform)
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
        except subprocess.TimeoutExpired:
            log.warning("gallery-dl timed out for %s", url)
        except Exception as exc:
            log.warning("gallery-dl error for %s: %s", url, exc)
    conn.close()


def run_scrape():
    log.info("=== Scrape cycle starting ===")
    scrape_instagram()
    scrape_gallery_dl()
    log.info("=== Scrape cycle complete ===")


if __name__ == "__main__":
    log.info("Scraper starting. Interval: %ds. IG targets: %s", SCRAPE_INTERVAL, IG_TARGETS)
    run_scrape()                                      # run immediately on boot
    schedule.every(SCRAPE_INTERVAL).seconds.do(run_scrape)
    while True:
        schedule.run_pending()
        time.sleep(30)

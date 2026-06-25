"""
C4P Social Scraper v2
Sources:
  - YouTube Data API v3  (tech/education channels + music trending)
  - Last.fm API          (genre charts)
  - Billboard RSS        (Hot 100 + genre charts)
  - RSS feeds            (tech/education orgs)
"""
import os
import time
import logging
import hashlib
import requests
import feedparser
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timezone

import schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scraper] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL     = os.environ["DATABASE_URL"]
SCRAPE_INTERVAL  = int(os.environ.get("SCRAPE_INTERVAL", 3600))
YT_API_KEY       = os.environ.get("YOUTUBE_API_KEY", "")
LASTFM_API_KEY   = os.environ.get("LASTFM_API_KEY", "")
LASTFM_SECRET    = os.environ.get("LASTFM_SECRET", "")

# ── YouTube tech/education channels ──────────────────────────────────────────
YOUTUBE_TECH_CHANNELS = [
    ("UCoxcjq-8xIDTYp3uz647V5A", "Numberphile"),
    ("UCsooa4yRKGN_zEE8iknghZA", "TED-Ed"),
    ("UC6nSFpj9HTCZ5t-N3Rm3-HA", "Vsauce"),
    ("UCbmNph6atAoGfqLoCL_duAg", "Veritasium"),
    ("UCWX3yGbODI3RHtmpPvB3UvA", "Khan Academy"),
    ("UCIwaH4oI8hRlbA3HsyeMHzw", "MIT OpenCourseWare"),
    ("UCnUYZLuoy1rq1aVMwx4aTzw", "Crash Course"),
    ("UCJXGnMNhMsdVMRZVYMp5JOA", "PBS NewsHour"),
    ("UCVTyTA7KZpC4vmozuHS_Ldg", "NPR"),
    ("UCTD_vxDn55KZCBiSLMYbgmQ", "Edutopia"),
]

# ── YouTube music trending playlist ID ───────────────────────────────────────
YT_MUSIC_TRENDING_PLAYLIST = "PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"

# ── Last.fm genre tags to pull top tracks from ───────────────────────────────
LASTFM_GENRES = [
    "hip-hop", "pop", "rock", "electronic", "r&b",
    "indie", "jazz", "classical", "country", "latin"
]

# ── Billboard RSS feeds ───────────────────────────────────────────────────────
BILLBOARD_FEEDS = [
    ("https://www.billboard.com/c/chart-beat/feed/", "billboard", "Hot 100"),
    ("https://www.billboard.com/c/music/pop/feed/", "billboard", "Pop"),
    ("https://www.billboard.com/c/music/hip-hop-rap/feed/", "billboard", "Hip-Hop"),
    ("https://www.billboard.com/c/music/rock/feed/", "billboard", "Rock"),
    ("https://www.billboard.com/c/music/country/feed/", "billboard", "Country"),
    ("https://www.billboard.com/c/music/latin/feed/", "billboard", "Latin"),
    ("https://www.billboard.com/c/music/r-b-hip-hop/feed/", "billboard", "R&B"),
]

# ── Tech/education RSS feeds ──────────────────────────────────────────────────
TECH_RSS_FEEDS = [
    ("https://feeds.npr.org/1001/rss.xml",                          "npr",            "NPR News"),
    ("https://www.pbs.org/feeds/all/",                              "pbs",            "PBS"),
    ("https://www.wired.com/feed/rss",                              "wired",          "Wired"),
    ("https://www.technologyreview.com/feed/",                      "mittech",        "MIT Tech Review"),
    ("https://www.fastcompany.com/technology/rss",                  "fastcompany",    "Fast Company Tech"),
    ("https://www.edutopia.org/rss.xml",                            "edutopia",       "Edutopia"),
    ("https://www.commonsensemedia.org/rss.xml",                    "commonsensemedia","Common Sense Media"),
    ("https://iste.org/feed",                                       "iste",           "ISTE"),
    ("https://digitalundivided.com/feed",                           "digitalundivided","digitalundivided"),
    ("https://www.everyoneon.org/feed/",                            "everyoneon",     "EveryoneOn"),
    ("https://digitalpromise.org/feed/",                            "digitalpromise", "Digital Promise"),
    ("https://blog.ted.com/feed/",                                  "ted",            "TED Blog"),
    ("https://techequitycollaborative.org/feed/",                   "techequity",     "Tech Equity Collaborative"),
    ("https://news.mit.edu/rss/topic/artificial-intelligence",      "mit",            "MIT AI News"),
    ("https://khanacademy.org/feed/",                               "khanacademy",    "Khan Academy Blog"),
]


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def upsert_post(cur, platform, account, url, data):
    # Deduplicate by URL; if no URL generate a stable hash
    if not url:
        url = "hash:" + hashlib.md5(
            f"{platform}{account}{data.get('caption','')}".encode()
        ).hexdigest()
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


# ── YouTube ───────────────────────────────────────────────────────────────────

def yt_search_channel(channel_id, channel_name, max_results=10):
    """Fetch latest videos/shorts from a YouTube channel."""
    if not YT_API_KEY:
        log.warning("YOUTUBE_API_KEY not set — skipping YouTube")
        return
    log.info("YouTube: scraping %s", channel_name)
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "key": YT_API_KEY,
                "channelId": channel_id,
                "part": "snippet",
                "order": "date",
                "maxResults": max_results,
                "type": "video",
            },
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("items", [])

        # Get video stats in one batch call
        video_ids = [i["id"]["videoId"] for i in items if "videoId" in i.get("id", {})]
        stats = {}
        if video_ids:
            sr = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "key": YT_API_KEY,
                    "id": ",".join(video_ids),
                    "part": "statistics,contentDetails",
                },
                timeout=15,
            )
            sr.raise_for_status()
            for v in sr.json().get("items", []):
                stats[v["id"]] = v

        conn = get_conn()
        for item in items:
            vid_id = item.get("id", {}).get("videoId")
            if not vid_id:
                continue
            snippet = item["snippet"]
            stat = stats.get(vid_id, {}).get("statistics", {})
            duration = stats.get(vid_id, {}).get("contentDetails", {}).get("duration", "")
            url = f"https://www.youtube.com/watch?v={vid_id}"
            data = {
                "caption": snippet.get("title") + "\n" + snippet.get("description", "")[:300],
                "title": snippet.get("title"),
                "description": snippet.get("description", "")[:500],
                "hashtags": snippet.get("tags", []),
                "likes": int(stat.get("likeCount", 0)) or None,
                "comments": int(stat.get("commentCount", 0)) or None,
                "views": int(stat.get("viewCount", 0)) or None,
                "duration": duration,
                "published_at": snippet.get("publishedAt"),
                "channel": channel_name,
                "content_type": "short" if "PT" in duration and "M" not in duration else "video",
            }
            with conn:
                with conn.cursor() as cur:
                    pid = upsert_post(cur, "youtube", channel_name, url, data)
                    if pid:
                        log.info("  Saved YouTube video id=%s: %s", pid, snippet.get("title", "")[:60])
        conn.close()
    except Exception as e:
        log.warning("YouTube error for %s: %s", channel_name, e)


def yt_music_trending(max_results=25):
    """Fetch YouTube music trending videos."""
    if not YT_API_KEY:
        return
    log.info("YouTube: fetching music trending")
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "key": YT_API_KEY,
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "videoCategoryId": "10",  # Music category
                "maxResults": max_results,
                "regionCode": "US",
            },
            timeout=15,
        )
        r.raise_for_status()
        conn = get_conn()
        for item in r.json().get("items", []):
            vid_id = item["id"]
            snippet = item["snippet"]
            stat = item.get("statistics", {})
            url = f"https://www.youtube.com/watch?v={vid_id}"
            data = {
                "caption": snippet.get("title"),
                "title": snippet.get("title"),
                "description": snippet.get("description", "")[:500],
                "hashtags": snippet.get("tags", []),
                "likes": int(stat.get("likeCount", 0)) or None,
                "comments": int(stat.get("commentCount", 0)) or None,
                "views": int(stat.get("viewCount", 0)) or None,
                "published_at": snippet.get("publishedAt"),
                "channel": snippet.get("channelTitle"),
                "genre": "music-trending",
            }
            with conn:
                with conn.cursor() as cur:
                    pid = upsert_post(cur, "youtube-music", snippet.get("channelTitle", "unknown"), url, data)
                    if pid:
                        log.info("  Saved YouTube music: %s", snippet.get("title", "")[:60])
        conn.close()
    except Exception as e:
        log.warning("YouTube music trending error: %s", e)


def scrape_youtube():
    for channel_id, channel_name in YOUTUBE_TECH_CHANNELS:
        yt_search_channel(channel_id, channel_name)
        time.sleep(1)
    yt_music_trending()


# ── Last.fm ───────────────────────────────────────────────────────────────────

def scrape_lastfm():
    if not LASTFM_API_KEY:
        log.warning("LASTFM_API_KEY not set — skipping Last.fm")
        return
    log.info("Last.fm: fetching genre charts")
    conn = get_conn()
    for genre in LASTFM_GENRES:
        try:
            r = requests.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "tag.gettoptracks",
                    "tag": genre,
                    "api_key": LASTFM_API_KEY,
                    "format": "json",
                    "limit": 15,
                },
                timeout=15,
            )
            r.raise_for_status()
            tracks = r.json().get("tracks", {}).get("track", [])
            for track in tracks:
                artist = track.get("artist", {}).get("name", "unknown")
                title = track.get("name", "")
                url = track.get("url", "")
                data = {
                    "caption": f"{artist} — {title}",
                    "title": title,
                    "artist": artist,
                    "genre": genre,
                    "hashtags": [genre, "music"],
                    "views": int(track.get("playcount", 0)) or None,
                    "listeners": int(track.get("listeners", 0)) or None,
                    "rank": track.get("@attr", {}).get("rank"),
                }
                with conn:
                    with conn.cursor() as cur:
                        pid = upsert_post(cur, "lastfm", genre, url, data)
                        if pid:
                            log.info("  Saved Last.fm [%s]: %s — %s", genre, artist, title)
            time.sleep(0.5)
        except Exception as e:
            log.warning("Last.fm error for genre %s: %s", genre, e)
    conn.close()


# ── Billboard RSS ─────────────────────────────────────────────────────────────

def scrape_billboard():
    log.info("Billboard: fetching charts RSS")
    conn = get_conn()
    for feed_url, platform, genre in BILLBOARD_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                url = entry.get("link", "")
                summary = entry.get("summary", "")
                data = {
                    "caption": title + "\n" + summary[:300],
                    "title": title,
                    "genre": genre,
                    "hashtags": ["music", genre.lower().replace(" ", "-"), "billboard"],
                    "published": entry.get("published", ""),
                }
                with conn:
                    with conn.cursor() as cur:
                        pid = upsert_post(cur, platform, f"Billboard {genre}", url, data)
                        if pid:
                            log.info("  Saved Billboard [%s]: %s", genre, title[:60])
        except Exception as e:
            log.warning("Billboard RSS error for %s: %s", genre, e)
    conn.close()


# ── Tech/Education RSS ────────────────────────────────────────────────────────

def scrape_tech_rss():
    log.info("RSS: fetching tech/education feeds")
    conn = get_conn()
    for feed_url, account, source_name in TECH_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                url = entry.get("link", "")
                summary = entry.get("summary", "")
                tags = [t.get("term", "") for t in entry.get("tags", [])]
                data = {
                    "caption": title + "\n" + summary[:500],
                    "title": title,
                    "description": summary[:500],
                    "hashtags": tags,
                    "published": entry.get("published", ""),
                    "source": source_name,
                }
                with conn:
                    with conn.cursor() as cur:
                        pid = upsert_post(cur, "rss", account, url, data)
                        if pid:
                            log.info("  Saved RSS [%s]: %s", source_name, title[:60])
        except Exception as e:
            log.warning("RSS error for %s: %s", source_name, e)
    conn.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def run_scrape():
    log.info("=== Scrape cycle starting ===")
    scrape_youtube()
    scrape_lastfm()
    scrape_billboard()
    scrape_tech_rss()
    log.info("=== Scrape cycle complete ===")


if __name__ == "__main__":
    log.info("Scraper v2 starting. Interval: %ds", SCRAPE_INTERVAL)
    run_scrape()
    schedule.every(SCRAPE_INTERVAL).seconds.do(run_scrape)
    while True:
        schedule.run_pending()
        time.sleep(30)

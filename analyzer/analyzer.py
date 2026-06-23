"""
C4P Analyzer
Polls PostgreSQL for unanalyzed posts, sends each to DeepSeek R1 via Ollama,
writes structured results back. All AI output is flagged ai_flagged=TRUE.
"""
import json
import logging
import os
import re
import time

import httpx
import psycopg2
import schedule
from prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [analyzer] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
LLM_MODEL    = os.environ.get("LLM_MODEL", "deepseek-r1:14b")
AUDIT_MODE   = os.environ.get("AI_AUDIT_MODE", "strict")
POLL_SECONDS = 60


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def call_ollama(prompt: str) -> str:
    """Send a chat completion request to the local Ollama instance."""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def extract_json(raw: str) -> dict:
    """Pull the first JSON object out of a model response."""
    # DeepSeek R1 sometimes wraps output in <think>…</think> blocks
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in model output: {raw[:300]}")
    return json.loads(match.group())


def analyze_pending():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sp.id, sp.platform, sp.source_account,
                       sp.caption, sp.hashtags, sp.likes, sp.comments, sp.views
                FROM scraped_posts sp
                LEFT JOIN post_analysis pa ON pa.post_id = sp.id
                WHERE pa.id IS NULL
                ORDER BY sp.scraped_at ASC
                LIMIT 10
                """
            )
            rows = cur.fetchall()

        if not rows:
            log.debug("No unanalyzed posts.")
            return

        log.info("Analyzing %d posts...", len(rows))
        for row in rows:
            post_id, platform, account, caption, hashtags, likes, comments, views = row
            if not caption:
                log.info("  Skipping post %s (no caption)", post_id)
                _mark_no_caption(conn, post_id)
                continue

            prompt = ANALYSIS_PROMPT.format(
                platform=platform,
                account=account,
                caption=(caption or "")[:1000],
                hashtags=", ".join(hashtags or []),
                likes=likes or 0,
                comments=comments or 0,
                views=views or 0,
            )
            try:
                raw = call_ollama(prompt)
                result = extract_json(raw)
                _save_analysis(conn, post_id, result)
                log.info("  post_id=%s score=%.1f audit=%s", post_id, result.get("trend_score", 0), AUDIT_MODE)
            except Exception as exc:
                log.warning("  Failed to analyze post %s: %s", post_id, exc)
                time.sleep(5)
    finally:
        conn.close()


def _save_analysis(conn, post_id: int, result: dict):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO post_analysis
                    (post_id, model_used, visual_hooks, pain_points,
                     trend_score, summary, suggested_content,
                     ai_flagged, audit_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s)
                ON CONFLICT (post_id) DO NOTHING
                """,
                (
                    post_id,
                    LLM_MODEL,
                    result.get("visual_hooks", []),
                    result.get("pain_points", []),
                    result.get("trend_score"),
                    result.get("summary"),
                    result.get("suggested_content"),
                    "pending" if AUDIT_MODE == "strict" else "auto_approved",
                ),
            )


def _mark_no_caption(conn, post_id: int):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO post_analysis
                    (post_id, model_used, summary, ai_flagged, audit_status)
                VALUES (%s, %s, 'Skipped — no caption', TRUE, 'skipped')
                ON CONFLICT (post_id) DO NOTHING
                """,
                (post_id, LLM_MODEL),
            )


if __name__ == "__main__":
    log.info("Analyzer starting. Model: %s | Audit mode: %s", LLM_MODEL, AUDIT_MODE)
    # Wait for Ollama to be ready
    for _ in range(20):
        try:
            httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5).raise_for_status()
            log.info("Ollama is ready.")
            break
        except Exception:
            log.info("Waiting for Ollama...")
            time.sleep(10)

    analyze_pending()
    schedule.every(POLL_SECONDS).seconds.do(analyze_pending)
    while True:
        schedule.run_pending()
        time.sleep(10)

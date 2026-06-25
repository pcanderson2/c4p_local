-- C4P Social Monitor — PostgreSQL schema

-- ── Raw scraped posts ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scraped_posts (
    id              BIGSERIAL PRIMARY KEY,
    platform        TEXT NOT NULL,          -- instagram | youtube | twitter | etc.
    source_account  TEXT NOT NULL,
    post_url        TEXT UNIQUE,
    caption         TEXT,
    hashtags        TEXT[],
    likes           INTEGER,
    comments        INTEGER,
    views           INTEGER,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_json        JSONB
);

CREATE INDEX IF NOT EXISTS idx_scraped_posts_platform ON scraped_posts(platform);
CREATE INDEX IF NOT EXISTS idx_scraped_posts_scraped_at ON scraped_posts(scraped_at DESC);

-- ── LLM analysis results ─────────────────────────────────────────────────────
-- NOTE: post_analysis is intentionally NOT created here.
-- Postiz (Prisma) manages this table via db push on startup.
-- The view v_weekly_trends is created after Postiz migrations complete.

-- ── Digest log ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS digest_log (
    id              BIGSERIAL PRIMARY KEY,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recipients      TEXT[],
    top_post_ids    BIGINT[],
    email_body      TEXT,
    success         BOOLEAN NOT NULL DEFAULT FALSE,
    error_msg       TEXT
);

-- ── Scheduled content queue ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_queue (
    id              BIGSERIAL PRIMARY KEY,
    analysis_id     BIGINT,
    platform_target TEXT NOT NULL,
    draft_text      TEXT NOT NULL,
    ai_flagged      BOOLEAN NOT NULL DEFAULT TRUE,
    audit_status    TEXT NOT NULL DEFAULT 'pending',
    scheduled_for   TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
-- NOTE: Postiz (Prisma) also uses this database but manages its own tables.
-- post_analysis is our custom table — Prisma does not touch it.
-- The v_weekly_trends view is intentionally omitted here; create it manually
-- after the stack is running if needed.
CREATE TABLE IF NOT EXISTS post_analysis (
    id              BIGSERIAL PRIMARY KEY,
    post_id         BIGINT NOT NULL REFERENCES scraped_posts(id) ON DELETE CASCADE,
    model_used      TEXT NOT NULL,
    visual_hooks    TEXT[],
    pain_points     TEXT[],
    trend_score     NUMERIC(4,2),
    summary         TEXT,
    suggested_content TEXT,
    ai_flagged      BOOLEAN NOT NULL DEFAULT TRUE,
    audit_status    TEXT NOT NULL DEFAULT 'pending',
    audit_note      TEXT,
    analyzed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(post_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_trend_score ON post_analysis(trend_score DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_audit_status ON post_analysis(audit_status);

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
    analysis_id     BIGINT REFERENCES post_analysis(id),
    platform_target TEXT NOT NULL,
    draft_text      TEXT NOT NULL,
    ai_flagged      BOOLEAN NOT NULL DEFAULT TRUE,
    audit_status    TEXT NOT NULL DEFAULT 'pending',
    scheduled_for   TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

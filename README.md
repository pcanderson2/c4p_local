# C4P Social Media Monitor — Fully Local

Self-hosted social media monitoring and AI content generation for Computers 4 People.

```
┌──────────────┐   scrape   ┌──────────────┐   analyze  ┌──────────────┐
│   Instaloader │──────────▶│  PostgreSQL   │───────────▶│  DeepSeek R1  │
│  gallery-dl  │           │   (posts +    │            │  via Ollama   │
└──────────────┘           │   analysis)   │            └──────────────┘
                           └──────┬────────┘                    │
                                  │ top trends                  │ hooks +
                                  ▼                             │ pain points
                           ┌──────────────┐                     │
                           │  MWF Email   │◀────────────────────┘
                           │   Digest     │
                           └──────────────┘
                           ┌──────────────┐
                           │    Postiz    │  content scheduling dashboard
                           │  :5000/:3000 │
                           └──────────────┘
```

## Quick Start

### 1. Prerequisites
- Docker Desktop (with Compose v2)
- NVIDIA GPU with CUDA drivers (optional but recommended for 14B/32B models)
- 16 GB RAM minimum (32 GB recommended for the 32B model)

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set passwords, targets, SMTP credentials
```

### 3. Start the stack

```bash
docker compose up -d
```

On first boot `ollama-init` will pull the DeepSeek R1 model (~9 GB for 14B).
Monitor with:

```bash
docker compose logs -f ollama-init   # watch model download
docker compose logs -f scraper       # watch scraping
docker compose logs -f analyzer      # watch LLM analysis
```

### 4. Open the dashboard

Postiz scheduling UI → http://localhost:5000

### 5. Approve AI content

All AI-generated content enters the database with `audit_status = 'pending'`.
Run this query to review and approve/reject before it reaches the queue:

```sql
SELECT pa.id, sp.post_url, pa.summary, pa.suggested_content, pa.trend_score
FROM post_analysis pa
JOIN scraped_posts sp ON sp.id = pa.post_id
WHERE pa.audit_status = 'pending'
ORDER BY pa.trend_score DESC;

-- Approve a finding:
UPDATE post_analysis SET audit_status = 'approved', audit_note = 'Reviewed by [name]'
WHERE id = <id>;

-- Reject a finding:
UPDATE post_analysis SET audit_status = 'rejected', audit_note = 'Off-brand'
WHERE id = <id>;
```

## Service Reference

| Service      | Port  | Description                              |
|-------------|-------|------------------------------------------|
| postgres    | 5432  | All data storage                         |
| ollama      | 11434 | Local LLM API (DeepSeek R1)              |
| scraper     | —     | Instaloader + gallery-dl polling loop    |
| analyzer    | —     | LLM analysis of unprocessed posts        |
| digest      | —     | MWF email digest (cron-driven)           |
| postiz      | 5000/3000 | Content scheduling dashboard         |

## AI Transparency

Every row in `post_analysis` has:
- `ai_flagged = TRUE` — always set, never nullable
- `audit_status` — `pending | approved | rejected | auto_approved | skipped`
- `model_used` — exact model string (e.g. `deepseek-r1:14b`)
- `audit_note` — free-text reviewer comment

Set `AI_AUDIT_MODE=strict` in `.env` (default) to require human approval before
content enters the scheduling queue. `auto` skips the approval gate.

## Email Digest

Sent Monday / Wednesday / Friday at 8 AM UTC by default.
Change via `DIGEST_CRON` in `.env` (standard 5-field cron syntax).

## Switching Models

Edit `LLM_MODEL` in `.env`:

```
LLM_MODEL=deepseek-r1:32b   # higher quality, needs ~20 GB VRAM
LLM_MODEL=deepseek-r1:14b   # default, needs ~10 GB VRAM
```

Then restart: `docker compose restart ollama-init analyzer`

## Stopping Everything

```bash
docker compose down          # keeps data volumes
docker compose down -v       # also deletes all data (destructive)
```

import sys
import os
import pytest

# Make each service directory importable without installing packages
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analyzer"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraper"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "digest"))

# Stub environment variables required by each module at import time
os.environ.setdefault("DATABASE_URL", "postgresql://c4p:test@localhost:5432/c4p_test")
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("LLM_MODEL", "phi3:mini")
os.environ.setdefault("AI_AUDIT_MODE", "strict")
os.environ.setdefault("INSTAGRAM_TARGETS", "")
os.environ.setdefault("GALLERY_DL_TARGETS", "")
os.environ.setdefault("SCRAPE_INTERVAL", "21600")
os.environ.setdefault("SMTP_HOST", "localhost")
os.environ.setdefault("SMTP_PORT", "1025")
os.environ.setdefault("SMTP_USER", "test")
os.environ.setdefault("SMTP_PASSWORD", "test")
os.environ.setdefault("DIGEST_FROM", "from@test.local")
os.environ.setdefault("DIGEST_TO", "to@test.local")
os.environ.setdefault("DIGEST_CRON", "0 8 * * 1,3,5")


@pytest.fixture
def sample_post():
    return {
        "id": 1,
        "platform": "instagram",
        "source_account": "digitalequity",
        "post_url": "https://www.instagram.com/p/ABC123/",
        "caption": "Rural broadband gap leaves millions without access. #digitalequity #broadband",
        "hashtags": ["digitalequity", "broadband"],
        "likes": 1200,
        "comments": 88,
        "views": None,
    }


@pytest.fixture
def sample_analysis_json():
    return {
        "visual_hooks": ["Side-by-side map contrast", "Oversized stat callout"],
        "pain_points": ["Unequal access to opportunity", "Policy complexity confusion"],
        "trend_score": 8.5,
        "summary": "Highlights the rural broadband divide affecting digital equity.",
        "suggested_content": "5 ways to check if your district qualifies for ACP funding.",
    }

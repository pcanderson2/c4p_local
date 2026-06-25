import os
import psycopg2
from flask import Flask, render_template_string

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>C4P Social Monitor</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f6fa; color: #222; }
    header { background: #1a1a2e; color: white; padding: 20px 32px; display: flex; align-items: center; gap: 16px; }
    header h1 { font-size: 1.4rem; font-weight: 600; }
    header .sub { font-size: 0.85rem; opacity: 0.6; }
    .stats { display: flex; gap: 16px; padding: 24px 32px 0; }
    .stat { background: white; border-radius: 10px; padding: 18px 24px; flex: 1; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
    .stat .num { font-size: 2rem; font-weight: 700; color: #1a1a2e; }
    .stat .label { font-size: 0.8rem; color: #888; margin-top: 2px; }
    .section { padding: 24px 32px; }
    .section h2 { font-size: 1rem; font-weight: 600; margin-bottom: 14px; color: #444; text-transform: uppercase; letter-spacing: 0.05em; }
    table { width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
    th { background: #1a1a2e; color: white; padding: 12px 16px; text-align: left; font-size: 0.8rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
    td { padding: 12px 16px; border-bottom: 1px solid #f0f0f0; font-size: 0.88rem; vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #fafbff; }
    .badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
    .badge.approved { background: #d4edda; color: #155724; }
    .badge.pending { background: #fff3cd; color: #856404; }
    .badge.rejected { background: #f8d7da; color: #721c24; }
    .score { font-weight: 700; color: #1a1a2e; }
    .platform { background: #e8eaf6; color: #3949ab; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
    .caption { max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #555; }
    .empty { text-align: center; padding: 48px; color: #aaa; font-size: 0.95rem; }
    .refresh { float: right; font-size: 0.8rem; color: #aaa; }
  </style>
</head>
<body>
<header>
  <div>
    <h1>C4P Social Monitor</h1>
    <div class="sub">Read-only dashboard</div>
  </div>
  <div class="refresh" style="margin-left:auto">Auto-refresh every 60s</div>
</header>

<div class="stats">
  <div class="stat"><div class="num">{{ stats.total_posts }}</div><div class="label">Scraped Posts</div></div>
  <div class="stat"><div class="num">{{ stats.analyzed }}</div><div class="label">Analyzed</div></div>
  <div class="stat"><div class="num">{{ stats.pending }}</div><div class="label">Pending Review</div></div>
  <div class="stat"><div class="num">{{ stats.digests }}</div><div class="label">Digests Sent</div></div>
</div>

<div class="section">
  <h2>Top Analyzed Posts (by trend score)</h2>
  {% if posts %}
  <table>
    <thead>
      <tr>
        <th>Platform</th>
        <th>Account</th>
        <th>Caption</th>
        <th>Score</th>
        <th>Status</th>
        <th>Summary</th>
        <th>Analyzed</th>
      </tr>
    </thead>
    <tbody>
      {% for p in posts %}
      <tr>
        <td><span class="platform">{{ p.platform }}</span></td>
        <td>{{ p.source_account }}</td>
        <td><div class="caption" title="{{ p.caption }}">{{ p.caption or '—' }}</div></td>
        <td><span class="score">{{ p.trend_score or '—' }}</span></td>
        <td><span class="badge {{ p.audit_status }}">{{ p.audit_status }}</span></td>
        <td><div class="caption" title="{{ p.summary }}">{{ p.summary or '—' }}</div></td>
        <td>{{ p.analyzed_at.strftime('%b %d %H:%M') if p.analyzed_at else '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">No analyzed posts yet — the analyzer is running in the background.</div>
  {% endif %}
</div>

<div class="section">
  <h2>Recent Scraped Posts</h2>
  {% if scraped %}
  <table>
    <thead>
      <tr>
        <th>Platform</th>
        <th>Account</th>
        <th>Caption</th>
        <th>Likes</th>
        <th>Views</th>
        <th>Scraped</th>
      </tr>
    </thead>
    <tbody>
      {% for p in scraped %}
      <tr>
        <td><span class="platform">{{ p.platform }}</span></td>
        <td>{{ p.source_account }}</td>
        <td><div class="caption" title="{{ p.caption }}">{{ p.caption or '—' }}</div></td>
        <td>{{ p.likes or '—' }}</td>
        <td>{{ p.views or '—' }}</td>
        <td>{{ p.scraped_at.strftime('%b %d %H:%M') if p.scraped_at else '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">No scraped posts yet — the scraper is running in the background.</div>
  {% endif %}
</div>

<div class="section">
  <h2>Digest Log</h2>
  {% if digests %}
  <table>
    <thead>
      <tr><th>Sent At</th><th>Recipients</th><th>Status</th><th>Error</th></tr>
    </thead>
    <tbody>
      {% for d in digests %}
      <tr>
        <td>{{ d.sent_at.strftime('%b %d %H:%M') if d.sent_at else '—' }}</td>
        <td>{{ ', '.join(d.recipients) if d.recipients else '—' }}</td>
        <td><span class="badge {{ 'approved' if d.success else 'rejected' }}">{{ 'sent' if d.success else 'failed' }}</span></td>
        <td>{{ d.error_msg or '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">No digests sent yet.</div>
  {% endif %}
</div>

<script>setTimeout(() => location.reload(), 60000);</script>
</body>
</html>
"""

@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    # Stats
    cur.execute("SELECT COUNT(*) FROM scraped_posts")
    total_posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM post_analysis")
    analyzed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM post_analysis WHERE audit_status = 'pending'")
    pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM digest_log WHERE success = TRUE")
    digests = cur.fetchone()[0]

    # Top posts by trend score
    cur.execute("""
        SELECT sp.platform, sp.source_account, sp.caption,
               pa.trend_score, pa.audit_status, pa.summary, pa.analyzed_at
        FROM post_analysis pa
        JOIN scraped_posts sp ON sp.id = pa.post_id
        ORDER BY pa.trend_score DESC NULLS LAST
        LIMIT 20
    """)
    cols = [d[0] for d in cur.description]
    posts = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Recent scraped
    cur.execute("""
        SELECT platform, source_account, caption, likes, views, scraped_at
        FROM scraped_posts ORDER BY scraped_at DESC LIMIT 20
    """)
    cols = [d[0] for d in cur.description]
    scraped = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Digest log
    cur.execute("SELECT sent_at, recipients, success, error_msg FROM digest_log ORDER BY sent_at DESC LIMIT 10")
    cols = [d[0] for d in cur.description]
    digest_rows = [dict(zip(cols, row)) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return render_template_string(TEMPLATE,
        stats=type('S', (), {'total_posts': total_posts, 'analyzed': analyzed, 'pending': pending, 'digests': digests})(),
        posts=posts,
        scraped=scraped,
        digests=digest_rows
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

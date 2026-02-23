#!/usr/bin/env python3
"""
Pipeline Dashboard — lightweight Flask app to monitor the AI content pipeline.

Usage:
  python dashboard.py                  # Start on port 5050
  python dashboard.py --port 8080      # Custom port
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string

# Ensure project root is on sys.path so config/database imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from database import Database

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

LOG_DIR = Config.OUTPUTS_DIR / "logs"


def _db() -> Database:
    """Return a fresh Database handle (short-lived per request)."""
    return Database()


def _api_key_status() -> list[dict]:
    """Check which API keys are configured (never expose the actual keys)."""
    keys = [
        ("APIFY_API_TOKEN", Config.APIFY_API_TOKEN, "Apify — content scraping"),
        ("GEMINI_API_KEY", Config.GEMINI_API_KEY, "Gemini — content analysis"),
        ("HIGGSFIELD_API_KEY", Config.HIGGSFIELD_API_KEY, "Higgsfield — video generation"),
        ("ELEVENLABS_API_KEY", Config.ELEVENLABS_API_KEY, "ElevenLabs — voice synthesis"),
        ("BLOTATO_API_KEY", Config.BLOTATO_API_KEY, "Blotato — post scheduling"),
    ]
    return [
        {"name": name, "configured": bool(val), "description": desc}
        for name, val, desc in keys
    ]


def _recent_logs(lines: int = 200) -> str:
    """Read the tail of today's log file."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"pipeline_{today}.log"
    if not log_file.exists():
        # Try to find the most recent log
        logs = sorted(LOG_DIR.glob("pipeline_*.log"), reverse=True)
        if not logs:
            return "No log files found yet. Run the pipeline to generate logs."
        log_file = logs[0]
    try:
        all_lines = log_file.read_text().splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception as exc:
        return f"Error reading log: {exc}"


def _scrape_json_files() -> list[dict]:
    """List saved scrape JSON files from the logs directory."""
    files = []
    for f in sorted(LOG_DIR.glob("scrape_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            files.append({
                "name": f.name,
                "items": len(data) if isinstance(data, list) else 0,
                "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            })
        except Exception:
            files.append({"name": f.name, "items": "?", "modified": "?"})
    return files


def _output_files() -> dict[str, list[dict]]:
    """List generated output files."""
    result: dict[str, list[dict]] = {}
    for label, directory in [
        ("videos", Config.VIDEOS_DIR),
        ("audio", Config.AUDIO_DIR),
        ("final", Config.FINAL_DIR),
    ]:
        entries = []
        if directory.exists():
            for f in sorted(directory.iterdir(), reverse=True):
                if f.is_file():
                    size_mb = f.stat().st_size / (1024 * 1024)
                    entries.append({
                        "name": f.name,
                        "size": f"{size_mb:.1f} MB",
                        "modified": datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                    })
        result[label] = entries
    return result


# ---------------------------------------------------------------------------
# JSON API endpoints (for programmatic access / JS refresh)
# ---------------------------------------------------------------------------


@app.route("/api/summary")
def api_summary():
    db = _db()
    summary = db.pipeline_summary()
    all_items = db.get_all_contents()
    db.close()
    return jsonify({
        "status_counts": summary,
        "total": sum(summary.values()) if summary else 0,
        "recent_items": all_items[:20],
    })


@app.route("/api/queue")
def api_queue():
    db = _db()
    items = db.get_all_contents()
    db.close()
    return jsonify(items)


@app.route("/api/posts")
def api_posts():
    db = _db()
    posts = db.get_post_logs()
    db.close()
    return jsonify(posts)


@app.route("/api/logs")
def api_logs():
    return jsonify({"log": _recent_logs(300)})


@app.route("/api/config")
def api_config():
    return jsonify({
        "api_keys": _api_key_status(),
        "soul_id": bool(Config.SOUL_ID),
        "voice_id": bool(Config.ELEVENLABS_VOICE_ID),
        "posts_per_day": Config.POSTS_PER_DAY,
        "platforms": Config.PLATFORMS,
        "approval_mode": Config.APPROVAL_MODE,
    })


@app.route("/api/outputs")
def api_outputs():
    return jsonify(_output_files())


@app.route("/healthz")
def healthz():
    """Health check for Fly.io / load balancers."""
    try:
        db = _db()
        db.pipeline_summary()
        db.close()
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 503


# ---------------------------------------------------------------------------
# Main HTML dashboard (single-page, self-contained)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Content Pipeline — Dashboard</title>
<style>
  :root {
    --bg: #0f1117;
    --card: #1a1d27;
    --border: #2a2d3a;
    --text: #e4e4e7;
    --muted: #8b8d97;
    --accent: #6366f1;
    --green: #22c55e;
    --yellow: #eab308;
    --red: #ef4444;
    --blue: #3b82f6;
    --orange: #f97316;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 24px; line-height: 1.5;
  }
  h1 { font-size: 1.5rem; margin-bottom: 4px; }
  .subtitle { color: var(--muted); font-size: 0.85rem; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px;
  }
  .card h2 { font-size: 0.9rem; color: var(--muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
  .big-number { font-size: 2.5rem; font-weight: 700; }
  .stat-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border); }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: var(--muted); }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 9999px;
    font-size: 0.75rem; font-weight: 600;
  }
  .badge-pending   { background: #eab30820; color: var(--yellow); }
  .badge-generating { background: #3b82f620; color: var(--blue); }
  .badge-generated { background: #6366f120; color: var(--accent); }
  .badge-scheduled { background: #22c55e20; color: var(--green); }
  .badge-failed    { background: #ef444420; color: var(--red); }
  .badge-ok   { background: #22c55e20; color: var(--green); }
  .badge-miss { background: #ef444420; color: var(--red); }

  /* Key status */
  .key-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); }
  .key-row:last-child { border-bottom: none; }
  .key-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .key-dot.ok { background: var(--green); }
  .key-dot.miss { background: var(--red); }
  .key-name { font-weight: 600; font-size: 0.85rem; }
  .key-desc { color: var(--muted); font-size: 0.78rem; }

  /* Table */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
  th { text-align: left; color: var(--muted); padding: 8px 12px; border-bottom: 2px solid var(--border); font-weight: 600; }
  td { padding: 8px 12px; border-bottom: 1px solid var(--border); }
  tr:hover td { background: #ffffff06; }

  /* Log viewer */
  .log-box {
    background: #0a0b0f; border: 1px solid var(--border); border-radius: 8px;
    padding: 16px; max-height: 400px; overflow-y: auto; font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.75rem; line-height: 1.7; white-space: pre-wrap; word-break: break-all;
  }
  .log-box .log-error { color: var(--red); }
  .log-box .log-warn  { color: var(--yellow); }
  .log-box .log-info  { color: var(--blue); }

  /* Tabs */
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
  .tab {
    padding: 8px 16px; border-radius: 8px; cursor: pointer;
    background: transparent; color: var(--muted); border: 1px solid transparent;
    font-size: 0.85rem; transition: all 0.15s;
  }
  .tab:hover { color: var(--text); background: var(--card); }
  .tab.active { background: var(--card); color: var(--text); border-color: var(--border); }
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }

  /* Refresh bar */
  .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
  .refresh-info { color: var(--muted); font-size: 0.78rem; }
  .btn {
    padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--card); color: var(--text); cursor: pointer; font-size: 0.82rem;
    transition: all 0.15s;
  }
  .btn:hover { border-color: var(--accent); color: var(--accent); }

  /* Output files */
  .file-section h3 { font-size: 0.85rem; color: var(--accent); margin: 12px 0 8px; }
  .empty { color: var(--muted); font-style: italic; font-size: 0.82rem; padding: 8px 0; }

  /* Platforms pills */
  .platform-pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill {
    padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem;
    font-weight: 600; background: #6366f120; color: var(--accent);
  }
</style>
</head>
<body>

<div class="topbar">
  <div>
    <h1>AI Content Pipeline</h1>
    <div class="subtitle">Real-time pipeline monitoring dashboard</div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;">
    <span class="refresh-info" id="last-refresh">—</span>
    <button class="btn" onclick="refreshAll()">Refresh</button>
    <label style="font-size:0.82rem;color:var(--muted);display:flex;align-items:center;gap:4px;">
      <input type="checkbox" id="auto-refresh" checked> Auto (30s)
    </label>
  </div>
</div>

<!-- Summary cards -->
<div class="grid" id="summary-cards">
  <div class="card">
    <h2>Total Items</h2>
    <div class="big-number" id="total-items">—</div>
  </div>
  <div class="card">
    <h2>Status Breakdown</h2>
    <div id="status-breakdown"><div class="empty">Loading…</div></div>
  </div>
  <div class="card">
    <h2>Configuration</h2>
    <div id="config-summary"><div class="empty">Loading…</div></div>
  </div>
</div>

<!-- Tabs -->
<div class="tabs">
  <div class="tab active" data-tab="queue">Content Queue</div>
  <div class="tab" data-tab="posts">Post Log</div>
  <div class="tab" data-tab="keys">API Keys</div>
  <div class="tab" data-tab="outputs">Output Files</div>
  <div class="tab" data-tab="logs">Pipeline Logs</div>
</div>

<!-- Queue -->
<div class="tab-panel active" id="panel-queue">
  <div class="card">
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>ID</th><th>Status</th><th>Topic</th><th>Caption</th><th>Source</th><th>Created</th><th>Updated</th>
        </tr></thead>
        <tbody id="queue-body"><tr><td colspan="7" class="empty">Loading…</td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Posts -->
<div class="tab-panel" id="panel-posts">
  <div class="card">
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>ID</th><th>Content ID</th><th>Platform</th><th>Post ID</th><th>Status</th><th>Posted At</th>
        </tr></thead>
        <tbody id="posts-body"><tr><td colspan="6" class="empty">Loading…</td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<!-- API Keys -->
<div class="tab-panel" id="panel-keys">
  <div class="card">
    <div id="keys-list"><div class="empty">Loading…</div></div>
  </div>
</div>

<!-- Outputs -->
<div class="tab-panel" id="panel-outputs">
  <div class="card" id="outputs-card"><div class="empty">Loading…</div></div>
</div>

<!-- Logs -->
<div class="tab-panel" id="panel-logs">
  <div class="card">
    <div class="log-box" id="log-box">Loading…</div>
  </div>
</div>

<script>
// Tab switching
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
  });
});

function badgeClass(status) {
  const map = { pending:'badge-pending', generating:'badge-generating', generated:'badge-generated', scheduled:'badge-scheduled', failed:'badge-failed' };
  return map[status] || 'badge-pending';
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
function trunc(s, n) { s = s || ''; return s.length > n ? s.slice(0, n) + '…' : s; }

// Fetch helpers
async function fetchJSON(url) { const r = await fetch(url); return r.json(); }

async function loadSummary() {
  const data = await fetchJSON('/api/summary');
  document.getElementById('total-items').textContent = data.total || 0;
  const bd = document.getElementById('status-breakdown');
  if (!data.status_counts || Object.keys(data.status_counts).length === 0) {
    bd.innerHTML = '<div class="empty">No items yet — run the pipeline to start.</div>';
  } else {
    bd.innerHTML = Object.entries(data.status_counts)
      .sort(([a],[b]) => a.localeCompare(b))
      .map(([s,c]) => `<div class="stat-row"><span class="stat-label">${esc(s)}</span><span class="badge ${badgeClass(s)}">${c}</span></div>`)
      .join('');
  }
}

async function loadConfig() {
  const data = await fetchJSON('/api/config');
  const el = document.getElementById('config-summary');
  el.innerHTML = `
    <div class="stat-row"><span class="stat-label">Soul ID</span><span class="badge ${data.soul_id ? 'badge-ok' : 'badge-miss'}">${data.soul_id ? 'Configured' : 'Not Set'}</span></div>
    <div class="stat-row"><span class="stat-label">Voice Clone</span><span class="badge ${data.voice_id ? 'badge-ok' : 'badge-miss'}">${data.voice_id ? 'Configured' : 'Not Set'}</span></div>
    <div class="stat-row"><span class="stat-label">Posts / Day</span><span>${data.posts_per_day}</span></div>
    <div class="stat-row"><span class="stat-label">Approval</span><span>${esc(data.approval_mode)}</span></div>
    <div class="stat-row"><span class="stat-label">Platforms</span>
      <div class="platform-pills">${(data.platforms || []).map(p => `<span class="pill">${esc(p)}</span>`).join('')}</div>
    </div>
  `;
}

async function loadQueue() {
  const items = await fetchJSON('/api/queue');
  const body = document.getElementById('queue-body');
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No content in queue. Run <code>python main.py</code> to start discovery.</td></tr>';
    return;
  }
  body.innerHTML = items.map(i => `<tr>
    <td>${i.id}</td>
    <td><span class="badge ${badgeClass(i.status)}">${esc(i.status)}</span></td>
    <td>${esc(trunc(i.topic, 60))}</td>
    <td>${esc(trunc(i.caption, 50))}</td>
    <td>${i.source_url ? `<a href="${esc(i.source_url)}" target="_blank" style="color:var(--accent)">link</a>` : '—'}</td>
    <td>${esc(i.created_at)}</td>
    <td>${esc(i.updated_at)}</td>
  </tr>`).join('');
}

async function loadPosts() {
  const posts = await fetchJSON('/api/posts');
  const body = document.getElementById('posts-body');
  if (!posts.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No posts scheduled yet.</td></tr>';
    return;
  }
  body.innerHTML = posts.map(p => `<tr>
    <td>${p.id}</td>
    <td>${p.content_id}</td>
    <td><span class="pill">${esc(p.platform)}</span></td>
    <td>${esc(trunc(p.post_id, 30))}</td>
    <td><span class="badge ${badgeClass(p.status)}">${esc(p.status)}</span></td>
    <td>${esc(p.posted_at)}</td>
  </tr>`).join('');
}

async function loadKeys() {
  const data = await fetchJSON('/api/config');
  const el = document.getElementById('keys-list');
  el.innerHTML = data.api_keys.map(k => `
    <div class="key-row">
      <div class="key-dot ${k.configured ? 'ok' : 'miss'}"></div>
      <div>
        <div class="key-name">${esc(k.name)} <span class="badge ${k.configured ? 'badge-ok' : 'badge-miss'}">${k.configured ? 'Set' : 'Missing'}</span></div>
        <div class="key-desc">${esc(k.description)}</div>
      </div>
    </div>
  `).join('');
}

async function loadOutputs() {
  const data = await fetchJSON('/api/outputs');
  const el = document.getElementById('outputs-card');
  let html = '';
  for (const [section, files] of Object.entries(data)) {
    html += `<div class="file-section"><h3>${esc(section)} (${files.length})</h3>`;
    if (!files.length) {
      html += '<div class="empty">No files yet</div>';
    } else {
      html += '<table><thead><tr><th>File</th><th>Size</th><th>Modified</th></tr></thead><tbody>';
      html += files.map(f => `<tr><td>${esc(f.name)}</td><td>${esc(f.size)}</td><td>${esc(f.modified)}</td></tr>`).join('');
      html += '</tbody></table>';
    }
    html += '</div>';
  }
  el.innerHTML = html;
}

async function loadLogs() {
  const data = await fetchJSON('/api/logs');
  const box = document.getElementById('log-box');
  if (!data.log) { box.textContent = 'No logs available.'; return; }
  // Colorize log lines
  box.innerHTML = data.log.split('\n').map(line => {
    if (/\bERROR\b/.test(line)) return `<span class="log-error">${esc(line)}</span>`;
    if (/\bWARNING\b/.test(line)) return `<span class="log-warn">${esc(line)}</span>`;
    if (/\bINFO\b/.test(line)) return `<span class="log-info">${esc(line)}</span>`;
    return esc(line);
  }).join('\n');
  box.scrollTop = box.scrollHeight;
}

async function refreshAll() {
  const ts = new Date().toLocaleTimeString();
  document.getElementById('last-refresh').textContent = 'Updated ' + ts;
  await Promise.all([loadSummary(), loadConfig(), loadQueue(), loadPosts(), loadKeys(), loadOutputs(), loadLogs()]);
}

// Initial load
refreshAll();

// Auto-refresh every 30 seconds
setInterval(() => {
  if (document.getElementById('auto-refresh').checked) refreshAll();
}, 30000);
</script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AI Content Pipeline Dashboard")
    parser.add_argument("--port", type=int, default=5050, help="Port to run on (default: 5050)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    Config.ensure_dirs()
    print(f"\n  Dashboard running at http://localhost:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()

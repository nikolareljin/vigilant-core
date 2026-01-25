"""Local web dashboard for VigilantCore."""

from __future__ import annotations

import asyncio
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, redirect, render_template_string, request, url_for

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.monitor import MonitorEngine  # noqa: E402
from utils import database  # noqa: E402
from utils.config import AppConfig, config_path, load_config, save_config  # noqa: E402
from utils.geo import detect_geo  # noqa: E402
from utils.sources import ensure_seed_feeds  # noqa: E402


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VigilantCore Live Impact Feed</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 24px; background: #f7f7fb; }
    header { display: flex; justify-content: space-between; align-items: center; }
    h1 { margin: 0 0 8px 0; }
    .meta { color: #666; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; background: white; }
    th, td { padding: 10px 12px; border-bottom: 1px solid #eee; text-align: left; }
    th { background: #f0f2f8; }
    .score-high { color: #c0392b; font-weight: 600; }
    .score-mid { color: #d35400; }
    .toolbar { margin-top: 12px; display: flex; gap: 12px; align-items: center; }
    .button { padding: 8px 14px; background: #2f4bff; color: white; border-radius: 6px; text-decoration: none; }
    .button.secondary { background: #5f6b7a; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Live Impact Feed</h1>
      <div class="meta">Subject: {{ subject }} | Location: {{ location }} | Model: {{ model }}</div>
    </div>
    <div class="toolbar">
      <a class="button secondary" href="{{ url_for('setup') }}">Edit Settings</a>
      <a class="button secondary" href="{{ url_for('data_view') }}">Data</a>
      <a class="button" href="/api/alerts" target="_blank">Raw JSON</a>
    </div>
  </header>
  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Score</th>
        <th>Title</th>
        <th>Source</th>
        <th>Relevant</th>
        <th>Prediction</th>
      </tr>
    </thead>
    <tbody id="feed"></tbody>
  </table>
  <div class="toolbar">
    <button class="button secondary" id="prevBtn">Previous 10</button>
    <button class="button secondary" id="nextBtn">Next 10</button>
    <span class="meta" id="pageLabel"></span>
  </div>

<script>
let page = 1;
async function loadFeed() {
  const res = await fetch(`/api/alerts?page=${page}&limit=10`);
  const data = await res.json();
  const tbody = document.getElementById('feed');
  tbody.innerHTML = '';
  document.getElementById('pageLabel').textContent = `Page ${data.page} of 2`;
  data.alerts.forEach(alert => {
    const tr = document.createElement('tr');
    const scoreClass = alert.impact_score >= 8 ? 'score-high' : (alert.impact_score >= 5 ? 'score-mid' : '');
    tr.innerHTML = `
      <td>${alert.created_at || ''}</td>
      <td class="${scoreClass}">${alert.impact_score ?? ''}</td>
      <td><a href="${alert.url}" target="_blank">${alert.title || ''}</a></td>
      <td>${alert.source || ''}</td>
      <td>${alert.is_relevant ? 'Yes' : 'No'}</td>
      <td>${alert.predictive_outcome || ''}</td>
    `;
    tbody.appendChild(tr);
  });
}

loadFeed();
setInterval(loadFeed, 30000);

document.getElementById('prevBtn').addEventListener('click', () => {
  if (page > 1) {
    page -= 1;
    loadFeed();
  }
});
document.getElementById('nextBtn').addEventListener('click', () => {
  if (page < 2) {
    page += 1;
    loadFeed();
  }
});
</script>
</body>
</html>
"""

DATA_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VigilantCore Data</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 24px; background: #f7f7fb; }
    pre { background: #111827; color: #f9fafb; padding: 16px; border-radius: 8px; overflow: auto; }
    .toolbar { margin-bottom: 16px; display: flex; gap: 10px; }
    a { color: #2f4bff; text-decoration: none; }
    .button { padding: 8px 14px; background: #2f4bff; color: white; border-radius: 6px; text-decoration: none; }
  </style>
</head>
<body>
  <div class="toolbar">
    <a class="button" href="{{ url_for('dashboard') }}">Back to Dashboard</a>
    <a class="button" href="{{ url_for('api_alerts') }}" target="_blank">Open JSON</a>
  </div>
  <h1>Latest Data</h1>
  <pre id="json">Loading...</pre>

  <script>
    async function loadData() {
      const res = await fetch('/api/alerts');
      const data = await res.json();
      document.getElementById('json').textContent = JSON.stringify(data, null, 2);
    }
    loadData();
  </script>
</body>
</html>
"""

SETUP_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VigilantCore Setup</title>
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 24px; background: #f7f7fb; }
    form { max-width: 700px; background: white; padding: 18px; border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
    label { display: block; margin-top: 12px; font-weight: 600; }
    input, textarea, select { width: 100%; padding: 10px; margin-top: 6px; border-radius: 6px; border: 1px solid #ddd; }
    button { margin-top: 18px; padding: 10px 16px; background: #2f4bff; color: white; border: none; border-radius: 6px; cursor: pointer; }
    .help { color: #666; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>VigilantCore Setup</h1>
  <p class="help">Enter your local area and what you want to track. Provide city/state/country/ZIP for better local feeds. We auto-detect location when possible.</p>
  <form method="post">
    <label>Event / Subject</label>
    <input name="subject" value="{{ config.subject }}" placeholder="e.g., Weather Alerts" required />

    <label>Monitoring Question (optional)</label>
    <input name="question" value="{{ config.question }}" placeholder="e.g., Probability of electric outage?" />

    <label>Prefer lighter model on 8GB or less</label>
    <select name="prefer_light_model">
      <option value="yes" {% if config.prefer_light_model %}selected{% endif %}>Yes (recommended)</option>
      <option value="no" {% if not config.prefer_light_model %}selected{% endif %}>No</option>
    </select>

    <label>Location Name</label>
    <input name="location_name" value="{{ config.location_name }}" placeholder="City, State, Country" />

    <label>ZIP Code</label>
    <input name="zip_code" value="{{ config.zip_code or '' }}" placeholder="ZIP" />

    <label>Latitude</label>
    <input name="latitude" value="{{ config.latitude or '' }}" placeholder="Optional" />

    <label>Longitude</label>
    <input name="longitude" value="{{ config.longitude or '' }}" placeholder="Optional" />

    <label>Radius (km)</label>
    <input name="radius_km" value="{{ config.radius_km }}" placeholder="50" />

    <label>Relax location filter</label>
    <select name="relax_location_filter">
      <option value="no" {% if not config.relax_location_filter %}selected{% endif %}>No (default)</option>
      <option value="yes" {% if config.relax_location_filter %}selected{% endif %}>Yes (show broader results)</option>
    </select>

    <label>RSS Feeds (auto-filled, optional)</label>
    <textarea name="rss_feeds" rows="4" placeholder="Auto-filled from major sources">{{ '\n'.join(config.rss_feeds) }}</textarea>

    <label>Only use RSS feeds listed above</label>
    <select name="use_only_rss_feeds">
      <option value="no" {% if not config.use_only_rss_feeds %}selected{% endif %}>No (include curated sources)</option>
      <option value="yes" {% if config.use_only_rss_feeds %}selected{% endif %}>Yes (only these feeds)</option>
    </select>

    <label>Disable RSS fetching</label>
    <select name="disable_rss_fetch">
      <option value="no" {% if not config.disable_rss_fetch %}selected{% endif %}>No (default)</option>
      <option value="yes" {% if config.disable_rss_fetch %}selected{% endif %}>Yes (API/search only)</option>
    </select>

    <label>Polling interval (minutes)</label>
    <input name="polling_minutes" value="{{ config.polling_minutes }}" placeholder="5" />

    <label>News API Key (optional)</label>
    <input name="news_api_key" type="password" value="{{ config.news_api_key or '' }}" />

    <label>Google CSE API Key (optional)</label>
    <input name="google_cse_api_key" type="password" value="{{ config.google_cse_api_key or '' }}" />

    <label>Google CSE CX (Search Engine ID)</label>
    <input name="google_cse_cx" value="{{ config.google_cse_cx or '' }}" placeholder="e.g., 0123456789:abcde" />

    <label>News time window (hours)</label>
    <select name="news_time_window_hours">
      {% set window = config.news_time_window_hours or 6 %}
      <option value="6" {% if window == 6 %}selected{% endif %}>Last 6 hours (default)</option>
      <option value="24" {% if window == 24 %}selected{% endif %}>Last 24 hours</option>
      <option value="72" {% if window == 72 %}selected{% endif %}>Last 72 hours</option>
      <option value="168" {% if window == 168 %}selected{% endif %}>Last 7 days</option>
    </select>

    <label>NewsAPI sort order</label>
    <select name="news_sort_by">
      {% set sort_by = (config.news_sort_by or 'popularity') %}
      <option value="popularity" {% if sort_by == "popularity" %}selected{% endif %}>Popularity (default)</option>
      <option value="publishedAt" {% if sort_by == "publishedAt" %}selected{% endif %}>Published time</option>
      <option value="relevancy" {% if sort_by == "relevancy" %}selected{% endif %}>Relevancy</option>
    </select>

    <label>Enable DuckDuckGo web search</label>
    <select name="enable_duckduckgo_search">
      <option value="yes" {% if config.enable_duckduckgo_search %}selected{% endif %}>Yes (default)</option>
      <option value="no" {% if not config.enable_duckduckgo_search %}selected{% endif %}>No</option>
    </select>

    <label>Get API Keys (opens new tabs)</label>
    <div class="help">
      <a href="https://programmablesearchengine.google.com/" target="_blank">Google CSE</a> |
      <a href="https://developers.google.com/custom-search/v1/overview" target="_blank">Google JSON API</a> |
      <a href="https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/create-bing-search-service-resource" target="_blank">Bing Search</a> |
      <a href="https://newsapi.org/" target="_blank">NewsAPI</a>
    </div>

    <button type="submit">Save & Start</button>
  </form>
</body>
</html>
"""


class MonitorService:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._engine: Optional[MonitorEngine] = None

    def start(self, config: AppConfig) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._engine = MonitorEngine(config)

        def _runner() -> None:
            asyncio.run(self._engine.run_forever())

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._engine:
            self._engine.stop()


app = Flask(__name__)
monitor_service = MonitorService()


def get_config() -> AppConfig:
    if config_path().exists():
        return load_config()
    config = AppConfig()
    geo = detect_geo()
    if geo.city or geo.region:
        config.location_name = ", ".join(
            part for part in [geo.city, geo.region] if part
        )
    if geo.postal:
        config.zip_code = geo.postal
    if geo.latitude is not None and geo.longitude is not None:
        config.latitude = geo.latitude
        config.longitude = geo.longitude
    return config


@app.route("/")
def root() -> str:
    if config_path().exists():
        return redirect(url_for("dashboard"))
    return redirect(url_for("setup"))


@app.route("/setup", methods=["GET", "POST"])
def setup() -> str:
    config = get_config()
    if request.method == "POST":
        config.subject = request.form.get("subject", "Impactful Events").strip() or "Impactful Events"
        config.location_name = request.form.get("location_name", "").strip()
        config.question = request.form.get("question", "").strip()
        config.prefer_light_model = request.form.get("prefer_light_model", "yes") == "yes"
        config.zip_code = request.form.get("zip_code") or None
        lat_val = request.form.get("latitude", "").strip()
        lon_val = request.form.get("longitude", "").strip()
        config.latitude = float(lat_val) if lat_val else None
        config.longitude = float(lon_val) if lon_val else None
        radius_val = request.form.get("radius_km", "50").strip()
        config.radius_km = int(radius_val) if radius_val else 50
        config.relax_location_filter = (
            request.form.get("relax_location_filter", "no") == "yes"
        )
        config.use_only_rss_feeds = request.form.get("use_only_rss_feeds", "no") == "yes"
        config.disable_rss_fetch = request.form.get("disable_rss_fetch", "no") == "yes"
        polling_val = request.form.get("polling_minutes", "5").strip()
        try:
            config.polling_minutes = max(1, int(polling_val))
        except ValueError:
            config.polling_minutes = 5
        window_val = request.form.get("news_time_window_hours", "6").strip()
        try:
            config.news_time_window_hours = max(1, int(window_val))
        except ValueError:
            config.news_time_window_hours = 6
        sort_by_val = request.form.get("news_sort_by", "popularity").strip()
        if sort_by_val in {"popularity", "publishedAt", "relevancy"}:
            config.news_sort_by = sort_by_val
        else:
            config.news_sort_by = "popularity"
        config.enable_duckduckgo_search = (
            request.form.get("enable_duckduckgo_search", "yes") == "yes"
        )
        config.google_cse_api_key = request.form.get("google_cse_api_key") or None
        config.google_cse_cx = request.form.get("google_cse_cx") or None
        rss_raw = request.form.get("rss_feeds", "")
        config.rss_feeds = [line.strip() for line in rss_raw.splitlines() if line.strip()]
        config.news_api_key = request.form.get("news_api_key") or None
        if not config.rss_feeds:
            config.rss_feeds = ensure_seed_feeds(config.rss_feeds)
        save_config(config)
        monitor_service.stop()
        monitor_service.start(config)
        return redirect(url_for("dashboard"))
    return render_template_string(SETUP_TEMPLATE, config=config)


@app.route("/dashboard")
def dashboard() -> str:
    config = get_config()
    if not config_path().exists():
        return redirect(url_for("setup"))
    if config and config_path().exists():
        if not config.rss_feeds:
            config.rss_feeds = ensure_seed_feeds(config.rss_feeds)
            save_config(config)
        monitor_service.start(config)
    model_name = "unknown"
    if monitor_service._engine is not None:
        model_name = monitor_service._engine.model_name
    return render_template_string(
        DASHBOARD_TEMPLATE,
        subject=config.subject,
        location=config.location_name,
        model=model_name,
    )


@app.route("/api/alerts")
def api_alerts() -> str:
    page = int(request.args.get("page", "1"))
    limit = int(request.args.get("limit", "10"))
    if page < 1:
        page = 1
    if page > 2:
        page = 2
    offset = (page - 1) * limit
    alerts = []
    for row in database.fetch_recent(200)[offset:offset + limit]:
        alerts.append(
            {
                "url": row["url"],
                "title": row["title"],
                "snippet": row["snippet"],
                "published_at": row["published_at"],
                "source": row["source"],
                "impact_score": row["impact_score"],
                "predictive_outcome": row["predictive_outcome"],
                "is_relevant": bool(row["is_relevant"]),
                "created_at": row["created_at"],
            }
        )
    return jsonify({"alerts": alerts, "page": page, "limit": limit})


@app.route("/data")
def data_view() -> str:
    return render_template_string(DATA_TEMPLATE)


def main() -> None:
    database.init_db()
    config = get_config()
    if config_path().exists():
        if not config.rss_feeds:
            config.rss_feeds = ensure_seed_feeds(config.rss_feeds)
            save_config(config)
        monitor_service.start(config)
    url = "http://127.0.0.1:8765"
    webbrowser.open(url)
    app.run(host="127.0.0.1", port=8765, debug=False)


if __name__ == "__main__":
    main()

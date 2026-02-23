"""Local web dashboard for VigilantCore."""

from __future__ import annotations

import asyncio
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, url_for

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.monitor import MonitorEngine  # noqa: E402
from utils import database  # noqa: E402
from utils.config import AppConfig, config_path, load_config, save_config  # noqa: E402
from utils.geo import detect_geo  # noqa: E402
from utils.sources import (  # noqa: E402
    ensure_seed_feeds,
    infer_region_profile,
    regional_signal_source_urls,
)
from utils.timefmt import format_alert_timestamp  # noqa: E402


DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VigilantCore Live Impact Feed</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico" />
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 24px; background: #f7f7fb; }
    header { display: flex; justify-content: space-between; align-items: center; }
    h1 { margin: 0 0 8px 0; }
    .meta { color: #666; }
    .privacy-note {
      font-size: 0.75em;
      color: #16a34a;
      margin-top: 4px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; background: white; }
    th, td { padding: 10px 12px; border-bottom: 1px solid #eee; text-align: left; }
    th { background: #f0f2f8; }
    .score-high { color: #c0392b; font-weight: 600; }
    .score-mid { color: #d35400; }
    .toolbar { margin-top: 12px; display: flex; gap: 12px; align-items: center; }
    .button { padding: 8px 14px; background: #2f4bff; color: white; border-radius: 6px; text-decoration: none; }
    .button.secondary { background: #5f6b7a; }

    /* Insight card styles */
    .insight-card {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 20px 24px;
      border-radius: 12px;
      margin: 20px 0;
      box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
      display: none;
    }
    .insight-card.visible { display: block; }
    .insight-card.loading {
      background: #e0e0e0;
      color: #666;
      display: block;
    }
    .insight-question {
      font-size: 0.85em;
      opacity: 0.9;
      margin-bottom: 8px;
      font-weight: 500;
    }
    .insight-summary {
      font-size: 1.3em;
      font-weight: 600;
      margin-bottom: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .insight-summary:hover { opacity: 0.9; }
    .insight-summary::after {
      content: '▼';
      font-size: 0.7em;
      transition: transform 0.2s;
    }
    .insight-card.expanded .insight-summary::after {
      transform: rotate(180deg);
    }
    .insight-explanation {
      display: none;
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid rgba(255,255,255,0.3);
      font-size: 0.95em;
      line-height: 1.6;
    }
    .insight-card.expanded .insight-explanation { display: block; }
    .insight-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(240px, 1fr);
      gap: 16px;
      align-items: start;
    }
    .insight-left { min-width: 0; }
    .insight-suggestions-panel {
      display: none;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 10px;
      padding: 12px 14px;
    }
    .insight-suggestions-panel.visible { display: block; }
    .insight-suggestions-title {
      font-size: 0.85em;
      font-weight: 700;
      margin-bottom: 8px;
      opacity: 0.95;
    }
    .insight-suggestions-list {
      margin: 0;
      padding-left: 18px;
      font-size: 0.9em;
      line-height: 1.4;
    }
    .insight-suggestions-list li + li { margin-top: 6px; }
    @media (max-width: 900px) {
      .insight-layout { grid-template-columns: 1fr; }
    }
    .insight-sources {
      margin-top: 12px;
      font-size: 0.85em;
      opacity: 0.8;
    }
    .insight-timestamp {
      font-size: 0.75em;
      opacity: 0.7;
      margin-top: 12px;
    }
    .insight-error {
      background: #fee2e2;
      color: #991b1b;
      padding: 12px 16px;
      border-radius: 8px;
      margin: 20px 0;
      display: none;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Live Impact Feed</h1>
      <div class="meta">Subject: {{ subject }} | Location: {{ location }} | Model: {{ model }}</div>
      <div class="privacy-note">🔒 All data processed locally by AI on this computer. Nothing is shared externally.</div>
    </div>
    <div class="toolbar">
      <a class="button secondary" href="{{ url_for('setup') }}">Edit Settings</a>
      <a class="button secondary" href="{{ url_for('data_view') }}">Data</a>
      <a class="button" href="/api/alerts" target="_blank">Raw JSON</a>
    </div>
  </header>

  <!-- Monitoring Question Insight Card -->
  <div id="insightCard" class="insight-card">
    <div class="insight-question" id="insightQuestion"></div>
    <div class="insight-layout">
      <div class="insight-left">
        <div class="insight-summary" id="insightSummary" onclick="toggleInsight()"></div>
        <div class="insight-explanation" id="insightExplanation"></div>
      </div>
      <div class="insight-suggestions-panel" id="insightSuggestionsPanel">
        <div class="insight-suggestions-title">Suggested actions</div>
        <ul class="insight-suggestions-list" id="insightSuggestionsList"></ul>
      </div>
    </div>
    <div class="insight-sources" id="insightSources"></div>
    <div class="insight-timestamp" id="insightTimestamp"></div>
  </div>
  <div id="insightError" class="insight-error"></div>

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

// Toggle insight card expansion
function toggleInsight() {
  const card = document.getElementById('insightCard');
  card.classList.toggle('expanded');
}

// Load monitoring question insight
async function loadInsight() {
  const card = document.getElementById('insightCard');
  const errorDiv = document.getElementById('insightError');

  try {
    const res = await fetch('/api/insight');
    const data = await res.json();

    if (!data.has_question) {
      card.classList.remove('visible', 'loading');
      return;
    }

    if (data.error) {
      errorDiv.textContent = data.error;
      errorDiv.style.display = 'block';
      card.classList.remove('visible', 'loading');
      return;
    }

    if (!data.summary || data.summary === 'No relevant data available.') {
      card.classList.remove('visible', 'loading');
      return;
    }

    // Populate the card
    document.getElementById('insightQuestion').textContent = data.question;
    document.getElementById('insightSummary').textContent = data.summary;
    document.getElementById('insightExplanation').textContent = data.explanation || '';
    const suggestionsPanel = document.getElementById('insightSuggestionsPanel');
    const suggestionsList = document.getElementById('insightSuggestionsList');
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    if (suggestions.length > 0) {
      suggestionsList.innerHTML = '';
      suggestions.slice(0, 5).forEach((item) => {
        const li = document.createElement('li');
        li.textContent = item;
        suggestionsList.appendChild(li);
      });
      suggestionsPanel.classList.add('visible');
    } else {
      suggestionsList.innerHTML = '';
      suggestionsPanel.classList.remove('visible');
    }

    // Show sources if available
    const sourcesDiv = document.getElementById('insightSources');
    if (data.sources_used && data.sources_used.length > 0) {
      sourcesDiv.textContent = 'Based on: ' + data.sources_used.slice(0, 5).join(', ');
    } else {
      sourcesDiv.textContent = '';
    }

    // Timestamp
    document.getElementById('insightTimestamp').textContent = 'Updated: ' + new Date().toLocaleTimeString();

    card.classList.remove('loading');
    card.classList.add('visible');
    errorDiv.style.display = 'none';
  } catch (e) {
    console.error('Failed to load insight:', e);
    card.classList.remove('visible', 'loading');
  }
}

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

// Config from server
const insightRefreshMinutes = {{ insight_refresh_minutes }};

// Initial load
loadInsight();
loadFeed();

// Refresh periodically
setInterval(loadFeed, 30000);  // Alerts every 30 seconds
setInterval(loadInsight, insightRefreshMinutes * 60 * 1000);  // Insight per config

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
  <link rel="icon" type="image/x-icon" href="/favicon.ico" />
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
  <link rel="icon" type="image/x-icon" href="/favicon.ico" />
  <style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 24px; background: #f7f7fb; }
    form { max-width: 700px; background: white; padding: 18px; border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,0.08); }
    label { display: block; margin-top: 12px; font-weight: 600; }
    input, textarea, select { width: 100%; padding: 10px; margin-top: 6px; border-radius: 6px; border: 1px solid #ddd; box-sizing: border-box; }
    button { margin-top: 18px; padding: 10px 16px; background: #2f4bff; color: white; border: none; border-radius: 6px; cursor: pointer; }
    .help { color: #666; font-size: 0.9em; }
    .section { margin-top: 28px; padding-top: 20px; border-top: 2px solid #e8e8f0; }
    .section-title { font-size: 1.1em; font-weight: 700; color: #333; margin-bottom: 4px; }
    .section-desc { font-size: 0.85em; color: #666; margin-bottom: 8px; }
    .row { display: flex; gap: 12px; }
    .row > div { flex: 1; }
    .row label { margin-top: 0; }
    .preview-card { margin-top: 14px; background: #f6f8ff; border: 1px solid #dfe5ff; border-radius: 8px; padding: 12px; }
    .preview-title { font-weight: 700; color: #22306a; margin-bottom: 6px; }
    .preview-meta { font-size: 0.9em; color: #4b5563; margin-bottom: 8px; }
    .preview-list { margin: 0; padding-left: 18px; max-height: 180px; overflow: auto; }
    .preview-actions { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
    .preview-btn { margin-top: 0; background: #5f6b7a; }
  </style>
</head>
<body>
  <h1>VigilantCore Setup</h1>
  <p class="help">Configure your local monitoring system. Provide city/state/country/ZIP for better local feeds.</p>
  <form method="post">

    <!-- MONITORING SUBJECT -->
    <div class="section-title">📋 Monitoring Subject</div>
    <div class="section-desc">What events do you want to track?</div>

    <label>Event / Subject</label>
    <input name="subject" value="{{ config.subject }}" placeholder="e.g., Weather Alerts, Power Outages" required />

    <label>Monitoring Question (optional)</label>
    <input name="question" value="{{ config.question }}" placeholder="e.g., What is the probability of electric outages at my address?" />
    <div class="help">If set, an AI-generated answer will appear above the alerts list on the dashboard.</div>

    <!-- LOCATION -->
    <div class="section">
      <div class="section-title">📍 Location</div>
      <div class="section-desc">Your location for filtering relevant alerts.</div>

      <label>Location Name</label>
      <input name="location_name" value="{{ config.location_name }}" placeholder="City, State, Country" />

      <div class="row">
        <div>
          <label>ZIP Code</label>
          <input name="zip_code" value="{{ config.zip_code or '' }}" placeholder="e.g., 08550" />
        </div>
        <div>
          <label>Radius (km)</label>
          <input name="radius_km" value="{{ config.radius_km }}" placeholder="50" type="number" />
        </div>
      </div>

      <div class="row">
        <div>
          <label>Latitude</label>
          <input name="latitude" value="{{ config.latitude or '' }}" placeholder="Optional" />
        </div>
        <div>
          <label>Longitude</label>
          <input name="longitude" value="{{ config.longitude or '' }}" placeholder="Optional" />
        </div>
      </div>

      <div class="preview-card">
        <div class="preview-title">Regional Source Preview</div>
        <div class="preview-meta" id="sourcePreviewMeta">Preview inferred region and curated source URLs for the current location / coordinates.</div>
        <ul class="preview-list" id="sourcePreviewList">
          <li>Loading preview…</li>
        </ul>
        <div class="preview-actions">
          <button type="button" class="preview-btn" id="refreshSourcePreviewBtn">Refresh Preview</button>
          <span class="help">Uses location name, ZIP, and latitude/longitude (lat/lon works even without location text).</span>
        </div>
      </div>

      <label>Relax location filter</label>
      <select name="relax_location_filter">
        <option value="no" {% if not config.relax_location_filter %}selected{% endif %}>No (default - strict matching)</option>
        <option value="yes" {% if config.relax_location_filter %}selected{% endif %}>Yes (show broader results)</option>
      </select>
    </div>

    <!-- AI SETTINGS -->
    <div class="section">
      <div class="section-title">🤖 AI Settings</div>
      <div class="section-desc">Configure Ollama LLM for impact scoring and insights.</div>

      <label>Prefer lighter model (for 8GB RAM or less)</label>
      <select name="prefer_light_model">
        <option value="yes" {% if config.prefer_light_model %}selected{% endif %}>Yes - use qwen2.5:3b (recommended for low RAM)</option>
        <option value="no" {% if not config.prefer_light_model %}selected{% endif %}>No - use qwen2.5:7b (better quality)</option>
      </select>

      <label>Insight refresh interval (minutes)</label>
      <select name="insight_refresh_minutes">
        {% set insight_mins = config.insight_refresh_minutes or 5 %}
        <option value="1" {% if insight_mins == 1 %}selected{% endif %}>Every 1 minute</option>
        <option value="5" {% if insight_mins == 5 %}selected{% endif %}>Every 5 minutes (default)</option>
        <option value="10" {% if insight_mins == 10 %}selected{% endif %}>Every 10 minutes</option>
        <option value="15" {% if insight_mins == 15 %}selected{% endif %}>Every 15 minutes</option>
        <option value="30" {% if insight_mins == 30 %}selected{% endif %}>Every 30 minutes</option>
      </select>
      <div class="help">How often to regenerate the AI insight for your monitoring question.</div>

      <label>Show AI suggested actions</label>
      <select name="enable_ai_suggestions">
        <option value="yes" {% if config.enable_ai_suggestions %}selected{% endif %}>Yes (show actionable suggestions next to the result)</option>
        <option value="no" {% if not config.enable_ai_suggestions %}selected{% endif %}>No</option>
      </select>
    </div>

    <!-- TIMING -->
    <div class="section">
      <div class="section-title">⏱️ Timing</div>
      <div class="section-desc">How often to check for new data.</div>

      <div class="row">
        <div>
          <label>Polling interval (minutes)</label>
          <input name="polling_minutes" value="{{ config.polling_minutes }}" placeholder="5" type="number" min="1" />
        </div>
        <div>
          <label>News time window</label>
          <select name="news_time_window_hours">
            {% set window = config.news_time_window_hours or 6 %}
            <option value="6" {% if window == 6 %}selected{% endif %}>Last 6 hours</option>
            <option value="24" {% if window == 24 %}selected{% endif %}>Last 24 hours</option>
            <option value="72" {% if window == 72 %}selected{% endif %}>Last 72 hours</option>
            <option value="168" {% if window == 168 %}selected{% endif %}>Last 7 days</option>
          </select>
        </div>
      </div>
    </div>

    <!-- DATA SOURCES - RSS -->
    <div class="section">
      <div class="section-title">📰 RSS Feeds</div>
      <div class="section-desc">RSS/Atom feeds to monitor.</div>

      <label>RSS Feeds (one per line, auto-filled from major sources)</label>
      <textarea name="rss_feeds" rows="4" placeholder="Auto-filled from major sources">{{ '\n'.join(config.rss_feeds) }}</textarea>

      <div class="row">
        <div>
          <label>Only use listed RSS feeds</label>
          <select name="use_only_rss_feeds">
            <option value="no" {% if not config.use_only_rss_feeds %}selected{% endif %}>No (include curated sources)</option>
            <option value="yes" {% if config.use_only_rss_feeds %}selected{% endif %}>Yes (only these feeds)</option>
          </select>
        </div>
        <div>
          <label>Disable RSS fetching</label>
          <select name="disable_rss_fetch">
            <option value="no" {% if not config.disable_rss_fetch %}selected{% endif %}>No (default)</option>
            <option value="yes" {% if config.disable_rss_fetch %}selected{% endif %}>Yes (API/search only)</option>
          </select>
        </div>
      </div>
    </div>

    <!-- DATA SOURCES - WEB SEARCH -->
    <div class="section">
      <div class="section-title">🔍 Web Search</div>
      <div class="section-desc">Search engines for finding news and alerts.</div>

      <label>Enable DuckDuckGo web search</label>
      <select name="enable_duckduckgo_search">
        <option value="yes" {% if config.enable_duckduckgo_search %}selected{% endif %}>Yes (default, no API key required)</option>
        <option value="no" {% if not config.enable_duckduckgo_search %}selected{% endif %}>No</option>
      </select>
    </div>

    <!-- DATA SOURCES - NEWS API -->
    <div class="section">
      <div class="section-title">📡 NewsAPI</div>
      <div class="section-desc">Optional: <a href="https://newsapi.org/" target="_blank">Get API key</a></div>

      <label>NewsAPI Key</label>
      <input name="news_api_key" type="password" value="{{ config.news_api_key or '' }}" placeholder="Your NewsAPI key (optional)" />

      <label>NewsAPI sort order</label>
      <select name="news_sort_by">
        {% set sort_by = (config.news_sort_by or 'popularity') %}
        <option value="popularity" {% if sort_by == "popularity" %}selected{% endif %}>Popularity (default)</option>
        <option value="publishedAt" {% if sort_by == "publishedAt" %}selected{% endif %}>Published time</option>
        <option value="relevancy" {% if sort_by == "relevancy" %}selected{% endif %}>Relevancy</option>
      </select>
    </div>

    <!-- DATA SOURCES - GOOGLE -->
    <div class="section">
      <div class="section-title">🔎 Google Custom Search</div>
      <div class="section-desc">Optional: <a href="https://programmablesearchengine.google.com/" target="_blank">Create search engine</a> | <a href="https://developers.google.com/custom-search/v1/overview" target="_blank">Get API key</a></div>

      <label>Google CSE API Key</label>
      <input name="google_cse_api_key" type="password" value="{{ config.google_cse_api_key or '' }}" placeholder="Your Google API key (optional)" />

      <label>Google CSE CX (Search Engine ID)</label>
      <input name="google_cse_cx" type="password" value="{{ config.google_cse_cx or '' }}" placeholder="e.g., 0123456789:abcde" />
    </div>

    <button type="submit">Save & Start Monitoring</button>
  </form>
  <script>
    function sourcePreviewParams() {
      const form = document.querySelector('form');
      const get = (name) => (form.querySelector(`[name="${name}"]`)?.value || '').trim();
      const params = new URLSearchParams();
      const subject = get('subject');
      const locationName = get('location_name');
      const zipCode = get('zip_code');
      const latitude = get('latitude');
      const longitude = get('longitude');
      if (subject) params.set('subject', subject);
      if (locationName) params.set('location_name', locationName);
      if (zipCode) params.set('zip_code', zipCode);
      if (latitude) params.set('latitude', latitude);
      if (longitude) params.set('longitude', longitude);
      return params;
    }

    async function loadSourcePreview() {
      const meta = document.getElementById('sourcePreviewMeta');
      const list = document.getElementById('sourcePreviewList');
      meta.textContent = 'Loading preview...';
      list.innerHTML = '<li>Loading preview…</li>';
      try {
        const params = sourcePreviewParams();
        const res = await fetch('/api/source-preview?' + params.toString());
        const data = await res.json();
        meta.textContent = `Inferred region: ${data.region_label} (${data.region_key}) | ${data.source_count} curated URLs`;
        if (!data.urls || data.urls.length === 0) {
          list.innerHTML = '<li>No curated regional URLs available for this location yet.</li>';
          return;
        }
        list.innerHTML = data.urls.slice(0, 25).map((url) => `<li><a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a></li>`).join('');
      } catch (err) {
        meta.textContent = 'Failed to load preview.';
        list.innerHTML = '<li>Could not fetch source preview.</li>';
      }
    }

    const previewFields = ['subject', 'location_name', 'zip_code', 'latitude', 'longitude'];
    for (const name of previewFields) {
      const el = document.querySelector(`[name="${name}"]`);
      if (el) {
        el.addEventListener('change', loadSourcePreview);
        el.addEventListener('blur', loadSourcePreview);
      }
    }
    document.getElementById('refreshSourcePreviewBtn').addEventListener('click', loadSourcePreview);
    loadSourcePreview();
  </script>
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


def _source_preview_payload(config: AppConfig) -> dict:
    region = infer_region_profile(
        location_name=config.location_name or "",
        zip_code=config.zip_code,
        latitude=config.latitude,
        longitude=config.longitude,
    )
    urls = regional_signal_source_urls(
        location_name=config.location_name or "",
        zip_code=config.zip_code,
        latitude=config.latitude,
        longitude=config.longitude,
    )
    return {
        "region_key": region.key,
        "region_label": region.label,
        "location_name": config.location_name or "",
        "zip_code": config.zip_code,
        "latitude": config.latitude,
        "longitude": config.longitude,
        "source_count": len(urls),
        "urls": urls,
    }


def _normalize_suggestions(value) -> list[str]:
    if isinstance(value, list):
        cleaned = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned[:5]
    if isinstance(value, str):
        lines = [line.strip("-• \t") for line in value.splitlines()]
        cleaned = [line for line in lines if line]
        if cleaned:
            return cleaned[:5]
    return []


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        ROOT_DIR / "assets",
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )


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
        config.enable_ai_suggestions = (
            request.form.get("enable_ai_suggestions", "yes") == "yes"
        )
        insight_mins_val = request.form.get("insight_refresh_minutes", "5").strip()
        try:
            config.insight_refresh_minutes = max(1, int(insight_mins_val))
        except ValueError:
            config.insight_refresh_minutes = 5
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
        insight_refresh_minutes=config.insight_refresh_minutes or 5,
    )


@app.route("/api/insight")
def api_insight() -> str:
    """Generate AI insight based on monitoring question and recent alerts."""
    config = get_config()

    # Check if there's a monitoring question
    if not config.question or not config.question.strip():
        return jsonify({"has_question": False})

    # Get recent alerts for context
    alerts = database.fetch_recent(50)
    if not alerts:
        return jsonify({
            "has_question": True,
            "question": config.question,
            "summary": "No relevant data available.",
            "explanation": "No alerts have been collected yet. Check back after the monitoring system gathers data.",
            "suggestions": [] if config.enable_ai_suggestions else [],
            "sources_used": [],
        })

    # Build context from alerts
    alert_summaries = []
    sources_used = set()
    for alert in alerts[:30]:  # Use top 30 for context
        title = alert["title"] or ""
        snippet = alert["snippet"] or ""
        source = alert["source"] or "Unknown"
        score = alert["impact_score"] or 0
        prediction = alert["predictive_outcome"] or ""
        sources_used.add(source)
        alert_summaries.append(
            f"- [{source}] (impact: {score}/10) {title}. {snippet[:200]}"
            + (f" Prediction: {prediction}" if prediction else "")
        )

    context = "\n".join(alert_summaries)

    # Use Ollama to generate insight
    try:
        from ollama import Client as OllamaClient
    except ImportError:
        return jsonify({
            "has_question": True,
            "question": config.question,
            "error": "Ollama not available",
        })

    try:
        client = OllamaClient()
        model = "qwen2.5:7b"

        # Check available models
        resp = client.list()
        models = resp.models if hasattr(resp, "models") else resp.get("models", [])
        available = set()
        for m in models:
            if hasattr(m, "model"):
                available.add(m.model)
            elif isinstance(m, dict) and m.get("name"):
                available.add(m.get("name"))

        if model not in available and available:
            model = next(iter(available))

        system_prompt = (
            f"You are an intelligence analyst. Based on the collected news and alerts about "
            f"'{config.subject}' in '{config.location_name}', answer the user's monitoring question. "
            f"Be concise, factual, and cite specific alerts when relevant. "
            f"If asked about probability or likelihood, provide a percentage estimate with brief reasoning."
        )

        prompt_lines = [
            f"MONITORING QUESTION: {config.question}",
            "",
            "RECENT ALERTS AND NEWS:",
            context,
            "",
            "Provide your response as JSON with these keys:",
            '- "summary": A 1-2 sentence direct answer (include probability % if asked about likelihood)',
            '- "explanation": A 2-4 sentence detailed explanation of how you reached this conclusion, citing specific sources',
        ]
        if config.enable_ai_suggestions:
            prompt_lines.append(
                '- "suggestions": 2-5 short actionable suggestions for what the user should do and how to react in this specific situation (safety-first, context-aware, concise)'
            )
        prompt_lines.append("Respond with ONLY valid JSON, no other text.")
        user_prompt = "\n".join(prompt_lines)

        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        content = response.get("message", {}).get("content", "{}").strip()

        # Parse JSON response
        import json
        try:
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            payload = json.loads(content)
        except json.JSONDecodeError:
            # Fallback: treat entire response as summary
            payload = {"summary": content[:300], "explanation": content}

        return jsonify({
            "has_question": True,
            "question": config.question,
            "summary": payload.get("summary", "Unable to generate summary."),
            "explanation": payload.get("explanation", ""),
            "suggestions": _normalize_suggestions(payload.get("suggestions")) if config.enable_ai_suggestions else [],
            "sources_used": list(sources_used)[:10],
        })

    except Exception as e:
        return jsonify({
            "has_question": True,
            "question": config.question,
            "error": f"Failed to generate insight: {str(e)}",
        })


@app.route("/api/alerts")
def api_alerts() -> str:
    config = get_config()
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
                "created_at": format_alert_timestamp(row["created_at"], config.display_timezone),
            }
        )
    return jsonify({"alerts": alerts, "page": page, "limit": limit})


@app.route("/api/source-preview")
def api_source_preview() -> str:
    config = get_config()
    config.subject = request.args.get("subject", config.subject or "Impactful Events").strip() or "Impactful Events"
    config.location_name = request.args.get("location_name", config.location_name or "").strip()
    zip_code = (request.args.get("zip_code") or "").strip()
    config.zip_code = zip_code or None
    lat_raw = (request.args.get("latitude") or "").strip()
    lon_raw = (request.args.get("longitude") or "").strip()
    try:
        config.latitude = float(lat_raw) if lat_raw else None
    except ValueError:
        config.latitude = None
    try:
        config.longitude = float(lon_raw) if lon_raw else None
    except ValueError:
        config.longitude = None
    return jsonify(_source_preview_payload(config))


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

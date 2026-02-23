"""VigilantCore desktop UI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.monitor import MonitorEngine  # noqa: E402
from utils import database  # noqa: E402
from utils.config import AppConfig, config_path, load_config, save_config  # noqa: E402
from utils.timefmt import format_alert_timestamp  # noqa: E402


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


def generate_insight(config: AppConfig) -> Optional[Dict]:
    """Generate AI insight based on monitoring question and recent alerts."""
    if not config.question or not config.question.strip():
        return None

    alerts = database.fetch_recent(50)
    if not alerts:
        return {
            "question": config.question,
            "summary": "No relevant data available.",
            "explanation": "No alerts have been collected yet.",
            "suggestions": [],
            "sources_used": [],
        }

    # Build context from alerts
    alert_summaries = []
    sources_used = set()
    for alert in alerts[:30]:
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

    try:
        from ollama import Client as OllamaClient
    except ImportError:
        return {"question": config.question, "error": "Ollama not available"}

    try:
        client = OllamaClient()
        model = "qwen2.5:7b"

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
            '- "explanation": A 2-4 sentence detailed explanation of how you reached this conclusion',
        ]
        if config.enable_ai_suggestions:
            prompt_lines.append(
                '- "suggestions": 2-5 short actionable suggestions for what the user should do next or how to react (specific to this situation and location; safety-first)'
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

        try:
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {"summary": content[:300], "explanation": content}

        return {
            "question": config.question,
            "summary": payload.get("summary", "Unable to generate summary."),
            "explanation": payload.get("explanation", ""),
            "suggestions": _normalize_suggestions(payload.get("suggestions")) if config.enable_ai_suggestions else [],
            "sources_used": list(sources_used)[:10],
        }

    except Exception as e:
        return {"question": config.question, "error": str(e)}


class InsightThread(QtCore.QThread):
    """Background thread to generate AI insights."""
    insight_ready = QtCore.Signal(dict)

    def __init__(self, config: AppConfig, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._running = True

    def run(self) -> None:
        import time
        interval_seconds = max(60, (self.config.insight_refresh_minutes or 5) * 60)

        while self._running:
            result = generate_insight(self.config)
            if result:
                self.insight_ready.emit(result)

            # Sleep in small increments to allow stopping
            for _ in range(int(interval_seconds)):
                if not self._running:
                    break
                time.sleep(1)

    def stop(self) -> None:
        self._running = False


class InsightWidget(QtWidgets.QFrame):
    """Expandable widget to display AI-generated insight."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameStyle(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet("""
            InsightWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 10px;
                padding: 8px;
            }
            QLabel { color: white; }
        """)
        self.setVisible(False)
        self._expanded = False

        # Question label
        self.question_label = QtWidgets.QLabel()
        self.question_label.setStyleSheet("font-size: 11px; opacity: 0.9;")
        self.question_label.setWordWrap(True)

        # Summary label (clickable)
        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.summary_label.setWordWrap(True)
        self.summary_label.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.summary_label.mousePressEvent = self._toggle_expanded

        # Expand indicator
        self.expand_indicator = QtWidgets.QLabel("▼ Click to expand")
        self.expand_indicator.setStyleSheet("font-size: 10px; opacity: 0.7;")

        # Explanation (hidden by default)
        self.explanation_label = QtWidgets.QLabel()
        self.explanation_label.setStyleSheet("font-size: 13px; margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.3);")
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setVisible(False)

        # Suggestions (visible next to/with the result)
        self.suggestions_label = QtWidgets.QLabel()
        self.suggestions_label.setStyleSheet(
            "font-size: 12px; margin-top: 8px; padding: 8px; "
            "background: rgba(255,255,255,0.12); border-radius: 6px;"
        )
        self.suggestions_label.setWordWrap(True)
        self.suggestions_label.setVisible(False)

        # Sources
        self.sources_label = QtWidgets.QLabel()
        self.sources_label.setStyleSheet("font-size: 10px; opacity: 0.8; margin-top: 8px;")
        self.sources_label.setWordWrap(True)
        self.sources_label.setVisible(False)

        # Timestamp
        self.timestamp_label = QtWidgets.QLabel()
        self.timestamp_label.setStyleSheet("font-size: 9px; opacity: 0.6; margin-top: 4px;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(self.question_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.suggestions_label)
        layout.addWidget(self.expand_indicator)
        layout.addWidget(self.explanation_label)
        layout.addWidget(self.sources_label)
        layout.addWidget(self.timestamp_label)

    def _toggle_expanded(self, event) -> None:
        self._expanded = not self._expanded
        self.explanation_label.setVisible(self._expanded)
        self.sources_label.setVisible(self._expanded)
        self.expand_indicator.setText("▲ Click to collapse" if self._expanded else "▼ Click to expand")

    def update_insight(self, data: Dict) -> None:
        if data.get("error"):
            self.setVisible(False)
            return

        summary = data.get("summary", "")
        if not summary or summary == "No relevant data available.":
            self.setVisible(False)
            return

        self.question_label.setText(f"📋 {data.get('question', '')}")
        self.summary_label.setText(summary)
        self.explanation_label.setText(data.get("explanation", ""))
        suggestions = _normalize_suggestions(data.get("suggestions"))
        if suggestions:
            self.suggestions_label.setText(
                "Suggested actions:\n" + "\n".join(f"- {item}" for item in suggestions)
            )
            self.suggestions_label.setVisible(True)
        else:
            self.suggestions_label.setText("")
            self.suggestions_label.setVisible(False)

        sources = data.get("sources_used", [])
        if sources:
            self.sources_label.setText("Based on: " + ", ".join(sources[:5]))
        else:
            self.sources_label.setText("")

        from datetime import datetime
        self.timestamp_label.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

        self.setVisible(True)


class FirstRunDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VigilantCore Setup")
        self.setMinimumWidth(520)
        self.display_timezone_value: str | None = None

        self.subject_input = QtWidgets.QLineEdit()
        self.question_input = QtWidgets.QLineEdit()
        self.light_model_checkbox = QtWidgets.QCheckBox("Prefer lighter model on 8GB or less")
        self.location_input = QtWidgets.QLineEdit()
        self.zip_input = QtWidgets.QLineEdit()
        self.lat_input = QtWidgets.QLineEdit()
        self.lon_input = QtWidgets.QLineEdit()
        self.radius_input = QtWidgets.QLineEdit()
        self.relax_location_checkbox = QtWidgets.QCheckBox("Relax location filter")
        self.rss_input = QtWidgets.QPlainTextEdit()
        self.use_only_rss_checkbox = QtWidgets.QCheckBox("Only use RSS feeds listed above")
        self.disable_rss_checkbox = QtWidgets.QCheckBox("Disable RSS fetching (API/search only)")
        self.api_input = QtWidgets.QLineEdit()
        self.api_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.google_cse_key_input = QtWidgets.QLineEdit()
        self.google_cse_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.google_cse_cx_input = QtWidgets.QLineEdit()
        self.google_cse_cx_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.news_window_combo = QtWidgets.QComboBox()
        self.news_window_combo.addItems(["6", "24", "72", "168"])
        self.news_sort_combo = QtWidgets.QComboBox()
        self.news_sort_combo.addItems(["popularity", "publishedAt", "relevancy"])
        self.duckduckgo_checkbox = QtWidgets.QCheckBox("Enable DuckDuckGo web search")
        self.ai_suggestions_checkbox = QtWidgets.QCheckBox("Show AI suggested actions in insight panel")
        self.ai_suggestions_checkbox.setChecked(True)
        self.polling_input = QtWidgets.QLineEdit()
        self.insight_refresh_combo = QtWidgets.QComboBox()
        self.insight_refresh_combo.addItems(["1", "5", "10", "15", "30"])
        self.insight_refresh_combo.setCurrentText("5")
        self.subject_input.setToolTip("What you want to monitor (e.g., weather alerts).")
        self.question_input.setToolTip("Optional question to guide the AI focus.")
        self.light_model_checkbox.setToolTip("Use a smaller model on low-RAM systems.")
        self.location_input.setToolTip("City/region name used for local relevance.")
        self.zip_input.setToolTip("ZIP code for local filtering and geocoding.")
        self.lat_input.setToolTip("Optional latitude for precise location filtering.")
        self.lon_input.setToolTip("Optional longitude for precise location filtering.")
        self.radius_input.setToolTip("Radius in kilometers for local matching (default 50).")
        self.relax_location_checkbox.setToolTip("Show results even if they don't mention the location.")
        self.rss_input.setToolTip("Paste RSS feed URLs, one per line.")
        self.use_only_rss_checkbox.setToolTip("Disable curated sources and only use your RSS list.")
        self.disable_rss_checkbox.setToolTip("Skip RSS sources entirely and use API/search only.")
        self.api_input.setToolTip("News API key for broader coverage (kept locally).")
        self.google_cse_key_input.setToolTip("Google CSE API key for web search.")
        self.google_cse_cx_input.setToolTip("Google CSE Search Engine ID (CX).")
        self.news_window_combo.setToolTip("News API time window in hours.")
        self.news_sort_combo.setToolTip("NewsAPI sort order.")
        self.duckduckgo_checkbox.setToolTip("Use DuckDuckGo HTML search for additional results.")
        self.ai_suggestions_checkbox.setToolTip("Show/hide actionable suggestions next to the AI insight summary.")
        self.polling_input.setToolTip("Polling interval in minutes (default 5).")
        self.insight_refresh_combo.setToolTip("How often to regenerate the AI insight (in minutes).")

        form = QtWidgets.QFormLayout()
        form.addRow("Subject", self.subject_input)
        form.addRow("Monitoring Question (optional)", self.question_input)
        form.addRow("", self.light_model_checkbox)
        form.addRow("Location", self.location_input)
        form.addRow("ZIP Code", self.zip_input)
        form.addRow("Latitude", self.lat_input)
        form.addRow("Longitude", self.lon_input)
        form.addRow("Radius (km)", self.radius_input)
        form.addRow("", self.relax_location_checkbox)
        form.addRow("RSS Feeds (one per line)", self.rss_input)
        form.addRow("", self.use_only_rss_checkbox)
        form.addRow("", self.disable_rss_checkbox)
        form.addRow("News API Key", self.api_input)
        form.addRow("Google CSE API Key", self.google_cse_key_input)
        form.addRow("Google CSE CX", self.google_cse_cx_input)
        form.addRow("News time window (hours)", self.news_window_combo)
        form.addRow("NewsAPI sort order", self.news_sort_combo)
        form.addRow("", self.duckduckgo_checkbox)
        form.addRow("", self.ai_suggestions_checkbox)
        form.addRow("Polling interval (minutes)", self.polling_input)
        form.addRow("Insight refresh (minutes)", self.insight_refresh_combo)
        api_links = QtWidgets.QLabel(
            "<a href='https://programmablesearchengine.google.com/'>Google CSE</a> | "
            "<a href='https://developers.google.com/custom-search/v1/overview'>Google JSON API</a> | "
            "<a href='https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/create-bing-search-service-resource'>Bing Search</a> | "
            "<a href='https://newsapi.org/'>NewsAPI</a>"
        )
        api_links.setOpenExternalLinks(True)
        api_links.setToolTip("Open API key signup pages in your browser.")
        form.addRow("Get API Keys", api_links)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def to_config(self) -> AppConfig:
        rss_list = [
            line.strip()
            for line in self.rss_input.toPlainText().splitlines()
            if line.strip()
        ]
        lat = float(self.lat_input.text()) if self.lat_input.text().strip() else None
        lon = float(self.lon_input.text()) if self.lon_input.text().strip() else None
        radius = int(self.radius_input.text()) if self.radius_input.text().strip() else 50
        return AppConfig(
            subject=self.subject_input.text().strip() or "Impactful Events",
            question=self.question_input.text().strip(),
            location_name=self.location_input.text().strip(),
            zip_code=self.zip_input.text().strip() or None,
            latitude=lat,
            longitude=lon,
            radius_km=radius,
            relax_location_filter=self.relax_location_checkbox.isChecked(),
            prefer_light_model=self.light_model_checkbox.isChecked(),
            rss_feeds=rss_list,
            use_only_rss_feeds=self.use_only_rss_checkbox.isChecked(),
            disable_rss_fetch=self.disable_rss_checkbox.isChecked(),
            news_api_key=self.api_input.text().strip() or None,
            news_time_window_hours=int(self.news_window_combo.currentText() or "6"),
            news_sort_by=self.news_sort_combo.currentText() or "popularity",
            google_cse_api_key=self.google_cse_key_input.text().strip() or None,
            google_cse_cx=self.google_cse_cx_input.text().strip() or None,
            enable_duckduckgo_search=self.duckduckgo_checkbox.isChecked(),
            enable_ai_suggestions=self.ai_suggestions_checkbox.isChecked(),
            polling_minutes=int(self.polling_input.text().strip() or "5"),
            insight_refresh_minutes=int(self.insight_refresh_combo.currentText() or "5"),
            display_timezone=self.display_timezone_value,
        )


class MonitorThread(QtCore.QThread):
    new_alert = QtCore.Signal(dict)
    status = QtCore.Signal(str)
    model = QtCore.Signal(str)

    def __init__(self, config: AppConfig, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._engine: MonitorEngine | None = None

    def run(self) -> None:
        async def _runner() -> None:
            self.status.emit("monitoring")
            self._engine = MonitorEngine(self.config, on_new_alert=self.new_alert.emit)
            self.model.emit(self._engine.model_name)
            await self._engine.run_forever()
            self.status.emit("stopped")

        import asyncio

        asyncio.run(_runner())

    def stop(self) -> None:
        if self._engine:
            self._engine.stop()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("VigilantCore")
        self.resize(1100, 700)
        self.config = config

        # Set window icon
        icon_path = ROOT_DIR / "assets" / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        self.monitor_thread: MonitorThread | None = None
        self.insight_thread: InsightThread | None = None

        # Insight widget (above the table)
        self.insight_widget = InsightWidget()

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Time", "Score", "Title", "Source", "Relevant", "Prediction"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setToolTip(
            "Live Impact Feed. Higher scores indicate more impactful alerts."
        )

        self.status_label = QtWidgets.QLabel("Idle")
        self.model_label = QtWidgets.QLabel("")
        self.start_button = QtWidgets.QPushButton("Start Monitoring")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.start_button.setToolTip("Begin monitoring for new alerts.")
        self.stop_button.setToolTip("Pause background monitoring.")
        self.status_label.setToolTip("Shows current monitoring status.")
        self.model_label.setToolTip("Active local model used for AI scoring.")

        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)

        # Privacy note
        self.privacy_label = QtWidgets.QLabel("🔒 Local AI - data never shared externally")
        self.privacy_label.setStyleSheet("color: #16a34a; font-size: 11px;")
        self.privacy_label.setToolTip("All processing is done locally on this computer using Ollama. No data is sent to external servers.")

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.privacy_label)
        controls.addStretch(1)
        controls.addWidget(self.status_label)
        controls.addWidget(self.model_label)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.insight_widget)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        menu = self.menuBar().addMenu("Settings")
        edit_action = menu.addAction("Edit Configuration")
        edit_action.triggered.connect(self.edit_config)

        self.refresh_feed()
        self.start_monitoring()

    def refresh_feed(self) -> None:
        self.table.setRowCount(0)
        for row in database.fetch_recent(200):
            self.add_row(
                {
                    "created_at": row["created_at"],
                    "impact_score": row["impact_score"],
                    "title": row["title"],
                    "source": row["source"],
                    "is_relevant": bool(row["is_relevant"]),
                    "predictive_outcome": row["predictive_outcome"],
                }
            )

    def add_row(self, alert: Dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        created = format_alert_timestamp(alert.get("created_at"), self.config.display_timezone)
        score = str(alert.get("impact_score", ""))
        title = alert.get("title", "")
        source = alert.get("source", "")
        relevant = "Yes" if alert.get("is_relevant") else "No"
        prediction = alert.get("predictive_outcome", "")
        items = [created, score, title, source, relevant, prediction]
        for col, value in enumerate(items):
            cell = QtWidgets.QTableWidgetItem(value)
            if col == 1 and value:
                try:
                    score_val = int(value)
                    if score_val >= 8:
                        cell.setForeground(QtGui.QColor("#c0392b"))
                    elif score_val >= 5:
                        cell.setForeground(QtGui.QColor("#d35400"))
                except ValueError:
                    pass
            self.table.setItem(row, col, cell)

    def start_monitoring(self) -> None:
        if self.monitor_thread and self.monitor_thread.isRunning():
            return
        self.monitor_thread = MonitorThread(self.config)
        self.monitor_thread.new_alert.connect(self.add_row)
        self.monitor_thread.status.connect(self.on_status)
        self.monitor_thread.model.connect(self.on_model)
        self.monitor_thread.start()

        # Start insight thread if there's a monitoring question
        if self.config.question and self.config.question.strip():
            self.insight_thread = InsightThread(self.config)
            self.insight_thread.insight_ready.connect(self.insight_widget.update_insight)
            self.insight_thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_monitoring(self) -> None:
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait(2000)
        if self.insight_thread:
            self.insight_thread.stop()
            self.insight_thread.wait(2000)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopped")

    def on_status(self, status: str) -> None:
        self.status_label.setText(status.capitalize())

    def on_model(self, model_name: str) -> None:
        self.model_label.setText(f"Model: {model_name}")

    def edit_config(self) -> None:
        dialog = FirstRunDialog(self)
        dialog.display_timezone_value = self.config.display_timezone
        dialog.subject_input.setText(self.config.subject)
        dialog.question_input.setText(self.config.question)
        dialog.light_model_checkbox.setChecked(self.config.prefer_light_model)
        dialog.location_input.setText(self.config.location_name)
        if self.config.zip_code:
            dialog.zip_input.setText(self.config.zip_code)
        if self.config.latitude is not None:
            dialog.lat_input.setText(str(self.config.latitude))
        if self.config.longitude is not None:
            dialog.lon_input.setText(str(self.config.longitude))
        dialog.radius_input.setText(str(self.config.radius_km))
        dialog.relax_location_checkbox.setChecked(self.config.relax_location_filter)
        if self.config.rss_feeds:
            dialog.rss_input.setPlainText("\n".join(self.config.rss_feeds))
        dialog.use_only_rss_checkbox.setChecked(self.config.use_only_rss_feeds)
        dialog.disable_rss_checkbox.setChecked(self.config.disable_rss_fetch)
        if self.config.news_api_key:
            dialog.api_input.setText(self.config.news_api_key)
        if self.config.news_time_window_hours:
            dialog.news_window_combo.setCurrentText(str(self.config.news_time_window_hours))
        if self.config.news_sort_by:
            dialog.news_sort_combo.setCurrentText(self.config.news_sort_by)
        if self.config.google_cse_api_key:
            dialog.google_cse_key_input.setText(self.config.google_cse_api_key)
        if self.config.google_cse_cx:
            dialog.google_cse_cx_input.setText(self.config.google_cse_cx)
        dialog.duckduckgo_checkbox.setChecked(self.config.enable_duckduckgo_search)
        dialog.ai_suggestions_checkbox.setChecked(self.config.enable_ai_suggestions)
        dialog.polling_input.setText(str(self.config.polling_minutes))
        dialog.insight_refresh_combo.setCurrentText(str(self.config.insight_refresh_minutes or 5))
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.config = dialog.to_config()
            save_config(self.config)
            self.stop_monitoring()
            self.refresh_feed()
            self.start_monitoring()


def ensure_config() -> AppConfig:
    if not config_path().exists():
        dialog = FirstRunDialog()
        current_cfg = load_config()
        dialog.display_timezone_value = current_cfg.display_timezone
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            config = dialog.to_config()
            save_config(config)
            return config
        return current_cfg
    return load_config()


def main() -> None:
    database.init_db()
    app = QtWidgets.QApplication(sys.argv)

    # Set application icon
    icon_path = ROOT_DIR / "assets" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    config = ensure_config()
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

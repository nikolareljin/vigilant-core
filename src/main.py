"""VigilantCore desktop UI."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from PySide6 import QtCore, QtGui, QtWidgets

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.monitor import MonitorEngine  # noqa: E402
from utils import database  # noqa: E402
from utils.config import AppConfig, config_path, load_config, save_config  # noqa: E402


class FirstRunDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VigilantCore Setup")
        self.setMinimumWidth(520)

        self.subject_input = QtWidgets.QLineEdit()
        self.question_input = QtWidgets.QLineEdit()
        self.light_model_checkbox = QtWidgets.QCheckBox("Prefer lighter model on 8GB or less")
        self.location_input = QtWidgets.QLineEdit()
        self.zip_input = QtWidgets.QLineEdit()
        self.lat_input = QtWidgets.QLineEdit()
        self.lon_input = QtWidgets.QLineEdit()
        self.radius_input = QtWidgets.QLineEdit()
        self.rss_input = QtWidgets.QPlainTextEdit()
        self.api_input = QtWidgets.QLineEdit()
        self.api_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.subject_input.setToolTip("What you want to monitor (e.g., weather alerts).")
        self.question_input.setToolTip("Optional question to guide the AI focus.")
        self.light_model_checkbox.setToolTip("Use a smaller model on low-RAM systems.")
        self.location_input.setToolTip("City/region name used for local relevance.")
        self.zip_input.setToolTip("ZIP code for local filtering and geocoding.")
        self.lat_input.setToolTip("Optional latitude for precise location filtering.")
        self.lon_input.setToolTip("Optional longitude for precise location filtering.")
        self.radius_input.setToolTip("Radius in kilometers for local matching (default 50).")
        self.rss_input.setToolTip("Paste RSS feed URLs, one per line.")
        self.api_input.setToolTip("News API key for broader coverage (kept locally).")

        form = QtWidgets.QFormLayout()
        form.addRow("Subject", self.subject_input)
        form.addRow("Monitoring Question (optional)", self.question_input)
        form.addRow("", self.light_model_checkbox)
        form.addRow("Location", self.location_input)
        form.addRow("ZIP Code", self.zip_input)
        form.addRow("Latitude", self.lat_input)
        form.addRow("Longitude", self.lon_input)
        form.addRow("Radius (km)", self.radius_input)
        form.addRow("RSS Feeds (one per line)", self.rss_input)
        form.addRow("News API Key", self.api_input)

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
            location_name=self.location_input.text().strip() or "Your Area",
            zip_code=self.zip_input.text().strip() or None,
            latitude=lat,
            longitude=lon,
            radius_km=radius,
            prefer_light_model=self.light_model_checkbox.isChecked(),
            rss_feeds=rss_list,
            news_api_key=self.api_input.text().strip() or None,
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
        self.monitor_thread: MonitorThread | None = None

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

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.status_label)
        controls.addWidget(self.model_label)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addLayout(controls)
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
        created = alert.get("created_at") or ""
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
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_monitoring(self) -> None:
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait(2000)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopped")

    def on_status(self, status: str) -> None:
        self.status_label.setText(status.capitalize())

    def on_model(self, model_name: str) -> None:
        self.model_label.setText(f"Model: {model_name}")

    def edit_config(self) -> None:
        dialog = FirstRunDialog(self)
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
        if self.config.rss_feeds:
            dialog.rss_input.setPlainText("\n".join(self.config.rss_feeds))
        if self.config.news_api_key:
            dialog.api_input.setText(self.config.news_api_key)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.config = dialog.to_config()
            save_config(self.config)
            self.stop_monitoring()
            self.refresh_feed()
            self.start_monitoring()


def ensure_config() -> AppConfig:
    if not config_path().exists():
        dialog = FirstRunDialog()
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            config = dialog.to_config()
            save_config(config)
            return config
        return AppConfig()
    return load_config()


def main() -> None:
    database.init_db()
    app = QtWidgets.QApplication(sys.argv)
    config = ensure_config()
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

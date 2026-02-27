"""GGUF-based local summarization helpers for alerts and risk snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

try:
    from llama_cpp import Llama  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Llama = None


@dataclass
class SummaryBundle:
    engine: str
    alert_summary: str
    risk_snapshot: str
    available: bool
    error: str | None = None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _build_alert_lines(alerts: Iterable[Any], max_items: int = 12) -> list[str]:
    lines: list[str] = []
    for idx, alert in enumerate(alerts):
        if idx >= max_items:
            break
        if isinstance(alert, dict):
            title = _safe_text(alert.get("title"))
            source = _safe_text(alert.get("source")) or "Unknown"
            score = alert.get("impact_score")
        else:
            title = _safe_text(alert["title"])
            source = _safe_text(alert["source"]) or "Unknown"
            score = alert["impact_score"]
        score_text = str(score if score is not None else "n/a")
        if title:
            lines.append(f"- [{source}] impact={score_text}: {title}")
    return lines


def _heuristic_alert_summary(subject: str, location: str, alerts: Iterable[Any]) -> str:
    lines = _build_alert_lines(alerts, max_items=4)
    if not lines:
        return f"No recent alerts found for {subject} in {location}."
    top = " ".join(line.split(": ", 1)[1] for line in lines[:2] if ": " in line)
    return f"Recent alert summary for {subject} in {location}: {top}".strip()


def _heuristic_risk_snapshot(subject: str, location: str, alerts: Iterable[Any]) -> str:
    alerts_list = list(alerts)
    if not alerts_list:
        return f"Risk snapshot for {subject} in {location}: no current alerts."
    impacts = []
    for alert in alerts_list:
        raw = alert.get("impact_score") if isinstance(alert, dict) else alert["impact_score"]
        impacts.append(int(raw or 0))
    high = sum(1 for score in impacts if score >= 7)
    medium = sum(1 for score in impacts if 4 <= score <= 6)
    low = sum(1 for score in impacts if score <= 3)
    avg = round(sum(impacts) / max(1, len(impacts)), 2)
    level = "high" if avg >= 7 or high >= max(2, len(alerts_list) // 3) else ("medium" if avg >= 4 else "low")
    return (
        f"Risk snapshot for {subject} in {location}: level={level}, "
        f"alerts={len(alerts_list)}, high={high}, medium={medium}, low={low}, avg_impact={avg}/10."
    )


def summarize_alerts_and_risk_snapshot(
    *,
    alerts: Iterable[Any],
    subject: str,
    location: str,
    question: str,
    enabled: bool,
    model_path: str | None,
    n_ctx: int = 2048,
    max_tokens: int = 220,
) -> SummaryBundle:
    alerts_list = list(alerts)
    heuristic_alert = _heuristic_alert_summary(subject, location, alerts_list)
    heuristic_risk = _heuristic_risk_snapshot(subject, location, alerts_list)

    if not enabled:
        return SummaryBundle(
            engine="disabled",
            alert_summary=heuristic_alert,
            risk_snapshot=heuristic_risk,
            available=False,
        )
    if not model_path:
        return SummaryBundle(
            engine="heuristic",
            alert_summary=heuristic_alert,
            risk_snapshot=heuristic_risk,
            available=False,
            error="GGUF summarizer enabled but GGUF_MODEL_PATH is not set.",
        )
    if Llama is None:
        return SummaryBundle(
            engine="heuristic",
            alert_summary=heuristic_alert,
            risk_snapshot=heuristic_risk,
            available=False,
            error="llama-cpp-python is not installed.",
        )

    try:
        model = Llama(model_path=model_path, n_ctx=max(512, int(n_ctx)))
        alert_prompt = "\n".join(_build_alert_lines(alerts_list, max_items=12))
        summary_prompt = (
            "Summarize these alerts in 2 concise sentences.\n"
            f"Subject: {subject}\nLocation: {location}\nQuestion: {question or 'N/A'}\n"
            f"Alerts:\n{alert_prompt or '- none'}"
        )
        risk_prompt = (
            "Create a concise risk snapshot with overall risk level (low/medium/high), "
            "key drivers, and near-term outlook in 2-3 sentences.\n"
            f"Subject: {subject}\nLocation: {location}\n"
            f"Alerts:\n{alert_prompt or '- none'}"
        )
        summary_out = model.create_completion(
            prompt=summary_prompt,
            max_tokens=max(48, int(max_tokens)),
            temperature=0.2,
        )
        risk_out = model.create_completion(
            prompt=risk_prompt,
            max_tokens=max(64, int(max_tokens)),
            temperature=0.2,
        )
        summary_text = _safe_text(summary_out["choices"][0]["text"]) or heuristic_alert
        risk_text = _safe_text(risk_out["choices"][0]["text"]) or heuristic_risk
        return SummaryBundle(
            engine="gguf",
            alert_summary=summary_text,
            risk_snapshot=risk_text,
            available=True,
        )
    except Exception as exc:  # pragma: no cover - runtime/environment dependent
        return SummaryBundle(
            engine="heuristic",
            alert_summary=heuristic_alert,
            risk_snapshot=heuristic_risk,
            available=False,
            error=str(exc),
        )

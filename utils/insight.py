"""Shared helpers for AI insight payload normalization."""

from __future__ import annotations

from typing import Any


def normalize_suggestions(value: list[Any] | str | None) -> list[str]:
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


def normalize_suggestions_origin(value: str | None, suggestions: list[str]) -> str:
    if not suggestions:
        return "none"
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "official": "official_paraphrase",
            "official_only": "official_paraphrase",
            "paraphrase": "official_paraphrase",
            "ai": "ai_assisted",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in {"official_paraphrase", "ai_assisted", "mixed"}:
            return normalized
    # Conservative fallback: if suggestions exist but origin is missing/invalid, treat as AI-assisted.
    return "ai_assisted"

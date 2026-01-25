"""AI parsing utilities for VigilantCore."""

from __future__ import annotations

import asyncio
import logging
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dotenv import load_dotenv

try:
    from ollama import Client as OllamaClient
except Exception:  # pragma: no cover - optional dependency import guard
    OllamaClient = None

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_TEMPLATE = (
    "You are a selective intelligence agent. Only flag events that directly impact "
    "{subject} in {location}. If an event is a 'Watch' or 'Warning,' provide a 1-sentence "
    "prediction of what happens next. "
    "If a monitoring question is provided, use it to judge relevance and prediction focus: "
    "{question}"
)


@dataclass
class ParsedImpact:
    impact_score: int
    predictive_outcome: str
    is_relevant: bool
    summary: str


class ImpactParser:
    """Parse headlines/snippets with a local LLM to derive impact context."""

    def __init__(
        self,
        subject: str,
        location: str,
        question: str = "",
        prefer_light_model: bool = True,
        model: Optional[str] = None,
        ollama_host: Optional[str] = None,
    ) -> None:
        load_dotenv()
        self.subject = subject
        self.location = location
        self.question = question
        self.prefer_light_model = prefer_light_model
        self.model = model or "qwen2.5:7b"
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST")
        self._client = None
        if OllamaClient is not None:
            self._client = (
                OllamaClient(host=self.ollama_host)
                if self.ollama_host
                else OllamaClient()
            )
        self._maybe_downgrade_model_for_ram()
        self._ensure_model_available()

    def _ensure_model_available(self) -> None:
        if self._client is None:
            return
        try:
            models = self._client.list().get("models", [])
            logger.info("Ollama models available: %d", len(models))
        except Exception:
            logger.exception("Failed to list Ollama models; disabling LLM parsing")
            self._client = None
            return
        available = {model.get("name") for model in models if model.get("name")}
        if self.model in available:
            return
        try:
            logger.warning("Ollama model %r not found; pulling it now", self.model)
            self._client.pull(self.model)
        except Exception:
            logger.exception("Failed to pull Ollama model %r", self.model)
            if available:
                fallback = next(iter(available))
                logger.warning("Falling back to available model %r", fallback)
                self.model = fallback
            else:
                logger.warning("No Ollama models available; disabling LLM parsing")
                self._client = None

    def _maybe_downgrade_model_for_ram(self) -> None:
        if os.getenv("OLLAMA_MODEL"):
            return
        if not self.prefer_light_model:
            return
        total_gb = self._get_total_ram_gb()
        if total_gb is not None and total_gb <= 8:
            self.model = "qwen2.5:3b"

    def _get_total_ram_gb(self) -> Optional[float]:
        try:
            import psutil
        except Exception:
            return None
        try:
            total = psutil.virtual_memory().total
        except Exception:
            return None
        return total / (1024 ** 3)

    def build_system_prompt(self) -> str:
        question = self.question.strip() or "None."
        return SYSTEM_PROMPT_TEMPLATE.format(
            subject=self.subject, location=self.location, question=question
        )

    def _fallback_parse(self, headline: str, snippet: str) -> ParsedImpact:
        text = f"{headline} {snippet}".lower()
        is_watch = "watch" in text
        is_warning = "warning" in text
        is_relevant = any(keyword in text for keyword in self.subject.lower().split())
        score = 6 if (is_watch or is_warning) else 3
        if not is_relevant:
            score = 1
        prediction = ""
        if is_watch or is_warning:
            prediction = "Conditions may deteriorate; expect updates from local agencies."
        summary = snippet[:220] if snippet else headline
        return ParsedImpact(
            impact_score=score,
            predictive_outcome=prediction,
            is_relevant=is_relevant,
            summary=summary,
        )

    def parse(self, headline: str, snippet: str) -> ParsedImpact:
        if self._client is None:
            return self._fallback_parse(headline, snippet)
        system_prompt = self.build_system_prompt()
        user_prompt = (
            "Analyze this headline and snippet for impact relevance. "
            "Return JSON with keys: impact_score (1-10 int), predictive_outcome (string), "
            "is_relevant (bool), summary (string).\n"
            f"Headline: {headline}\nSnippet: {snippet}"
        )
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception:
            logger.exception("LLM parse failed; falling back to heuristic parser")
            self._client = None
            return self._fallback_parse(headline, snippet)
        content = response.get("message", {}).get("content", "{}").strip()
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return self._fallback_parse(headline, snippet)
        return ParsedImpact(
            impact_score=int(payload.get("impact_score", 1)),
            predictive_outcome=str(payload.get("predictive_outcome", "")),
            is_relevant=bool(payload.get("is_relevant", False)),
            summary=str(payload.get("summary", "")),
        )

    def current_model(self) -> str:
        return self.model

    async def parse_async(self, headline: str, snippet: str) -> ParsedImpact:
        if self._client is not None:
            return await asyncio.to_thread(self.parse, headline, snippet)
        return self._fallback_parse(headline, snippet)


def build_parser_from_config(config: Dict[str, Any]) -> ImpactParser:
    subject = config.get("subject", "Impactful Events")
    location = config.get("location", "Unknown")
    model = config.get("model")
    ollama_host = config.get("ollama_host")
    return ImpactParser(subject, location, model=model, ollama_host=ollama_host)

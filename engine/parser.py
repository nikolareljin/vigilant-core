"""AI parsing utilities for VigilantCore."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from dotenv import load_dotenv

try:
    from ollama import Client as OllamaClient
except Exception:  # pragma: no cover - optional dependency import guard
    OllamaClient = None


SYSTEM_PROMPT_TEMPLATE = (
    "You are a selective intelligence agent. Only flag events that directly impact "
    "{subject} in {location}. If an event is a 'Watch' or 'Warning,' provide a 1-sentence "
    "prediction of what happens next."
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
        model: Optional[str] = None,
        ollama_host: Optional[str] = None,
    ) -> None:
        load_dotenv()
        self.subject = subject
        self.location = location
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST")
        self._client = None
        if OllamaClient is not None:
            self._client = (
                OllamaClient(host=self.ollama_host)
                if self.ollama_host
                else OllamaClient()
            )

    def build_system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(subject=self.subject, location=self.location)

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
        response = self._client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
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

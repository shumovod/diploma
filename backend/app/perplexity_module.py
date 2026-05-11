import logging
import time
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from app.config import Settings
from app.logutil import preview_text

logger = logging.getLogger(__name__)


class PerplexitySearchHit(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class PerplexitySonarResult(BaseModel):
    content: str = ""
    citations: list[str] = Field(default_factory=list)
    search_results: list[PerplexitySearchHit] = Field(default_factory=list)


def _favicon_for_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc or url
    if host.startswith("www."):
        host = host[4:]
    return f"https://www.google.com/s2/favicons?domain={host}&sz=64"


class PerplexitySonarClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = "https://api.perplexity.ai/v1/sonar"

    async def chat(
        self,
        user_message: str,
        system_prompt: str | None = None,
    ) -> PerplexitySonarResult:
        t0 = time.perf_counter()
        logger.info(
            "perplexity.chat: HTTP старт model=%s timeout_s=%s preview=%s",
            self._settings.perplexity_sonar_model,
            self._settings.perplexity_timeout_seconds,
            preview_text(user_message),
        )
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        payload: dict = {
            "model": self._settings.perplexity_sonar_model,
            "messages": messages,
            "search_language_filter": ["ru"],
            "web_search_options": {
                "search_context_size": self._settings.perplexity_search_context_size,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._settings.perplexity_api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self._settings.perplexity_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(self._url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = ""
        choices = data.get("choices") or []
        if choices:
            msg = (choices[0] or {}).get("message") or {}
            content = msg.get("content") or ""
            if isinstance(content, list):
                parts = []
                for chunk in content:
                    if isinstance(chunk, dict) and chunk.get("type") == "text":
                        parts.append(chunk.get("text") or "")
                content = "".join(parts)
        citations_raw = data.get("citations") or []
        citations = [str(c) for c in citations_raw if c]
        raw_results = data.get("search_results") or []
        hits: list[PerplexitySearchHit] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            hits.append(
                PerplexitySearchHit(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("snippet") or ""),
                )
            )
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "perplexity.chat: готово за %.0f мс len_content=%d citations=%d search_hits=%d",
            ms,
            len(content),
            len(citations),
            len(hits),
        )
        return PerplexitySonarResult(content=content, citations=citations, search_results=hits)

    def sources_for_ui(self, result: PerplexitySonarResult) -> list[dict[str, str]]:
        by_url: dict[str, PerplexitySearchHit] = {h.url: h for h in result.search_results if h.url}
        ordered_urls: list[str] = []
        for h in result.search_results:
            if h.url and h.url not in ordered_urls:
                ordered_urls.append(h.url)
        for u in result.citations:
            if u and u not in ordered_urls:
                ordered_urls.append(u)
        out: list[dict[str, str]] = []
        for u in ordered_urls:
            hit = by_url.get(u)
            title = hit.title if hit and hit.title else u
            out.append({"title": title, "url": u, "favicon_url": _favicon_for_url(u)})
        return out

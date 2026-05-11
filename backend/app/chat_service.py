import logging
import time

from fastapi import HTTPException

from app.config import Settings
from app.moderation import moderate_and_decompose
from app.perplexity_module import PerplexitySonarClient
from app.query_rewrite import rewrite_all_subquestions_for_rag
from app.rag import RAGService
from app.rag_aggregate import answer_from_rag_or_insufficient
from app.logutil import preview_text
from app.schemas import ChatResponse, SourceItem

logger = logging.getLogger(__name__)


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        k = q.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(q.strip())
    return out


async def process_chat(
    settings: Settings,
    rag: RAGService,
    perplexity: PerplexitySonarClient,
    message: str,
) -> ChatResponse:
    if not settings.openai_api_key.strip():
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY не задан")
    t_chat = time.perf_counter()
    logger.info(
        "chat: начало обработки preview=%s",
        preview_text(message),
    )
    allowed, sub_questions = await moderate_and_decompose(settings, message)
    if not allowed:
        logger.info(
            "chat: блокировка за %.0f мс",
            (time.perf_counter() - t_chat) * 1000,
        )
        return ChatResponse(
            text="Сообщение не прошло модерацию: обнаружена недопустимая лексика или содержание.",
            sources=[],
            source_type="blocked",
        )
    t_rw = time.perf_counter()
    rewritten = await rewrite_all_subquestions_for_rag(settings, message, sub_questions)
    rw_ms = (time.perf_counter() - t_rw) * 1000
    all_queries = _dedupe_queries(rewritten)
    logger.info(
        "chat: после дедупа запросов_в_RAG=%d (до дедупа %d) rewrite_этап_%.0f_мс",
        len(all_queries),
        len(rewritten),
        rw_ms,
    )
    t_rag = time.perf_counter()
    docs = await rag.retrieve(all_queries)
    rag_ms = (time.perf_counter() - t_rag) * 1000
    logger.info("chat: retrieve этап %.0f мс документов=%d", rag_ms, len(docs))
    t_agg = time.perf_counter()
    sufficient, rag_text = await answer_from_rag_or_insufficient(
        settings,
        message,
        sub_questions,
        docs,
    )
    agg_ms = (time.perf_counter() - t_agg) * 1000
    logger.info(
        "chat: sufficiency этап %.0f мс sufficient=%s",
        agg_ms,
        sufficient,
    )
    if sufficient:
        logger.info(
            "chat: ответ RAG полный цикл %.0f мс",
            (time.perf_counter() - t_chat) * 1000,
        )
        return ChatResponse(text=rag_text, sources=[], source_type="rag")
    if not settings.perplexity_api_key.strip():
        raise HTTPException(status_code=503, detail="PERPLEXITY_API_KEY не задан для веб-поиска")
    system_prompt = (
        "Ты помощник абитуриентов по поступлению в российские вузы. "
        "Отвечай по-русски, опирайся на найденные источники, не выдумывай конкретные цифры и даты без опоры на поиск."
    )
    t_px = time.perf_counter()
    sonar = await perplexity.chat(message, system_prompt=system_prompt)
    px_ms = (time.perf_counter() - t_px) * 1000
    logger.info("chat: Perplexity этап %.0f мс", px_ms)
    raw_sources = perplexity.sources_for_ui(sonar)
    sources = [
        SourceItem(
            title=s["title"],
            url=s["url"],
            favicon_url=s.get("favicon_url") or "",
        )
        for s in raw_sources
    ]
    urls = [s.url for s in sources if s.url]
    try:
        await rag.ingest_perplexity_turn(message, sonar.content, urls)
    except Exception:
        logger.exception("ingest_perplexity_turn")
    logger.info(
        "chat: ответ Perplexity полный цикл %.0f мс источников=%d",
        (time.perf_counter() - t_chat) * 1000,
        len(sources),
    )
    return ChatResponse(
        text=sonar.content.strip(),
        sources=sources,
        source_type="perplexity",
    )

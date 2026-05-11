import logging
import time

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.llm_factory import chat_llm
from app.logutil import preview_text

logger = logging.getLogger(__name__)

MAX_RAG_SEARCH_QUERIES = 3


def _cap_rag_queries(queries: list[str], limit: int = MAX_RAG_SEARCH_QUERIES) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        t = q.strip()
        if not t:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out


class RewrittenQueries(BaseModel):
    queries: list[str] = Field(
        description="От 1 до 3 коротких поисковых запросов для векторной БД (синонимы, другая формулировка); не больше трёх строк, без дубликатов"
    )


class BatchRewrittenQueries(BaseModel):
    queries: list[str] = Field(
        description="Две или три короткие строки для семантического поиска по всем подвопросам сразу, без дубликатов, не больше трёх"
    )


async def rewrite_all_subquestions_for_rag(
    settings: Settings,
    original_message: str,
    sub_questions: list[str],
) -> list[str]:
    t_all = time.perf_counter()
    if not sub_questions:
        logger.info(
            "query_rewrite: нет подвопросов, один запрос из сообщения preview=%s",
            preview_text(original_message),
        )
        return [original_message.strip()]
    if len(sub_questions) == 1:
        logger.info(
            "query_rewrite: один подвопрос, режим single preview=%s",
            preview_text(sub_questions[0]),
        )
        return await rewrite_for_rag(settings, sub_questions[0])
    subs_line = " | ".join(preview_text(s, 80) for s in sub_questions[:6])
    if len(sub_questions) > 6:
        subs_line += f" …(+{len(sub_questions) - 6})"
    logger.info(
        "query_rewrite: батч LLM старт подвопросов=%d: %s",
        len(sub_questions),
        subs_line,
    )
    t_batch = time.perf_counter()
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sub_questions))
    llm = chat_llm(settings).with_structured_output(BatchRewrittenQueries)
    sys = SystemMessage(
        content=(
            "По исходному сообщению и списку подвопросов абитуриента сформулируй для векторной БД о поступлении в ВУЗ ровно от двух до трёх коротких поисковых строк, "
            "которые вместе покрывают смысл всех перечисленных подвопросов. Без дубликатов и без расползания на длинный список: максимум три строки. "
            "Только русский язык, без ненормативной лексики."
        )
    )
    human = HumanMessage(
        content=f"Исходное сообщение:\n{original_message}\n\nПодвопросы:\n{numbered}"
    )
    out = await llm.ainvoke([sys, human])
    batch_ms = (time.perf_counter() - t_batch) * 1000
    if out is None or not out.queries:
        logger.warning(
            "query_rewrite: батч пустой за %.0f мс, откат по исходному сообщению",
            batch_ms,
        )
        fb = _cap_rag_queries(await rewrite_for_rag(settings, original_message.strip()))
        total_ms = (time.perf_counter() - t_all) * 1000
        logger.info(
            "query_rewrite: итого после отката %.0f мс запросов_для_RAG=%d",
            total_ms,
            len(fb),
        )
        return fb
    cleaned = _cap_rag_queries([q.strip() for q in out.queries if q and q.strip()])
    if not cleaned:
        logger.warning(
            "query_rewrite: батч без строк за %.0f мс, откат по исходному сообщению",
            batch_ms,
        )
        fb = _cap_rag_queries(await rewrite_for_rag(settings, original_message.strip()))
        total_ms = (time.perf_counter() - t_all) * 1000
        logger.info(
            "query_rewrite: итого после отката %.0f мс запросов_для_RAG=%d",
            total_ms,
            len(fb),
        )
        return fb
    q_preview = " | ".join(preview_text(q, 60) for q in cleaned)
    total_ms = (time.perf_counter() - t_all) * 1000
    logger.info(
        "query_rewrite: батч готов за %.0f мс (LLM %.0f мс) строк=%d: %s",
        total_ms,
        batch_ms,
        len(cleaned),
        q_preview,
    )
    return cleaned


async def rewrite_for_rag(settings: Settings, user_message: str) -> list[str]:
    t0 = time.perf_counter()
    logger.info(
        "query_rewrite: single LLM старт preview=%s",
        preview_text(user_message),
    )
    llm = chat_llm(settings).with_structured_output(RewrittenQueries)
    sys = SystemMessage(
        content=(
            "Переформулируй вопрос абитуриента для семантического поиска по базе знаний о поступлении в ВУЗ. "
            "Верни от одного до трёх коротких вариантов запроса: синонимы или другая формулировка той же темы. "
            "Не больше трёх строк, без дубликатов. Запросы на русском, без ненормативной лексики."
        )
    )
    human = HumanMessage(content=user_message)
    out = await llm.ainvoke([sys, human])
    ms = (time.perf_counter() - t0) * 1000
    if out is None or not out.queries:
        logger.warning(
            "query_rewrite: single пустой за %.0f мс, fallback одна строка",
            ms,
        )
        return [user_message.strip()]
    cleaned = _cap_rag_queries([q.strip() for q in out.queries if q and q.strip()])
    if not cleaned:
        logger.warning(
            "query_rewrite: single без строк за %.0f мс, fallback одна строка",
            ms,
        )
        return [user_message.strip()]
    qp = " | ".join(preview_text(q, 50) for q in cleaned)
    logger.info(
        "query_rewrite: single готов за %.0f мс вариантов=%d: %s",
        ms,
        len(cleaned),
        qp,
    )
    return cleaned

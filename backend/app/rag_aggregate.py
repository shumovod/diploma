import logging
import time

from pydantic import BaseModel, Field

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.llm_factory import chat_llm
from app.logutil import preview_text

logger = logging.getLogger(__name__)


class RAGCoverageAnswer(BaseModel):
    sufficient: bool = Field(
        description="True только если по контексту можно полностью ответить на исходный составной вопрос со всеми частями"
    )
    answer_ru: str = Field(
        default="",
        description="Полный ответ на русском, если sufficient=true; иначе пустая строка",
    )


async def answer_from_rag_or_insufficient(
    settings: Settings,
    original_question: str,
    sub_questions: list[str],
    docs: list[Document],
) -> tuple[bool, str]:
    t0 = time.perf_counter()
    if not docs:
        logger.info("rag_aggregate: нет документов, sufficient=false")
        return False, ""
    ctx = "\n\n---\n\n".join(d.page_content for d in docs if d.page_content)
    if len(ctx.strip()) < settings.rag_min_docs_chars:
        logger.info(
            "rag_aggregate: контекст короче порога за %.0f мс chars=%d min=%d",
            (time.perf_counter() - t0) * 1000,
            len(ctx.strip()),
            settings.rag_min_docs_chars,
        )
        return False, ""
    subs = "\n".join(f"- {s}" for s in sub_questions)
    llm = chat_llm(settings).with_structured_output(RAGCoverageAnswer)
    sys = SystemMessage(
        content=(
            "Ты консультант по поступлению в вузы РФ. Даны исходный вопрос абитуриента (возможно составной), "
            "список выделенных подвопросов и фрагменты из базы знаний. "
            "Оцени, хватает ли контекста, чтобы ответить на ВСЕ части исходного вопроса без додумывания и без пробелов. "
            "Если по контексту закрывается только часть подвопросов — sufficient=false. "
            "При sufficient=true напиши связный ответ answer_ru на весь исходный вопрос по-русски, со структурой и заголовками при необходимости, только из фактов контекста."
        )
    )
    human = HumanMessage(
        content=(
            f"Исходный вопрос:\n{original_question}\n\n"
            f"Подвопросы:\n{subs}\n\n"
            f"Фрагменты базы:\n{ctx[:14000]}"
        )
    )
    logger.info(
        "rag_aggregate: LLM sufficiency старт docs=%d ctx_chars=%d вопрос=%s",
        len(docs),
        len(ctx),
        preview_text(original_question),
    )
    t_llm = time.perf_counter()
    out = await llm.ainvoke([sys, human])
    llm_ms = (time.perf_counter() - t_llm) * 1000
    total_ms = (time.perf_counter() - t0) * 1000
    if out is None or not out.sufficient:
        logger.info(
            "rag_aggregate: insufficient за %.0f мс (LLM %.0f мс) out=%s",
            total_ms,
            llm_ms,
            "none" if out is None else f"sufficient={out.sufficient}",
        )
        return False, ""
    text = (out.answer_ru or "").strip()
    if not text:
        logger.info(
            "rag_aggregate: sufficient=true но пустой ответ за %.0f мс (LLM %.0f мс)",
            total_ms,
            llm_ms,
        )
        return False, ""
    logger.info(
        "rag_aggregate: ответ из RAG за %.0f мс (LLM %.0f мс) длина_ответа=%d preview=%s",
        total_ms,
        llm_ms,
        len(text),
        preview_text(text, 120),
    )
    return True, text

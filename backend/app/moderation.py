import logging
import time

from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.llm_factory import chat_llm
from app.logutil import preview_text

logger = logging.getLogger(__name__)


class ModerationVerdict(BaseModel):
    allowed: bool = Field(description="True только если сообщение допустимо для помощи по поступлению в ВУЗ")


class ModerationDecompose(BaseModel):
    allowed: bool = Field(
        description="True только если сообщение допустимо; иначе False и пустой sub_questions"
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        description="Если allowed=true: по одной строке на каждую явно отдельную тему вопроса. Если allowed=false: пустой список",
    )


def _is_obvious_flood_or_empty(message: str) -> bool:
    s = message.strip()
    if len(s) < 3:
        return True
    if len(s) > 12000:
        return True
    compact = "".join(s.split())
    if len(compact) >= 40 and len(set(compact)) <= 2:
        return True
    words = [w for w in s.split() if w]
    if len(words) >= 8 and len(set(words)) == 1:
        return True
    return False


async def moderate_and_decompose(settings: Settings, message: str) -> tuple[bool, list[str]]:
    t0 = time.perf_counter()
    if _is_obvious_flood_or_empty(message):
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "moderation_decompose: отказ по правилам флуда/пусто за %.0f мс preview=%s",
            ms,
            preview_text(message),
        )
        return False, []
    logger.info(
        "moderation_decompose: LLM старт len=%d preview=%s",
        len(message),
        preview_text(message),
    )
    llm = chat_llm(settings).with_structured_output(ModerationDecompose)
    sys = SystemMessage(
        content=(
            "Ты модератор и разборщик запросов абитуриента в одном шаге. "
            "Сначала реши allowed по правилам: разрешай только осмысленные вопросы по поступлению, вузам, ЕГЭ, программам, документам, срокам. "
            "allowed=false для ненормативной лексики, розни, экстремизма, нарушений закона, пропаганды насилия, военной пропаганды и призывов к насилию, "
            "аморального вне темы поступления, флуда и спама без вопроса по делу, сообщений не по теме без реального вопроса. "
            "Если allowed=false — верни пустой sub_questions. "
            "Если allowed=true — sub_questions только для явно разных вопросов в одном сообщении: отдельные темы, отдельные предложения с разными запросами "
            "(пример: «как поступить в МГУ? есть ли военная кафедра?» — две строки; «как поступить в МГУ что насчёт общаги и военной кафедры» — три строки). "
            "Один цельный вопрос без явного второго запроса — ровно одна строка, дословно или слегка уточнённо, без разбиения на документы, ЕГЭ, сроки и т.п. "
            "(пример: «как поступить в МГУ?» — одна строка, не пять). Не дроби один смысл на список. Без ненормативной лексики в sub_questions."
        )
    )
    human = HumanMessage(content=message)
    out = await llm.ainvoke([sys, human])
    ms = (time.perf_counter() - t0) * 1000
    if out is None:
        logger.warning("moderation_decompose: ответ LLM пустой за %.0f мс", ms)
        return False, []
    if not out.allowed:
        logger.info("moderation_decompose: запрещено за %.0f мс", ms)
        return False, []
    cleaned = [s.strip() for s in out.sub_questions if s and s.strip()]
    if not cleaned:
        logger.info(
            "moderation_decompose: подвопросов нет, один блок за %.0f мс preview=%s",
            ms,
            preview_text(message),
        )
        return True, [message.strip()]
    subs_preview = " | ".join(preview_text(s, 100) for s in cleaned[:8])
    if len(cleaned) > 8:
        subs_preview += f" …(+{len(cleaned) - 8})"
    logger.info(
        "moderation_decompose: разрешено за %.0f мс подвопросов=%d: %s",
        ms,
        len(cleaned),
        subs_preview,
    )
    return True, cleaned


async def moderate_user_message(settings: Settings, message: str) -> bool:
    if _is_obvious_flood_or_empty(message):
        return False
    llm = chat_llm(settings).with_structured_output(ModerationVerdict)
    sys = SystemMessage(
        content=(
            "Ты модератор чата помощи абитуриентам. Разрешай только осмысленные вопросы по теме поступления, вузов, ЕГЭ, программ, документов, сроков. "
            "allowed=false для: ненормативной лексики и оскорблений; межнациональной, религиозной или иной вражды и розни; "
            "пропаганды насилия, экстремизма, оправдания преступлений и нарушений закона; инструкций к противоправным действиям; "
            "материалов, разжигающих ненависть по признаку национальности, расы, религии; "
            "военной тематики в форме пропаганды, оправдания агрессии, призывов к насилию (нейтральные школьные вопросы по истории без ненависти и призывов — allowed=true); "
            "сексуального контента с несовершеннолетними; заведомо аморального контента вне учебной темы; "
            "флуда: повтор одних и тех же слов/символов без вопроса, бессмысленный набор символов, спам без запроса по делу. "
            "Если сообщение не по теме поступления и не содержит реального вопроса по делу — allowed=false. "
            "Иначе allowed=true."
        )
    )
    human = HumanMessage(content=message)
    verdict = await llm.ainvoke([sys, human])
    if verdict is None:
        return False
    return bool(verdict.allowed)

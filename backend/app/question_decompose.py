from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.llm_factory import chat_llm


class DecomposedQuestions(BaseModel):
    sub_questions: list[str] = Field(
        description="Список атомарных подвопросов на русском, по одному на каждую отдельную тему из исходного запроса"
    )


async def decompose_user_question(settings: Settings, user_message: str) -> list[str]:
    llm = chat_llm(settings).with_structured_output(DecomposedQuestions)
    sys = SystemMessage(
        content=(
            "Ты разбираешь запросы абитуриентов. Если в одном сообщении несколько разных вопросов, "
            "раздели их на отдельные короткие подвопросы (каждый — одна тема). "
            "Если вопрос один и неделимый, верни ровно один элемент — исходную формулировку или её уточнение. "
            "Не объединяй разные темы в один пункт. Количество пунктов не ограничено сверху — столько, сколько реально отдельных вопросов. "
            "Без ненормативной лексики."
        )
    )
    human = HumanMessage(content=user_message)
    out = await llm.ainvoke([sys, human])
    if out is None or not out.sub_questions:
        return [user_message.strip()]
    cleaned = [s.strip() for s in out.sub_questions if s and s.strip()]
    if not cleaned:
        return [user_message.strip()]
    return cleaned

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import Settings


def chat_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=0.2,
        timeout=120.0,
    )


def embeddings_model(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_embedding_model,
        timeout=120.0,
    )

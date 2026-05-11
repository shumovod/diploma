import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d | %(levelname)-5s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
from fastapi.middleware.cors import CORSMiddleware

from app.chat_service import process_chat
from app.config import get_settings
from app.perplexity_module import PerplexitySonarClient
from app.rag import RAGService
from app.schemas import ChatRequest, ChatResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.rag = RAGService(settings)
    app.state.perplexity = PerplexitySonarClient(settings)
    yield


app = FastAPI(title="Student Helper API", lifespan=lifespan)
settings = get_settings()
_origins = {
    settings.frontend_origin,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost",
    "http://127.0.0.1",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "student-helper-api",
        "health": "/api/health",
        "docs": "/docs",
        "ui_docker_compose": "http://localhost:8080",
        "note": "Порт 8000 — только API. Интерфейс в Docker открывайте на порту 8080 (nginx).",
    }


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest, request: Request) -> ChatResponse:
    s = request.app.state.settings
    rag: RAGService = request.app.state.rag
    perplexity: PerplexitySonarClient = request.app.state.perplexity
    return await process_chat(s, rag, perplexity, payload.message.strip())

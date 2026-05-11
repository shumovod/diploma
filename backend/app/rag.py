import asyncio
import logging
import time

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings
from app.llm_factory import embeddings_model
from app.logutil import preview_text

logger = logging.getLogger(__name__)


def _split_text_for_embedding(body: str, max_chars: int, overlap: int) -> list[str]:
    ov = min(overlap, max(0, max_chars // 5))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=ov,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    parts = splitter.split_text(body)
    out: list[str] = []
    step = max(1, max_chars - ov)
    for p in parts:
        s = p.strip()
        if not s:
            continue
        if len(s) <= max_chars:
            out.append(s)
            continue
        for i in range(0, len(s), step):
            chunk = s[i : i + max_chars].strip()
            if chunk:
                out.append(chunk)
    return out


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embeddings: Embeddings = embeddings_model(settings)
        self._vectorstore = Chroma(
            collection_name=settings.chroma_collection_name,
            embedding_function=self._embeddings,
            persist_directory=settings.chroma_persist_directory,
        )

    async def retrieve(self, queries: list[str]) -> list[Document]:
        t0 = time.perf_counter()
        k = self._settings.rag_retrieve_k
        lines = []
        for i, q in enumerate(queries[:12]):
            lines.append(f"[{i + 1}] {preview_text(q, 90)}")
        if len(queries) > 12:
            lines.append(f"… ещё запросов: {len(queries) - 12}")
        logger.info(
            "rag.retrieve: старт запросов=%d k=%d\n%s",
            len(queries),
            k,
            "\n".join(lines),
        )

        def _run() -> list[Document]:
            seen: set[str] = set()
            acc: list[Document] = []
            for q in queries:
                batch = self._vectorstore.similarity_search_with_score(
                    q,
                    k=k,
                )
                for doc, _score in batch:
                    key = doc.page_content[:400] if doc.page_content else ""
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    acc.append(doc)
            return acc

        docs = await asyncio.to_thread(_run)
        ms = (time.perf_counter() - t0) * 1000
        total_chars = sum(len(d.page_content or "") for d in docs)
        previews = [preview_text(d.page_content or "", 70) for d in docs[:5]]
        tail = f" …(+{len(docs) - 5})" if len(docs) > 5 else ""
        logger.info(
            "rag.retrieve: готово за %.0f мс документов=%d суммарно_символов=%d фрагменты: %s%s",
            ms,
            len(docs),
            total_chars,
            " | ".join(previews),
            tail,
        )
        return docs

    async def ingest_perplexity_turn(
        self,
        question: str,
        answer_text: str,
        source_urls: list[str],
    ) -> None:
        t0 = time.perf_counter()
        urls_line = "\n".join(source_urls[:20])
        body = f"Вопрос:\n{question}\n\nОтвет:\n{answer_text}\n\nИсточники:\n{urls_line}"
        meta = {"origin": "perplexity", "question": question[:500]}
        max_c = self._settings.rag_ingest_max_chars
        overlap = self._settings.rag_ingest_chunk_overlap

        def _add() -> int:
            parts = _split_text_for_embedding(body, max_c, overlap)
            for i, p in enumerate(parts):
                doc = Document(page_content=p, metadata={**meta, "part": i})
                self._vectorstore.add_documents([doc])
            return len(parts)

        n_parts = await asyncio.to_thread(_add)
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "rag.ingest_perplexity_turn: готово за %.0f мс частей=%d urls=%d",
            ms,
            n_parts,
            len(source_urls),
        )

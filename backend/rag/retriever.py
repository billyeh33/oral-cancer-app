"""Find the passages most relevant to a question.

Where the vectors live:
- QDRANT_URL set   -> Qdrant Cloud (or any Qdrant server), filled by build_index.py
- QDRANT_URL unset -> an in-memory Qdrant loaded from rag/data/ at startup
If the cloud cluster cannot be reached, the in-memory copy is used instead, so the
website keeps working (e.g. when a free cluster has been suspended).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Sequence

from qdrant_client import models

from . import config, store
from .embeddings import embed_query

LOGGER = logging.getLogger("oral_lesion_screening.rag")


@dataclass
class Passage:
    chunk_id: str
    source_title: str
    publisher: str
    file: str
    page: int
    chapter: str
    section: str
    title: str
    text: str
    score: float

    @property
    def citation(self) -> str:
        label = f"《{self.source_title}》第 {self.page} 頁"
        return f"{label}・{self.title}" if self.title else label

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "citation": self.citation}


def passage_from_payload(payload: Dict[str, Any], score: float = 0.0) -> Passage:
    """Build a Passage from a Qdrant payload or a chunks.jsonl row."""
    return Passage(
        chunk_id=payload["chunk_id"],
        source_title=payload["source_title"],
        publisher=payload["publisher"],
        file=payload["file"],
        page=payload["page"],
        chapter=payload.get("chapter", ""),
        section=payload.get("section", ""),
        title=payload.get("title", ""),
        text=payload["text"],
        score=round(score, 4),
    )


def _build_filter(
    source_ids: Optional[Sequence[str]], chapters: Optional[Sequence[str]]
) -> Optional[models.Filter]:
    conditions = []
    if source_ids:
        conditions.append(
            models.FieldCondition(key="source_id", match=models.MatchAny(any=list(source_ids)))
        )
    if chapters:
        conditions.append(
            models.FieldCondition(key="chapter", match=models.MatchAny(any=list(chapters)))
        )
    return models.Filter(should=conditions) if conditions else None


class Retriever:
    def __init__(self) -> None:
        self._lock = Lock()
        self._client: Any = None
        self._mode = "not_loaded"
        self._has_dense = False
        self._chunk_count = 0
        self._error: Optional[str] = None

    # ----- setup -----

    def _load_memory(self) -> None:
        chunks = store.load_chunks()
        vectors = store.load_vectors()
        client = store.connect_memory()
        name = config.qdrant_collection()
        store.recreate_collection(client, name)
        with_dense = store.upsert_chunks(client, name, chunks, vectors)
        self._client = client
        self._mode = "memory"
        self._chunk_count = len(chunks)
        self._has_dense = with_dense == len(chunks) > 0

    def _load_cloud(self) -> None:
        client = store.connect_cloud()
        name = config.qdrant_collection()
        if not client.collection_exists(name):
            raise RuntimeError(f"Collection '{name}' not found; run: python -m rag.build_index")
        self._client = client
        self._mode = "cloud"
        self._chunk_count = client.count(collection_name=name, exact=True).count
        self._has_dense = bool(store.load_meta().get("has_dense"))

    def _ensure_ready(self) -> None:
        if self._client is not None:
            return
        with self._lock:
            if self._client is not None:
                return
            if config.qdrant_url():
                try:
                    self._load_cloud()
                    self._error = None
                    LOGGER.info("RAG: using Qdrant Cloud (%d chunks).", self._chunk_count)
                    return
                except Exception as exc:
                    self._error = f"Qdrant Cloud unavailable: {exc}"
                    LOGGER.exception("RAG: Qdrant Cloud unavailable; falling back to in-memory index.")
            self._load_memory()
            LOGGER.info("RAG: using in-memory Qdrant (%d chunks).", self._chunk_count)

    def warm_up(self) -> None:
        try:
            self._ensure_ready()
        except Exception as exc:
            self._error = str(exc)
            LOGGER.exception("RAG index failed to load.")

    # ----- queries -----

    def _dense_query(self, query: str) -> Optional[List[float]]:
        if not (self._has_dense and config.gemini_api_key()):
            return None
        try:
            return list(embed_query(query))
        except Exception:
            LOGGER.warning("RAG: query embedding failed; using keyword search only.", exc_info=True)
            return None

    def retrieve(
        self,
        query: str,
        k: int = 4,
        source_ids: Optional[Sequence[str]] = None,
        chapters: Optional[Sequence[str]] = None,
    ) -> List[Passage]:
        """Top-k passages. source_ids / chapters limit the search to chunks that
        come from any of those sources OR any of those chapters."""
        self._ensure_ready()
        dense = self._dense_query(query)
        name = config.qdrant_collection()
        query_filter = _build_filter(source_ids, chapters)
        if self._mode == "memory":
            with self._lock:  # the in-memory client is plain Python; keep it single-threaded
                hits = store.search(self._client, name, query, dense, k, query_filter)
        else:
            hits = store.search(self._client, name, query, dense, k, query_filter)
        return [passage_from_payload(payload, score) for payload, score in hits]

    def status(self) -> Dict[str, Any]:
        """Cheap status for /health; never connects to anything."""
        return {
            "ready": self._client is not None,
            "mode": self._mode,
            "chunks": self._chunk_count,
            "hybrid": self._has_dense and bool(config.gemini_api_key()),
            "error": self._error,
        }


_RETRIEVER = Retriever()


def get_retriever() -> Retriever:
    return _RETRIEVER


def retrieve(
    query: str,
    k: int = 4,
    source_ids: Optional[Sequence[str]] = None,
    chapters: Optional[Sequence[str]] = None,
) -> List[Passage]:
    return _RETRIEVER.retrieve(query, k, source_ids, chapters)

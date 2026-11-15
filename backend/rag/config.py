"""Paths and settings for the RAG module.

Settings are read from environment variables at call time, so they pick up
backend/.env after main.py (or build_index.py) has called load_dotenv().
"""

from __future__ import annotations

import os
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parent
BACKEND_DIR = RAG_DIR.parent
SOURCES_DIR = RAG_DIR / "sources"
DATA_DIR = RAG_DIR / "data"
# Human-readable chunks (open this file to see how the documents were split).
CHUNKS_PATH = DATA_DIR / "chunks.jsonl"
# Gemini embeddings keyed by a hash of the embedded text, so a rebuild only
# re-embeds chunks whose text changed.
VECTORS_PATH = DATA_DIR / "dense_vectors.json"

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
EMBED_DIM = 768

_GEMINI_KEY_ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
_PLACEHOLDER_VALUES = {
    "",
    "your_gemini_api_key_here",
    "your_google_api_key_here",
    "your_qdrant_api_key_here",
}


def gemini_api_key() -> str:
    for name in _GEMINI_KEY_ENV_NAMES:
        value = os.getenv(name, "").strip()
        if value not in _PLACEHOLDER_VALUES:
            return value
    return ""


def gemini_chat_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def gemini_embed_model() -> str:
    return os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")


def qdrant_url() -> str:
    return os.getenv("QDRANT_URL", "").strip()


def qdrant_api_key() -> str | None:
    value = os.getenv("QDRANT_API_KEY", "").strip()
    return None if value in _PLACEHOLDER_VALUES else value


def qdrant_collection() -> str:
    return os.getenv("QDRANT_COLLECTION", "oral_health_kb").strip()

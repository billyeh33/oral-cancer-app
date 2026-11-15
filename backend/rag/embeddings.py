"""Dense (semantic) vectors from the Gemini embedding API."""

from __future__ import annotations

import math
import time
from functools import lru_cache
from typing import Any, List, Sequence

from . import config

BATCH_SIZE = 50
TIMEOUT_MS = 30_000


@lru_cache(maxsize=2)
def _client(api_key: str) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=TIMEOUT_MS, api_version="v1beta"),
    )


def _normalize(values: Sequence[float]) -> List[float]:
    # Gemini only normalizes the full 3072-dim output; shorter outputs need it here.
    length = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / length for v in values]


def embed(texts: Sequence[str], task_type: str) -> List[List[float]]:
    """task_type: "RETRIEVAL_DOCUMENT" for chunks, "RETRIEVAL_QUERY" for questions."""
    api_key = config.gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    from google.genai import types

    client = _client(api_key)
    vectors: List[List[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start : start + BATCH_SIZE])
        for attempt in range(4):
            try:
                response = client.models.embed_content(
                    model=config.gemini_embed_model(),
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=config.EMBED_DIM,
                    ),
                )
                break
            except Exception:
                # The free tier rate-limits bursts; back off and retry.
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        vectors.extend(_normalize(item.values) for item in response.embeddings)
    return vectors


@lru_cache(maxsize=256)
def embed_query(text: str) -> tuple[float, ...]:
    return tuple(embed([text], "RETRIEVAL_QUERY")[0])

"""Keyword (sparse) vectors for Traditional Chinese text.

Chinese has no spaces between words, so the text is split into overlapping
two-character pieces (bigrams): 「口腔白斑」 -> 口腔, 腔白, 白斑. Latin words and
numbers are kept whole. Document vectors use BM25 term weights; Qdrant adds the
IDF part itself (the collection's sparse vector uses Modifier.IDF).
"""

from __future__ import annotations

import re
import unicodedata
import zlib
from collections import Counter
from typing import Dict, Iterable, List, Tuple

_CJK = "㐀-䶿一-鿿豈-﫿"
_TOKEN_RUN = re.compile(f"[{_CJK}]+|[a-z0-9]+")
_CJK_RUN = re.compile(f"^[{_CJK}]+$")

BM25_K1 = 1.2
BM25_B = 0.75


def tokenize(text: str) -> List[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: List[str] = []
    for run in _TOKEN_RUN.findall(normalized):
        if _CJK_RUN.match(run):
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        elif len(run) > 1 or run.isdigit():
            tokens.append(run)
    return tokens


def token_id(token: str) -> int:
    # crc32 is stable across processes, unlike Python's built-in hash().
    return zlib.crc32(token.encode("utf-8")) & 0x7FFFFFFF


def _merge_ids(weights: Iterable[Tuple[str, float]]) -> Tuple[List[int], List[float]]:
    merged: Dict[int, float] = {}
    for token, weight in weights:
        index = token_id(token)
        merged[index] = merged.get(index, 0.0) + weight
    indices = sorted(merged)
    return indices, [merged[i] for i in indices]


def document_vector(text: str, avg_length: float) -> Tuple[List[int], List[float]]:
    tokens = tokenize(text)
    length = len(tokens) or 1
    norm = BM25_K1 * (1 - BM25_B + BM25_B * length / max(avg_length, 1.0))
    counts = Counter(tokens)
    return _merge_ids(
        (token, count * (BM25_K1 + 1) / (count + norm)) for token, count in counts.items()
    )


def query_vector(text: str) -> Tuple[List[int], List[float]]:
    return _merge_ids((token, 1.0) for token in set(tokenize(text)))


def average_length(texts: Iterable[str]) -> float:
    lengths = [len(tokenize(text)) for text in texts]
    return sum(lengths) / len(lengths) if lengths else 1.0

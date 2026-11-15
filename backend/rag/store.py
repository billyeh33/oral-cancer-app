"""Qdrant storage: index files on disk, collection setup and hybrid search.

Each chunk is stored as one Qdrant point with two vectors:
- "dense":  Gemini embedding (meaning-based match, e.g. 「擦不掉的白色東西」 -> 白斑)
- "sparse": keyword bigrams with BM25/IDF weights (exact terms, e.g. 「OSF」)
A search runs both and merges the rankings with Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

from qdrant_client import QdrantClient, models

from . import config, sparse
from .chunking import Chunk

PREFETCH_LIMIT = 20
_POINT_NAMESPACE = uuid.UUID("6f1c3d1e-6a43-4c8e-9a51-0b8f6f3c2a10")
META_PATH = config.DATA_DIR / "index_meta.json"


# ---------- index files ----------

def save_index_files(chunks: Sequence[Chunk], vectors: Dict[str, List[float]], meta: Dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with config.CHUNKS_PATH.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_json(), ensure_ascii=False) + "\n")
    rounded = {key: [round(v, 6) for v in vector] for key, vector in vectors.items()}
    config.VECTORS_PATH.write_text(json.dumps(rounded), encoding="utf-8")
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_chunks() -> List[Chunk]:
    with config.CHUNKS_PATH.open(encoding="utf-8") as handle:
        return [Chunk(**json.loads(line)) for line in handle if line.strip()]


def load_vectors() -> Dict[str, List[float]]:
    if not config.VECTORS_PATH.exists():
        return {}
    return json.loads(config.VECTORS_PATH.read_text(encoding="utf-8"))


def load_meta() -> Dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


# ---------- Qdrant ----------

def connect_cloud() -> QdrantClient:
    return QdrantClient(url=config.qdrant_url(), api_key=config.qdrant_api_key(), timeout=15)


def connect_memory() -> QdrantClient:
    return QdrantClient(":memory:")


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


def recreate_collection(client: QdrantClient, name: str) -> None:
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config={
            config.DENSE_VECTOR_NAME: models.VectorParams(
                size=config.EMBED_DIM, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={
            config.SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )


def upsert_chunks(
    client: QdrantClient,
    name: str,
    chunks: Sequence[Chunk],
    vectors: Dict[str, List[float]],
) -> int:
    """Upload chunks; returns how many got a dense vector."""
    avg_length = sparse.average_length(chunk.embed_text() for chunk in chunks)
    points = []
    with_dense = 0
    for chunk in chunks:
        indices, values = sparse.document_vector(chunk.embed_text(), avg_length)
        vector: Dict = {config.SPARSE_VECTOR_NAME: models.SparseVector(indices=indices, values=values)}
        dense = vectors.get(chunk.text_hash())
        if dense is not None:
            vector[config.DENSE_VECTOR_NAME] = dense
            with_dense += 1
        points.append(
            models.PointStruct(id=point_id(chunk.chunk_id), vector=vector, payload=chunk.to_json())
        )
    for start in range(0, len(points), 64):
        client.upsert(collection_name=name, points=points[start : start + 64], wait=True)
    return with_dense


def create_payload_indexes(client: QdrantClient, name: str) -> None:
    """Qdrant Cloud needs an index on a payload field before it can filter on it."""
    for field in ("source_id", "chapter"):
        client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )


def search(
    client: QdrantClient,
    name: str,
    query: str,
    dense_query: Optional[Sequence[float]],
    limit: int,
    query_filter: Optional[models.Filter] = None,
) -> List[Tuple[Dict, float]]:
    indices, values = sparse.query_vector(query)
    sparse_query = models.SparseVector(indices=indices, values=values)
    if dense_query is not None:
        prefetch = [
            models.Prefetch(
                query=list(dense_query),
                using=config.DENSE_VECTOR_NAME,
                filter=query_filter,
                limit=PREFETCH_LIMIT,
            )
        ]
        if indices:
            prefetch.append(
                models.Prefetch(
                    query=sparse_query,
                    using=config.SPARSE_VECTOR_NAME,
                    filter=query_filter,
                    limit=PREFETCH_LIMIT,
                )
            )
        response = client.query_points(
            collection_name=name,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
        )
    elif indices:
        response = client.query_points(
            collection_name=name,
            query=sparse_query,
            using=config.SPARSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
    else:
        return []
    return [(point.payload or {}, float(point.score)) for point in response.points]

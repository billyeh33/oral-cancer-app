"""Build the RAG index: split the documents, embed them, upload to Qdrant.

Run from the backend folder (needs `pip install -r rag/requirements-build.txt`):
    python -m rag.build_index               # full build; uploads to Qdrant Cloud if QDRANT_URL is set
    python -m rag.build_index --skip-embed  # keyword index only (no GEMINI_API_KEY needed)
    python -m rag.build_index --no-upload   # write rag/data/ but leave Qdrant Cloud alone

Outputs in rag/data/ (commit these; the website reads them):
    chunks.jsonl        every chunk, readable — open it to check the splitting
    dense_vectors.json  Gemini embeddings, reused on the next build if a chunk is unchanged
    index_meta.json     build info (model, chunk count, whether embeddings are complete)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from . import config, store
from .chunking import SOURCES, build_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-embed", action="store_true", help="do not call the Gemini embedding API")
    parser.add_argument("--no-upload", action="store_true", help="do not upload to Qdrant Cloud")
    args = parser.parse_args()

    load_dotenv(config.BACKEND_DIR / ".env")

    chunks = build_chunks()
    print(f"Split {len(SOURCES)} sources into {len(chunks)} chunks.")

    old_meta = store.load_meta()
    old_vectors = store.load_vectors()
    if old_meta.get("embed_model") != config.gemini_embed_model():
        old_vectors = {}  # vectors from another model are not comparable
    wanted = {chunk.text_hash(): chunk.embed_text() for chunk in chunks}
    vectors = {key: old_vectors[key] for key in wanted if key in old_vectors}
    missing = [key for key in wanted if key not in vectors]

    if missing and not args.skip_embed:
        if not config.gemini_api_key():
            print("GEMINI_API_KEY is not set in backend/.env. Add it, or rerun with --skip-embed.")
            return 1
        from .embeddings import embed

        print(f"Embedding {len(missing)} new or changed chunks with {config.gemini_embed_model()} ...")
        for key, vector in zip(missing, embed([wanted[key] for key in missing], "RETRIEVAL_DOCUMENT")):
            vectors[key] = vector
    print(f"Embeddings: {len(vectors)}/{len(chunks)} chunks (reused {len(wanted) - len(missing)}).")

    has_dense = len(vectors) == len(chunks)
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embed_model": config.gemini_embed_model() if vectors else None,
        "embed_dim": config.EMBED_DIM,
        "chunk_count": len(chunks),
        "has_dense": has_dense,
        "collection": config.qdrant_collection(),
        "sources": [source["title"] for source in SOURCES],
    }
    store.save_index_files(chunks, vectors, meta)
    print(f"Wrote {config.CHUNKS_PATH.relative_to(config.BACKEND_DIR)} and the vectors/meta files.")

    if config.qdrant_url() and not args.no_upload:
        if not has_dense and not args.skip_embed:
            print("Not uploading: some chunks have no embedding.")
            return 1
        if not has_dense:
            print("Uploading keyword vectors only (--skip-embed); rebuild with a Gemini key for hybrid search.")
        client = store.connect_cloud()
        name = config.qdrant_collection()
        store.recreate_collection(client, name)
        store.create_payload_indexes(client, name)
        store.upsert_chunks(client, name, chunks, vectors)
        count = client.count(collection_name=name, exact=True).count
        print(f"Uploaded {count} points to Qdrant collection '{name}'.")
    elif not config.qdrant_url():
        print("QDRANT_URL not set: the website will use the in-memory index from rag/data/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

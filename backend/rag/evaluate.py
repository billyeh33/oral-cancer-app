"""Measure retrieval quality on rag/eval_questions.json.

Run from the backend folder:
    python -m rag.evaluate          # uses the same setup as the website (.env)
    python -m rag.evaluate -k 3

For each question, a hit means one of the expected chunks (matched by id prefix,
e.g. "handbook-p18" matches "handbook-p18-1") is in the top k results.
  Hit@k : share of questions with a hit
  MRR   : average of 1/rank of the first expected chunk (0 if missing)
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from . import config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", type=int, default=4)
    parser.add_argument("--keyword-only", action="store_true", help="ignore embeddings")
    args = parser.parse_args()

    load_dotenv(config.BACKEND_DIR / ".env")
    if args.keyword_only:
        import os

        os.environ["GEMINI_API_KEY"] = ""
        os.environ.pop("GOOGLE_API_KEY", None)
    from .retriever import get_retriever

    retriever = get_retriever()
    questions = json.loads((config.RAG_DIR / "eval_questions.json").read_text(encoding="utf-8"))
    hits = 0
    reciprocal_ranks = []
    for item in questions:
        results = retriever.retrieve(item["question"], args.k)
        rank = next(
            (
                position
                for position, passage in enumerate(results, start=1)
                if any(passage.chunk_id.startswith(expected) for expected in item["expected"])
            ),
            None,
        )
        hits += rank is not None
        reciprocal_ranks.append(1 / rank if rank else 0.0)
        mark = f"#{rank}" if rank else "MISS"
        top = ", ".join(p.chunk_id for p in results)
        print(f"{mark:>5}  {item['question']}\n       -> {top}")

    status = retriever.status()
    print()
    print(f"Mode: {status['mode']}, hybrid (embeddings + keywords): {status['hybrid']}")
    print(f"Hit@{args.k}: {hits}/{len(questions)} = {hits / len(questions):.0%}")
    print(f"MRR@{args.k}: {sum(reciprocal_ranks) / len(questions):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""RAG (retrieval-augmented generation) over the oral-health education documents.

Public API used by main.py:
    answer_question(question, prediction=None) -> {"answer", "status", "sources"}
    build_report(class_probabilities)           -> result-page content (for /predict, /explain)
    get_retriever().status() / .warm_up()

See rag/README.md for how the index is built and how to call the API.
"""

from .answer import answer_question, format_passages
from .explain import build_report
from .retriever import Passage, get_retriever, retrieve

__all__ = [
    "Passage",
    "answer_question",
    "build_report",
    "format_passages",
    "get_retriever",
    "retrieve",
]

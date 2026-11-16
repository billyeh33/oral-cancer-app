"""Content of the result page (/predict and /explain), section by section.

The page has three sections, each produced a different way so the text always
fits its heading and needs no live LLM call:

  結果說明  summary    template filled with the probabilities
  就診建議  care       hand-written per class from the 處置流程 / handbook,
                       each field backed by the chunks in CARE[...]["basis"]
  衛教說明  education  written once per class by RAG (build_explain_content.py),
                       stored in rag/data/explain_content.json for human review

Plus one link to the official handbook page (HANDBOOK_LINK).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict

from . import config, store
from .links import find_links
from .retriever import passage_from_payload

CONTENT_PATH = config.DATA_DIR / "explain_content.json"

# Top-two probabilities closer than this are reported as an uncertain call.
CLOSE_CALL_MARGIN = 0.25

CLASS_LABELS_ZH = {
    "Normal": "未見明顯異常",
    "Benign": "良性病灶",
    "OPMD": "口腔潛在惡性疾患（癌前病變）",
    "Oral Cancer": "疑似口腔癌病灶",
}

HANDBOOK_LINK = {
    "title": "口腔黏膜異常患者之口腔保健指導手冊（民眾版）",
    "publisher": "衛生福利部",
    "url": "https://dep.mohw.gov.tw/DOOH/cp-6545-77332-124.html",
}

_BRING = "這次上傳的照片、發現異狀的時間與位置、是否疼痛或出血；如果有吸菸、喝酒或嚼檳榔的習慣，也請告訴醫師"

# 就診建議. "basis" lists the chunks each recommendation is based on (shown as sources).
CARE: Dict[str, Dict[str, Any]] = {
    "Normal": {
        "department": "牙科、口腔外科或耳鼻喉科；可用健保署「健保特約醫療機構查詢」找能做口腔黏膜檢查的院所",
        "timing": "定期檢查口腔黏膜；如果破皮或異狀超過兩星期仍未癒合，請就醫檢查",
        "bring": _BRING,
        "basis": ["handbook-p62-1", "handbook-p68-1"],
    },
    "Benign": {
        "department": "牙科、口腔外科或耳鼻喉科；可用健保署「健保特約醫療機構查詢」找附近的院所",
        "timing": "近期安排門診；如果超過兩星期仍未癒合，或反覆出現，請盡快就醫",
        "bring": _BRING,
        "basis": ["handbook-p63-1", "handbook-p68-1"],
    },
    # Oral cancer screening moved from 國健署 to 衛福部口腔健康司 in 2023, so the
    # hospital list is named by its current publisher (the handbook says 國健署).
    "OPMD": {
        "department": "口腔顎面外科，或具頭頸癌診治專業的耳鼻喉科；可先查衛福部「口腔癌確認診斷及治療醫院名單」",
        "timing": "盡快就醫，由醫師評估是否需要切片檢查",
        "bring": _BRING,
        "basis": ["flowchart-2", "handbook-p71-1"],
    },
    "Oral Cancer": {
        "department": "口腔顎面外科，或具頭頸癌診治專業的耳鼻喉科；可先查衛福部「口腔癌確認診斷及治療醫院名單」",
        "timing": "盡快就醫，不建議延後；是否需要切片檢查由醫師評估",
        "bring": _BRING,
        "basis": ["flowchart-2", "handbook-p71-1"],
    },
}


def format_percent(probability: float) -> str:
    # Rounding 0.996 to "100%" reads as certainty, which a screening tool never has.
    if probability >= 0.995:
        return "99% 以上"
    if probability < 0.01:
        return "不到 1%"
    return f"約 {round(probability * 100)}%"


def build_summary(class_probabilities: Dict[str, float]) -> str:
    ranked = sorted(class_probabilities.items(), key=lambda item: item[1], reverse=True)
    (top, top_p), (second, second_p) = ranked[:2]
    text = f"AI 篩檢最可能為「{CLASS_LABELS_ZH[top]}」，{format_percent(top_p)}。"
    if top_p - second_p < CLOSE_CALL_MARGIN:
        text += (
            f"第二可能為「{CLASS_LABELS_ZH[second]}」，{format_percent(second_p)}，"
            "兩者很接近，AI 難以明確區分，更需要由醫師檢查確認。"
        )
    elif second_p >= 0.01:
        text += f"其次為「{CLASS_LABELS_ZH[second]}」，{format_percent(second_p)}。"
    text += "這只是依照片做的初步分類，實際情況要由醫師檢查確認。"
    return text


@lru_cache(maxsize=1)
def _chunks_by_id() -> Dict[str, Dict[str, Any]]:
    return {chunk.chunk_id: chunk.to_json() for chunk in store.load_chunks()}


@lru_cache(maxsize=1)
def _education_content() -> Dict[str, Any]:
    if not CONTENT_PATH.exists():
        return {}
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def _source(chunk_id: str) -> Dict[str, Any] | None:
    payload = _chunks_by_id().get(chunk_id)
    return passage_from_payload(payload).to_dict() if payload else None


def _stored_lesion_report(class_probabilities: Dict[str, float]) -> Dict[str, Any] | None:
    from .lesion_education import stored_report  # imported here: lesion_education imports this module

    return stored_report(class_probabilities)


def build_report(class_probabilities: Dict[str, float]) -> Dict[str, Any]:
    prediction = max(class_probabilities, key=class_probabilities.get)
    care = CARE[prediction]
    care_sources = [s for s in (_source(cid) for cid in care["basis"]) if s]

    content = _education_content()
    education = []
    for item in content.get("classes", {}).get(prediction, {}).get("items", []):
        item_sources = [s for s in (_source(cid) for cid in item["chunk_ids"]) if s]
        if item_sources:
            education.append(
                {
                    "heading": item["heading"],
                    "text": item["text"],
                    "sources": item_sources,
                    "links": find_links(item["text"]),
                }
            )

    summary = build_summary(class_probabilities)
    all_sources = care_sources + [s for e in education for s in e["sources"]]
    sources = {s["chunk_id"]: s for s in all_sources}
    return {
        "summary": summary,
        "care": {
            "department": care["department"],
            "timing": care["timing"],
            "bring": care["bring"],
            "sources": care_sources,
            # Lookup sites named in the three fields, to show as hyperlinks.
            "links": find_links(care["department"], care["timing"], care["bring"]),
        },
        "education": education,
        # 結構化衛教（每個病灶固定欄位），先放事先產生的版本，/education 再換成這次撰寫的版本。
        "lesion_report": _stored_lesion_report(class_probabilities),
        "handbook": HANDBOOK_LINK,
        "content_reviewed": bool(content.get("reviewed")),
        # Older fields kept so the current frontend keeps working.
        "explanation": summary,
        "care_guidance": "\n".join(
            [
                f"1. 建議科別：{care['department']}",
                f"2. 就醫時機：{care['timing']}",
                f"3. 就診時可以告訴醫師：{care['bring']}",
            ]
        ),
        "source": "curated",
        "sources": list(sources.values()),
    }

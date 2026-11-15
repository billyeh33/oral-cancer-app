"""Write the 衛教說明 section for each screening result with RAG.

Run from the backend folder after build_index:
    python -m rag.build_explain_content            # all four classes
    python -m rag.build_explain_content --only OPMD

For each class it searches only the handbook's education chapters, asks Gemini
for 2-3 short points that each cite one passage, checks them, and saves
rag/data/explain_content.json. Read the printed result (or the file) and set
"reviewed": true in the file once a person has checked it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel

from . import config
from .explain import CLASS_LABELS_ZH, CONTENT_PATH
from .retriever import Passage, retrieve

EDUCATION_CHAPTERS = ["常見病變簡介", "Q&A 及常見迷思", "口腔保健綜合建議事項", "衛教資訊"]
PASSAGES_PER_QUERY = 3
MAX_PASSAGES = 6
ATTEMPTS = 3

EDUCATION_QUERIES: Dict[str, List[str]] = {
    "Normal": [
        "避免危險因子 吸菸 飲酒 嚼食檳榔 定期檢查口腔黏膜",
        "口腔破皮 潰瘍 超過兩星期沒有癒合",
        "口腔黏膜檢查 補助對象 每2年一次",
    ],
    "Benign": [
        "口腔破皮 潰瘍的處理 自己癒合",
        "塗抹鹽水 含冰塊 口內膏 偏方",
        "口腔黏膜破洞不一定是口腔癌",
    ],
    "OPMD": [
        "白斑 不同致癌機率 定期檢查",
        "口腔黏膜下纖維化 嚼食檳榔",
        "紅斑 比白斑更容易轉變成口腔癌",
        "戒除菸 酒 檳榔 仍應定期檢查",
    ],
    "Oral Cancer": [
        "切片檢查 確診 口腔癌 癌前病變",
        "吸菸 飲酒 嚼食檳榔 口腔癌 危險因子",
        "偏方 口內膏 延誤處理真正病因",
    ],
}
# The handbook has no chapter on oral cancer itself, so the higher-risk classes may
# also draw on the 處置流程 (how a suspected lesion is confirmed by biopsy).
EXTRA_SOURCES: Dict[str, List[str]] = {"OPMD": ["flowchart"], "Oral Cancer": ["flowchart"]}

SYSTEM_INSTRUCTION = """
你是台灣口腔健康衛教網站的編輯。使用者剛拿到 AI 篩檢結果，你要根據使用者訊息中的「參考資料」，為結果頁的「衛教說明」區塊寫 2～3 則重點。

請輸出 JSON：items 陣列，每則包含
- heading：8～16 字的小標題，寫成問句或主題（例如「口腔破皮常見嗎？」「為什麼要遠離檳榔？」）
- text：40～90 字的說明
- cited：這則內容用到的參考資料編號，1～2 個整數；內容出自哪幾段就要全部列出

規則：
1. 只能使用參考資料裡的內容，不可加入參考資料沒有的醫療資訊或數字，也不要加上「不用擔心」「不需恐慌」這類原文沒有的安撫或評價。
2. 寫成這一類結果的一般性衛教。AI 篩檢無法判斷是哪一種病灶，不可說使用者可能是某種特定疾病，不可診斷；標題也不要用症狀發問（例如「口腔出現緊繃感是什麼原因？」），要用主題（例如「認識口腔黏膜下纖維化」）。
3. 不寫看哪一科、什麼時候就醫（另一個區塊會寫），不提供藥物、劑量或治療方式。
4. 結果為「口腔潛在惡性疾患（癌前病變）」或「疑似口腔癌病灶」時，不可寫「兩星期」「會自己好」「自行癒合」「注意變化」「觀察」等可能讓人延後就醫的內容。
   也不可寫「每半年」「每三個月」這類追蹤間隔，那是醫師針對特定病灶的安排，AI 篩檢無法判斷是哪一種病灶。
5. 不要假設使用者有吸菸、喝酒、嚼檳榔的習慣；需要提到時寫成「如果有……」。
6. 各則主題不要重複。繁體中文、台灣用語、語氣溫和，純文字，不用 Markdown，不寫免責聲明。
""".strip()

_DELAY_WORDS = re.compile(r"兩星期|兩週|二週|自己好|自行癒合|自己癒合|注意.{0,4}變化|觀察|每\s*[半一二三四五六3-6]\s*(?:個)?\s*[月年]")
_REASSURANCE = re.compile(r"不用擔心|不必擔心|不需.{0,2}恐慌|不用緊張|別擔心")


class EducationItem(BaseModel):
    heading: str
    text: str
    cited: List[int]


class EducationOutput(BaseModel):
    items: List[EducationItem]


def gather_passages(prediction: str) -> List[Passage]:
    seen: Dict[str, Passage] = {}
    for query in EDUCATION_QUERIES[prediction]:
        for passage in retrieve(
            query,
            PASSAGES_PER_QUERY,
            source_ids=EXTRA_SOURCES.get(prediction),
            chapters=EDUCATION_CHAPTERS,
        ):
            seen.setdefault(passage.chunk_id, passage)
    return list(seen.values())[:MAX_PASSAGES]


def _prompt(prediction: str, passages: List[Passage]) -> str:
    blocks = [
        f"[{n}] 第 {p.page} 頁" + (f"｜{p.title}" if p.title else "") + f"\n{p.text}"
        for n, p in enumerate(passages, start=1)
    ]
    return f"AI 篩檢結果：{CLASS_LABELS_ZH[prediction]}\n\n參考資料：\n" + "\n\n".join(blocks)


def _problems(prediction: str, output: EducationOutput, passage_count: int) -> List[str]:
    problems = []
    if not 2 <= len(output.items) <= 3:
        problems.append(f"{len(output.items)} items")
    for item in output.items:
        if not 4 <= len(item.heading) <= 18:
            problems.append(f"heading length {len(item.heading)}: {item.heading}")
        if not 25 <= len(item.text) <= 120:
            problems.append(f"text length {len(item.text)}: {item.heading}")
        if not 1 <= len(item.cited) <= 2 or any(not 1 <= n <= passage_count for n in item.cited):
            problems.append(f"bad citation {item.cited}")
        if prediction in ("OPMD", "Oral Cancer") and _DELAY_WORDS.search(item.text):
            problems.append(f"delay wording: {item.text}")
        if _REASSURANCE.search(item.text):
            problems.append(f"reassurance not in the source: {item.text}")
    return problems


def generate(prediction: str) -> Optional[Dict]:
    from google.genai import types

    from .answer import _gemini_client

    passages = gather_passages(prediction)
    client = _gemini_client(config.gemini_api_key())
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=config.gemini_chat_model(),
                contents=_prompt(prediction, passages),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.3,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                    response_schema=EducationOutput,
                ),
            )
            output = EducationOutput.model_validate_json(response.text or "")
        except Exception as exc:
            # Busy model (503), rate limit (429) or unreadable JSON: wait and retry.
            print(f"  attempt {attempt}: {str(exc)[:120]}")
            time.sleep(15 * attempt)
            continue
        problems = _problems(prediction, output, len(passages))
        if problems:
            print(f"  attempt {attempt}: " + "; ".join(problems))
            continue
        return {
            "items": [
                {
                    "heading": item.heading.strip(),
                    "text": item.text.strip(),
                    "chunk_ids": list(dict.fromkeys(passages[n - 1].chunk_id for n in item.cited)),
                }
                for item in output.items
            ],
            "passages_considered": [p.chunk_id for p in passages],
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=sorted(EDUCATION_QUERIES), action="append")
    args = parser.parse_args()

    load_dotenv(config.BACKEND_DIR / ".env")
    if not config.gemini_api_key():
        print("GEMINI_API_KEY is not set in backend/.env.")
        return 1

    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8")) if CONTENT_PATH.exists() else {}
    classes = content.get("classes", {})
    failed = []
    for prediction in args.only or list(EDUCATION_QUERIES):
        print(f"\n== {prediction}（{CLASS_LABELS_ZH[prediction]}）")
        result = generate(prediction)
        if result is None:
            failed.append(prediction)
            print("  FAILED: kept the previous content (if any).")
            continue
        classes[prediction] = result
        for item in result["items"]:
            print(f"  ・{item['heading']}  {item['chunk_ids']}\n    {item['text']}")

    content = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": config.gemini_chat_model(),
        # Set to true by hand after someone has read every item against the handbook.
        "reviewed": False,
        "classes": classes,
    }
    CONTENT_PATH.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {CONTENT_PATH.relative_to(config.BACKEND_DIR)}. Review it, then set \"reviewed\": true.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

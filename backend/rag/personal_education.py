"""衛教說明 written for this one screening result (POST /education).

The result page first shows the reviewed per-class text from explain_content.json
(it comes back with /predict, so the page is never empty). The frontend then calls
/education, which writes 3 points for these exact probabilities:

  1. take the handbook passages retrieved for the most likely class when
     explain_content.json was built, plus those of the second class when it is
     10% or more (an OPMD 87% / cancer 12% result should also read about cancer);
  2. Gemini writes 3 points from those passages only, each citing 1-2 of them;
  3. the same checks as build_explain_content (length, citations, no wording that
     could make a high-risk user wait, no reassurance the source does not say).

Anything that fails returns None and the page keeps the reviewed text.
Nothing is cached: each upload is written afresh, so the same photo reads a little
differently each time (one Gemini call per upload).
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .build_explain_content import _DELAY_WORDS, _REASSURANCE, EducationOutput
from .explain import CLASS_LABELS_ZH, _chunks_by_id, _education_content, format_percent
from .links import find_links
from .retriever import Passage, passage_from_payload

try:  # backend/labels.py (main.py runs with backend/ on the path)
    from labels import RISK_LEVELS
except ImportError:  # pragma: no cover
    RISK_LEVELS = {"Normal": "低風險", "Benign": "中低風險", "OPMD": "中高風險", "Oral Cancer": "高風險"}

LOGGER = logging.getLogger("oral_lesion_screening.rag")

SECOND_CLASS_MIN = 0.10
_CONNECTIVES = re.compile(r"此外|因此|總之|綜上所述|總的來說")
MAX_PASSAGES = 10
HIGH_RISK = ("OPMD", "Oral Cancer")

SYSTEM_INSTRUCTION = """
你是台灣口腔健康衛教網站的編輯。使用者剛拿到這一次的 AI 篩檢結果，你要依照「這次的結果」與使用者訊息中的「參考資料」，為結果頁的「衛教說明」區塊寫 3 則重點，讓使用者看完知道這個結果跟自己有什麼關係。

請輸出 JSON：items 陣列，每則包含
- heading：6～16 字的小標題，用主題寫（例如「白斑與紅斑是什麼」「為什麼要遠離檳榔」）
- text：50～130 字的說明，用「你」稱呼使用者
- cited：這則內容用到的參考資料編號，1～3 個整數，內容出自哪幾段就全部列出

三則的分工：
第 1 則：用白話說明這次結果最可能的類別代表什麼。如果訊息裡有「第二可能」，也要提到兩種都有可能，所以更需要醫師檢查確認。
第 2 則：介紹「最可能的類別」常見的病灶或狀況，例如外觀、和口腔癌的關係。
第 3 則：生活上可以做的事或常見迷思，例如遠離菸酒檳榔、不要自己塗偏方。

規則：
1. 只能使用參考資料裡的內容，不可加入參考資料沒有的醫療資訊或數字，也不要加上「不用擔心」「不需恐慌」這類原文沒有的安撫或評價。
2. AI 篩檢只看照片，無法判斷是哪一種病灶，不可說使用者一定是某種疾病，不可診斷。
3. 不寫看哪一科、什麼時候就醫（另一個區塊會寫），不提供藥物、劑量或治療方式。
4. 這次結果包含「口腔潛在惡性疾患（癌前病變）」或「疑似口腔癌病灶」時，不可寫「兩星期」「會自己好」「自行癒合」「注意變化」「觀察」等可能讓人延後就醫的內容，也不可寫「每半年」「每三個月」這類追蹤間隔。
5. 不要假設使用者有吸菸、喝酒、嚼檳榔的習慣，需要提到時寫成「如果有……」。
6. 提到機率時照訊息裡的寫法，例如「約 87%」，不要寫成「百分之八十七」或「約佔」。
7. 三則主題不要重複。繁體中文、台灣用語、語氣溫和、口語，不用「此外」「因此」「總之」「綜上所述」這類轉折詞，純文字，不用 Markdown，不寫免責聲明。
""".strip()


def _ranked(class_probabilities: Dict[str, float]) -> List[Tuple[str, float]]:
    return sorted(class_probabilities.items(), key=lambda item: item[1], reverse=True)


def _gather(top: str, second: Optional[str]) -> List[Passage]:
    """Passages already retrieved for each class when explain_content.json was built
    (no embedding call at request time, so this costs nothing and takes no time)."""
    classes = _education_content().get("classes", {})
    ids: List[str] = []
    for name in (top, second):
        if name:
            ids += classes.get(name, {}).get("passages_considered", [])
    chunks = _chunks_by_id()
    passages = [passage_from_payload(chunks[cid]) for cid in dict.fromkeys(ids) if cid in chunks]
    return passages[:MAX_PASSAGES]


def _passage_text(text: str, high_risk: bool) -> str:
    """處置流程把「約二星期仍不癒的潰爛」列在轉介清單裡，模型常整段照抄，
    對高風險結果讀起來像可以先等兩週，所以餵給模型前先拿掉這一項。"""
    if high_risk:
        text = re.sub(r"、?約?[兩二]星期仍不癒的口腔潰爛或糜爛", "", text)
        # 官方網頁寫的「遵照醫囑每3-6個月定期追蹤」是確診後的安排，不適合寫給還沒就醫的人。
        text = re.sub(r"，?並?遵照醫囑每\s*3\s*-\s*6\s*個月定期追蹤\s*1\s*次", "", text)
    return text


def _prompt(ranked: List[Tuple[str, float]], second: Optional[str], passages: List[Passage]) -> str:
    (top, top_p) = ranked[0]
    lines = [
        f"這次的 AI 篩檢結果：最可能為「{CLASS_LABELS_ZH[top]}」，{format_percent(top_p)}，風險分級為{RISK_LEVELS[top]}。"
    ]
    if second:
        second_p = dict(ranked)[second]
        lines.append(f"第二可能：「{CLASS_LABELS_ZH[second]}」，{format_percent(second_p)}。")
    high_risk = top in HIGH_RISK or second in HIGH_RISK
    blocks = [
        f"[{n}] 第 {p.page} 頁" + (f"｜{p.title}" if p.title else "") + f"\n{_passage_text(p.text, high_risk)}"
        for n, p in enumerate(passages, start=1)
    ]
    return "\n".join(lines) + "\n\n參考資料：\n" + "\n\n".join(blocks)


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_number(text: str) -> Optional[int]:
    """一～九十九的國字數字，例如 八十七 → 87、十二 → 12。"""
    if not text or any(ch not in _CN_DIGITS and ch != "十" for ch in text):
        return None
    if "十" not in text:
        return _CN_DIGITS[text] if len(text) == 1 else None
    tens, _, ones = text.partition("十")
    return (_CN_DIGITS.get(tens, 1) if tens else 1) * 10 + (_CN_DIGITS.get(ones, 0) if ones else 0)


def _tidy(text: str) -> str:
    """機率寫法統一成「約 87%」，並拿掉轉折詞，和結果說明的寫法一致。"""
    def cn_percent(match: "re.Match[str]") -> str:
        number = _cn_number(match.group(1))
        return f"約 {number}%" if number is not None else match.group(0)

    text = text.strip()
    text = re.sub(r"約?[佔為]?\s*百分之([零一二兩三四五六七八九十]+)", cn_percent, text)
    text = re.sub(r"約?[佔為]?\s*([零一二兩三四五六七八九十]+)\s*%", cn_percent, text)
    text = re.sub(r"約[佔為]?\s*(\d+)\s*%", r"約 \1%", text)
    text = re.sub(r"(^|[。，])\s*(此外|另外|總之|綜上所述|總的來說)[，,]?", r"\1", text)
    text = text.replace("因此", "所以")
    return text


def _problems(high_risk: bool, output: EducationOutput, passage_count: int) -> List[str]:
    problems = []
    if len(output.items) != 3:
        problems.append(f"{len(output.items)} items")
    for item in output.items:
        if not 4 <= len(item.heading) <= 18:
            problems.append(f"heading length {len(item.heading)}")
        if not 30 <= len(item.text) <= 160:
            problems.append(f"text length {len(item.text)}")
        if not 1 <= len(item.cited) <= 4 or any(not 1 <= n <= passage_count for n in item.cited):
            problems.append(f"bad citation {item.cited}")
        if high_risk and _DELAY_WORDS.search(_tidy(item.text)):
            problems.append("delay wording")
        if _REASSURANCE.search(_tidy(item.text)):
            problems.append("reassurance")
        if _CONNECTIVES.search(_tidy(item.text)):
            problems.append("connective")
        if re.search(r"百分之|[一二三四五六七八九十]\s*%", _tidy(item.text)):
            problems.append("percent wording")
    return problems


def _fallback_model() -> str:
    return os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")


def _write(prompt: str, model: str) -> Optional[EducationOutput]:
    from google.genai import types

    from .answer import _gemini_client

    response = _gemini_client(config.gemini_api_key()).models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7,
            max_output_tokens=1200,
            response_mime_type="application/json",
            response_schema=EducationOutput,
        ),
    )
    return EducationOutput.model_validate_json(getattr(response, "text", "") or "")


def _generate(key: Tuple[Tuple[str, float], ...]) -> Optional[Tuple[Dict[str, Any], ...]]:
    ranked = list(key)
    top = ranked[0][0]
    second = ranked[1][0] if ranked[1][1] >= SECOND_CLASS_MIN else None
    high_risk = top in HIGH_RISK or second in HIGH_RISK
    passages = _gather(top, second)
    if not passages:
        return None
    prompt = _prompt(ranked, second, passages)
    started = time.perf_counter()
    # 3.5 Flash-Lite often answers 503/429 at busy times, so after two tries switch
    # to a second model that has its own quota (GEMINI_FALLBACK_MODEL).
    models = [config.gemini_chat_model()] * 2 + [_fallback_model()] * 2
    for attempt, model in enumerate(models):
        try:
            output = _write(prompt, model)
        except Exception as exc:
            LOGGER.warning("Education: %s failed (%s), attempt %d.", model, getattr(exc, "code", type(exc).__name__), attempt + 1)
            time.sleep(1.0)
            continue
        problems = _problems(high_risk, output, len(passages))
        if problems:
            LOGGER.warning("Education: %s rejected (%s), attempt %d.", model, "; ".join(problems), attempt + 1)
            continue
        LOGGER.info("Education: written by %s in %.1fs.", model, time.perf_counter() - started)
        return tuple(
            {
                "heading": item.heading.strip(),
                "text": _tidy(item.text),
                "sources": [passages[n - 1].to_dict() for n in list(dict.fromkeys(item.cited))[:3]],
                "links": find_links(item.text),
            }
            for item in output.items
        )
    return None


def personal_education(class_probabilities: Dict[str, float]) -> Optional[List[Dict[str, Any]]]:
    """3 education points for these probabilities, or None (keep the reviewed text)."""
    if not config.gemini_api_key():
        return None
    # No cache: every upload asks Gemini again, so the same photo gets freshly written text.
    key = tuple((name, round(p, 2)) for name, p in _ranked(class_probabilities))
    items = _generate(key)
    return list(items) if items else None

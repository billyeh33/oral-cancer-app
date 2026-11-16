"""衛教說明：依病灶知識庫（lesion_kb.py）逐一病灶、逐一欄位撰寫的結構化內容。

POST /education 會呼叫 lesion_report()：
  1. 依這次最可能的類別，從知識庫取出該類的病灶（例如 OPMD → 白斑、扁平苔癬、黏膜下纖維化）；
  2. 每個病灶只給它自己的手冊段落加上類別共用段落，請 Gemini 依固定欄位填寫，每個欄位附出處；
  3. 用規則檢查（欄位齊全、出處合法、高風險不寫延後就醫、不加原文沒有的安撫、機率寫法），
     不合格就重試，主要模型失敗兩次改用備援模型；
  4. 全部失敗時改用事先產生的 lesion_content.json（同樣的結構），頁面不會空白。

重新產生備援內容（在 backend 資料夾）：
    python -m rag.lesion_education --build
產生後請對照手冊逐欄檢查，再把檔案裡的 "reviewed" 改成 true。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from . import config
from .explain import CLASS_LABELS_ZH, _chunks_by_id, format_percent
from .lesion_kb import FIELDS, LESIONS, lesion_chunk_ids
from .links import find_links
from .personal_education import (
    HIGH_RISK,
    SECOND_CLASS_MIN,
    _CONNECTIVES,
    _DELAY_WORDS,
    _REASSURANCE,
    _fallback_model,
    _passage_text,
    _tidy,
)
from .retriever import Passage, passage_from_payload

LOGGER = logging.getLogger("oral_lesion_screening.rag")
CONTENT_PATH = config.DATA_DIR / "lesion_content.json"

try:  # backend/labels.py
    from labels import RISK_LEVELS
except ImportError:  # pragma: no cover
    RISK_LEVELS = {"Normal": "低風險", "Benign": "中低風險", "OPMD": "中高風險", "Oral Cancer": "高風險"}

FIELD_KEYS = [f["key"] for f in FIELDS]
# 官方「破斑硬突腫」的「破」就是「破皮超過兩週未癒合」，是症狀的定義而不是叫人等兩週，檢查延後字眼時先拿掉。
# 病灶欄位用的延後字眼：「觀察」本身不擋（自己可以留意就是在講觀察什麼），只擋「先觀察」「持續觀察」這類說法。
_DELAY_LESION = re.compile(_DELAY_WORDS.pattern.replace("|觀察", "") + r"|(先|持續|繼續|再|多)觀察")
_SYMPTOM_DEFINITION = re.compile(r"(口腔黏膜)?破皮(已經)?超過\s*[兩二2]\s*(週|星期|個星期)(仍|都|還)?(沒有|未)癒合")
REQUIRED = {f["key"] for f in FIELDS if f["required"]}


class FieldOut(BaseModel):
    text: str
    cited: List[int]


class LesionOut(BaseModel):
    id: str
    what: FieldOut
    cause: FieldOut
    cancer_risk: FieldOut
    self_check: FieldOut
    daily_care: FieldOut


class ReportOut(BaseModel):
    intro: str
    lesions: List[LesionOut]


SYSTEM_INSTRUCTION = """
你是台灣口腔健康衛教網站的編輯。使用者剛拿到 AI 篩檢結果，你要依照使用者訊息中各病灶的「參考資料」，為結果頁的「衛教說明」填寫一份結構化內容。

請輸出 JSON：
- intro：60～160 字，用「你」稱呼使用者，開頭不要打招呼。說明這次結果最可能的類別與機率（照訊息裡的寫法，例如「約 87%」），再說明這一類包含下面幾種病灶，AI 只看照片無法分辨是哪一種，可以對照看看，最後要由醫師檢查確認。如果訊息裡有「第二可能」，也要提到。如果只有一個病灶（例如健康的口腔黏膜），不要寫「這一類包含」，直接說明這個結果代表什麼、下面整理了相關的衛教重點。
- lesions：照訊息裡病灶的順序，每個病灶一筆，id 照抄訊息裡的 id。每筆有五個欄位，每個欄位都是 {text, cited}：
  - what（這是什麼）：外觀、常發生的位置、摸起來或感覺起來怎樣
  - cause（常見原因）：原文提到的成因或相關習慣、疾病
  - cancer_risk（跟口腔癌的關係）：會不會轉變成口腔癌、風險高低，原文怎麼說就怎麼寫
  - self_check（自己可以留意）：可以自己看到或感覺到的特徵，例如會不會痛、擦不擦得掉
  - daily_care（生活上可以怎麼做）：戒除菸酒檳榔、口腔清潔、不要自行塗藥等原文提到的做法
  text 寫 20～110 字。cited 是這個欄位用到的參考資料編號，1～3 個，只能用這個病灶底下列出的編號。
  cause、self_check 如果參考資料完全沒有提到，text 留空字串、cited 給空陣列，不要自己編。what、daily_care 一定要寫，cancer_risk 除非參考資料完全沒提到也要寫。

規則：
1. 只能使用參考資料裡的內容，不可加入參考資料沒有的醫療資訊或數字，也不要加上「不用擔心」「不需恐慌」這類原文沒有的安撫或評價。
2. 不可說使用者一定是某種病灶，不可診斷，不提供藥物、劑量或治療方式，不寫看哪一科、多久內就醫（另一個區塊會寫）。
3. 結果為「口腔潛在惡性疾患（癌前病變）」或「疑似口腔癌病灶」時，不可寫「兩星期」「會自己好」「自行癒合」「注意變化」「觀察」等可能讓人延後就醫的內容，也不可寫「每半年」「每三個月」這類追蹤間隔。
4. 不要假設使用者有吸菸、喝酒、嚼檳榔的習慣，需要提到時寫成「如果有……」。
5. 內文不要出現「參考資料」「資料中」這類字，要說的話寫「衛教手冊」。原文沒有提到的就不寫，不要寫「沒有提到」。
6. 繁體中文、台灣用語、語氣溫和口語，不用「此外」「因此」「總之」這類轉折詞，純文字，不用 Markdown，不寫免責聲明。
""".strip()


def _ranked(class_probabilities: Dict[str, float]) -> List[Tuple[str, float]]:
    return sorted(class_probabilities.items(), key=lambda item: item[1], reverse=True)


def _passages(prediction: str) -> Tuple[List[Passage], Dict[str, List[int]]]:
    """所有要給模型的段落（全域編號），以及每個病灶可以引用的編號。"""
    chunks = _chunks_by_id()
    order: List[str] = []
    allowed: Dict[str, List[int]] = {}
    for lesion in LESIONS[prediction]:
        ids = [cid for cid in lesion_chunk_ids(prediction, lesion) if cid in chunks]
        for cid in ids:
            if cid not in order:
                order.append(cid)
        allowed[lesion["id"]] = [order.index(cid) + 1 for cid in ids]
    return [passage_from_payload(chunks[cid]) for cid in order], allowed


def _prompt(ranked: List[Tuple[str, float]], second: Optional[str], passages: List[Passage],
            allowed: Dict[str, List[int]]) -> str:
    top, top_p = ranked[0]
    high_risk = top in HIGH_RISK or second in HIGH_RISK
    lines = [f"這次的 AI 篩檢結果：最可能為「{CLASS_LABELS_ZH[top]}」，{format_percent(top_p)}，風險分級為{RISK_LEVELS[top]}。"]
    if second:
        lines.append(f"第二可能：「{CLASS_LABELS_ZH[second]}」，{format_percent(dict(ranked)[second])}。")
    lines.append("\n參考資料：")
    for n, p in enumerate(passages, start=1):
        lines.append(f"[{n}] 第 {p.page} 頁" + (f"｜{p.title}" if p.title else "") + f"\n{_passage_text(p.text, high_risk)}\n")
    lines.append("要填寫的病灶：")
    for lesion in LESIONS[top]:
        nums = "、".join(str(n) for n in allowed[lesion["id"]])
        lines.append(f"- id: {lesion['id']}｜{lesion['name']}（{lesion['en']}）｜可引用的參考資料：{nums}")
        if lesion.get("hint"):
            lines.append(f"  寫法提示：{lesion['hint']}")
    return "\n".join(lines)


def _problems(top: str, intro_high_risk: bool, output: ReportOut, allowed: Dict[str, List[int]]) -> List[str]:
    problems: List[str] = []
    by_id = {lesion["id"]: lesion for lesion in LESIONS[top]}
    expected = [lesion["id"] for lesion in LESIONS[top]]
    if [lesion.id for lesion in output.lesions] != expected:
        return [f"lesions {[lesion.id for lesion in output.lesions]} != {expected}"]
    texts = [("intro", _tidy(output.intro))]
    if not 30 <= len(output.intro) <= 220 or "%" not in _tidy(output.intro):
        problems.append("intro")
    for lesion in output.lesions:
        for key in FIELD_KEYS:
            field: FieldOut = getattr(lesion, key)
            text = _tidy(field.text)
            if not text:
                if key in REQUIRED and key not in by_id[lesion.id].get("optional", []):
                    problems.append(f"{lesion.id}.{key} empty")
                continue
            if not 10 <= len(text) <= 160:
                problems.append(f"{lesion.id}.{key} length {len(text)}")
            if not 1 <= len(field.cited) <= 4 or any(n not in allowed[lesion.id] for n in field.cited):
                problems.append(f"{lesion.id}.{key} cited {field.cited}")
            texts.append((f"{lesion.id}.{key}", text))
    lesion_high_risk = top in HIGH_RISK
    for where, text in texts:
        cleaned = _SYMPTOM_DEFINITION.sub("", text)
        # 開頭那段也看第二可能（例如良性 80%、OPMD 12%），病灶欄位只看最可能的類別。
        if where == "intro" and intro_high_risk and _DELAY_WORDS.search(cleaned):
            problems.append(f"{where} delay wording")
        if where != "intro" and lesion_high_risk and _DELAY_LESION.search(cleaned):
            problems.append(f"{where} delay wording")
        if _REASSURANCE.search(text):
            problems.append(f"{where} reassurance")
        if _CONNECTIVES.search(text):
            problems.append(f"{where} connective")
        if re.search(r"百分之|[一二三四五六七八九十]\s*%", text):
            problems.append(f"{where} percent wording")
        if re.search(r"參考資料|資料中|未提及|沒有提到", text):
            problems.append(f"{where} meta wording")
    return problems


def _write(prompt: str, model: str) -> ReportOut:
    from google.genai import types

    from .answer import _gemini_client

    response = _gemini_client(config.gemini_api_key()).models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.6,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=ReportOut,
        ),
    )
    return ReportOut.model_validate_json(getattr(response, "text", "") or "")


def _render(top: str, output: ReportOut, passages: List[Passage]) -> Dict[str, Any]:
    by_id = {lesion["id"]: lesion for lesion in LESIONS[top]}
    lesions = []
    for lesion in output.lesions:
        info = by_id[lesion.id]
        fields = []
        for spec in FIELDS:
            field: FieldOut = getattr(lesion, spec["key"])
            text = _tidy(field.text)
            if not text:
                continue
            fields.append({
                "key": spec["key"],
                "label": info.get("labels", {}).get(spec["key"], spec["label"]),
                "text": text,
                "sources": [passages[n - 1].to_dict() for n in list(dict.fromkeys(field.cited))[:3]],
                "links": find_links(text),
            })
        lesions.append({"id": info["id"], "name": info["name"], "en": info["en"], "fields": fields})
    return {"intro": _tidy(output.intro), "lesions": lesions}


def generate(class_probabilities: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """結構化衛教內容（intro + 每個病灶的欄位），或 None。"""
    if not config.gemini_api_key():
        return None
    ranked = [(name, round(p, 2)) for name, p in _ranked(class_probabilities)]
    top = ranked[0][0]
    second = ranked[1][0] if ranked[1][1] >= SECOND_CLASS_MIN else None
    high_risk = top in HIGH_RISK or second in HIGH_RISK
    passages, allowed = _passages(top)
    prompt = _prompt(ranked, second, passages, allowed)
    started = time.perf_counter()
    for attempt, model in enumerate([config.gemini_chat_model()] * 2 + [_fallback_model()] * 2):
        try:
            output = _write(prompt, model)
        except Exception as exc:
            LOGGER.warning("Lesion report: %s failed (%s), attempt %d.", model, getattr(exc, "code", type(exc).__name__), attempt + 1)
            time.sleep(1.0)
            continue
        problems = _problems(top, high_risk, output, allowed)
        if problems:
            LOGGER.warning("Lesion report: %s rejected (%s), attempt %d.", model, "; ".join(problems[:4]), attempt + 1)
            continue
        LOGGER.info("Lesion report: written by %s in %.1fs.", model, time.perf_counter() - started)
        return _render(top, output, passages)
    return None


def _stored() -> Dict[str, Any]:
    if not CONTENT_PATH.exists():
        return {}
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def stored_report(class_probabilities: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """事先產生的同結構內容（給 /predict 先顯示，以及 Gemini 失敗時用）。"""
    content = _stored()
    ranked = _ranked(class_probabilities)
    top, top_p = ranked[0]
    entry = content.get("classes", {}).get(top)
    if not entry:
        return None
    names = "、".join(lesion["name"] for lesion in LESIONS[top])
    if len(LESIONS[top]) > 1:
        intro = (f"這次的 AI 篩檢結果最可能為「{CLASS_LABELS_ZH[top]}」，{format_percent(top_p)}。"
                 f"這一類包含{names}，AI 只看照片無法分辨是哪一種，可以對照下面的說明，實際情況要由醫師檢查確認。")
    else:
        intro = (f"這次的 AI 篩檢結果最可能為「{CLASS_LABELS_ZH[top]}」，{format_percent(top_p)}。"
                 "下面整理了相關的衛教重點，實際情況要由醫師檢查確認。")
    return {"intro": intro, "lesions": entry["lesions"], "reviewed": bool(content.get("reviewed"))}


def main() -> int:
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="regenerate rag/data/lesion_content.json")
    parser.add_argument("--only", choices=sorted(LESIONS), action="append")
    args = parser.parse_args()
    if not args.build:
        parser.print_help()
        return 0
    load_dotenv(config.BACKEND_DIR / ".env")
    content = _stored()
    classes = content.get("classes", {})
    failed = []
    for name in args.only or list(LESIONS):
        probs = {c: (1.0 if c == name else 0.0) for c in LESIONS}
        report = generate(probs)
        if report is None:
            failed.append(name)
            print(f"== {name}: FAILED, kept the previous content")
            continue
        classes[name] = {"lesions": report["lesions"]}
        print(f"== {name}")
        for lesion in report["lesions"]:
            print(f"  【{lesion['name']}】")
            for field in lesion["fields"]:
                print(f"    {field['label']}：{field['text']}  {[s['page'] for s in field['sources']]}")
    content = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": config.gemini_chat_model(),
        "reviewed": False,
        "classes": classes,
    }
    CONTENT_PATH.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {CONTENT_PATH.relative_to(config.BACKEND_DIR)}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

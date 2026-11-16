"""病灶知識庫（規則）：每個篩檢類別包含哪些病灶、每個病灶的衛教欄位、各自依據的手冊段落。

模型只分四類，所以一個類別下的病灶都會列出（例如 OPMD 會列白斑、扁平苔癬、黏膜下纖維化），
每個病灶都用同一套欄位寫，內容只能出自這個病灶自己的段落（chunk_ids）加上類別共用段落。
病灶清單依資料集的原始標籤（檔名）與手冊頁碼整理：
  良性：良性潰瘍（BenighUlcer）、念珠菌感染（Candidiasis）
  OPMD：白斑（Leukoplakia）、扁平苔癬（LichenPlanus）、黏膜下纖維化（OSF）
  口腔癌：手冊沒有口腔癌專章，改用口腔健康司與衛福部的口腔癌衛教原文（sources/口腔癌*.md）
"""

from __future__ import annotations

from typing import Dict, List, TypedDict


class Lesion(TypedDict, total=False):
    id: str
    name: str
    en: str
    chunk_ids: List[str]
    # 寫給模型的補充說明（這個病灶的欄位要怎麼寫）
    hint: str
    # 這個病灶要換掉的欄位名稱，例如口腔癌不適合寫「跟口腔癌的關係」
    labels: Dict[str, str]
    # 這個病灶可以留白的必填欄位（資料來源本來就沒寫，硬寫只會編造）
    optional: List[str]


# 每個病灶要寫的欄位（順序就是網頁上的順序）。required 的欄位不能空白。
FIELDS: List[Dict[str, object]] = [
    {"key": "what", "label": "這是什麼", "required": True,
     "hint": "外觀、常發生的位置、摸起來或感覺起來怎樣"},
    {"key": "cause", "label": "常見原因", "required": False,
     "hint": "原文提到的成因或相關習慣、疾病"},
    {"key": "cancer_risk", "label": "跟口腔癌的關係", "required": True,
     "hint": "會不會轉變成口腔癌、風險高低，原文怎麼說就怎麼寫"},
    {"key": "self_check", "label": "自己可以留意", "required": False,
     "hint": "可以自己看到或感覺到的特徵，例如會不會痛、擦不擦得掉、是否左右對稱"},
    {"key": "daily_care", "label": "生活上可以怎麼做", "required": True,
     "hint": "戒除菸酒檳榔、口腔清潔、不要自行塗藥等原文提到的做法"},
]

# 每個類別共用的段落（危險因子、迷思、處置流程），各病灶都可以引用。
SHARED_CHUNKS: Dict[str, List[str]] = {
    "Normal": ["handbook-p62-1", "oralcancer-lazypack-3", "oralcancer-dooh-2"],
    "Benign": ["handbook-p63-1", "handbook-p59-1"],
    "OPMD": ["handbook-p62-1", "flowchart-1", "oralcancer-dooh-5"],
    "Oral Cancer": ["handbook-p62-1", "oralcancer-dooh-6"],
}

LESIONS: Dict[str, List[Lesion]] = {
    "Normal": [
        {"id": "healthy_mucosa", "name": "健康的口腔黏膜", "en": "Normal mucosa",
         "chunk_ids": ["handbook-p08-1", "handbook-p09-1", "handbook-p10-1"],
         "hint": "what 用白話寫健康的口腔黏膜和牙齦看起來是什麼顏色、什麼樣子，讓使用者可以對照自己，不要列專有名詞。"
                 "self_check 寫刷牙時可以自己檢查「破斑硬突腫」。cancer_risk 寫目前未見明顯異常，但菸酒檳榔是口腔癌的危險因子，符合資格可以免費做口腔黏膜檢查。"},
    ],
    "Benign": [
        {"id": "ulcer", "name": "良性潰瘍（口腔破皮）", "en": "Benign ulcer",
         "chunk_ids": ["handbook-p37-1", "handbook-p47-1"]},
        {"id": "candidiasis", "name": "念珠菌感染", "en": "Candidiasis",
         "chunk_ids": ["handbook-p24-1", "handbook-p72-1"],
         "optional": ["cancer_risk"]},
    ],
    "OPMD": [
        {"id": "leukoplakia", "name": "白斑", "en": "Leukoplakia",
         "chunk_ids": ["handbook-p18-1", "handbook-p20-1"]},
        {"id": "lichen_planus", "name": "扁平苔癬", "en": "Oral lichen planus",
         "chunk_ids": ["handbook-p26-1", "handbook-p27-1"]},
        {"id": "osf", "name": "口腔黏膜下纖維化", "en": "Oral submucous fibrosis",
         "chunk_ids": ["handbook-p19-1"]},
    ],
    "Oral Cancer": [
        {"id": "suspected_cancer", "name": "疑似口腔癌病灶", "en": "Suspected oral cancer",
         "chunk_ids": ["oralcancer-dooh-1", "oralcancer-news-2", "oralcancer-news-3",
                       "oralcancer-lazypack-1", "oralcancer-lazypack-3", "oralcancer-dooh-5", "flowchart-2"],
         "labels": {"cancer_risk": "早期發現的重要性", "self_check": "自我檢查「破斑硬突腫」"},
         "hint": "what 寫口腔癌是什麼樣的癌症、好發族群與主要原因。cause 寫菸酒檳榔與各自的風險倍數。"
                 "cancer_risk 這欄改寫早期發現的重要性：確診要靠醫師切片檢查，早期與晚期的存活率差多少。"
                 "self_check 寫「破斑硬突腫」五項，可以刷牙時自己檢查。daily_care 寫戒檳榔、戒菸、戒酒與避免高溫或刺激性食物。"},
    ],
}


def lesion_chunk_ids(prediction: str, lesion: Lesion) -> List[str]:
    """這個病灶可以引用的段落：自己的段落在前，類別共用段落在後。"""
    return list(dict.fromkeys(lesion["chunk_ids"] + SHARED_CHUNKS[prediction]))

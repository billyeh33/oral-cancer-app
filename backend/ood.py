"""擋掉不是口腔照片的影像（X 光、風景、截圖等）。

分類模型只會在四類裡選一個，不管上傳什麼都會給出結果，例如頭顱 X 光會被判成「口腔潛在惡性疾患 75.8%」。
上傳的影像要通過兩項檢查才會給結果：

1. 顏色：口腔黏膜是紅、粉紅色，中央區域的紅粉色像素要至少 RED_MIN（X 光、圖表、QR code 幾乎是 0）。
2. 特徵距離：模型主幹的 768 維特徵，和 1450 張訓練影像中最像的 5 張比 cosine 距離，平均要小於 KNN_MAX。

門檻在 build_ood_reference.py 依驗證集設定（2026-11-22）：
驗證集 414 張誤擋 1 張、測試集 208 張與外部口腔癌 49 張都沒有被擋，46 張非口腔影像擋下 40 張（含 X 光）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

REFERENCE_PATH = Path(__file__).with_name("ood_reference.npz")
NOT_ORAL_MESSAGE = (
    "這張照片看起來不像口腔內部的照片，系統無法判讀。"
    "請張開嘴巴，在光線充足的地方拍攝口腔內部，再重新上傳。"
)


@lru_cache(maxsize=1)
def _reference():
    if not REFERENCE_PATH.exists():
        return None
    data = np.load(REFERENCE_PATH)
    feats = data["train_features"].astype(np.float32)
    return {
        "features": feats,  # 已經 L2 正規化
        "k": int(data["k"]),
        "knn_max": float(data["knn_max"]),
        "red_min": float(data["red_min"]),
    }


def red_fraction(image: Image.Image) -> float:
    """中央正方形區域裡紅、粉紅色像素的比例（色相 330°–40°、飽和度 > 0.18、亮度 > 0.15）。"""
    w, h = image.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    square = image.crop((left, top, left + side, top + side)).resize((128, 128))
    hsv = np.asarray(square.convert("HSV")).astype(np.float32)
    hue = hsv[..., 0] * 360 / 255
    sat = hsv[..., 1] / 255
    val = hsv[..., 2] / 255
    mask = ((hue >= 330) | (hue <= 40)) & (sat > 0.18) & (val > 0.15)
    return float(mask.mean())


def knn_distance(feature: np.ndarray) -> Optional[float]:
    ref = _reference()
    if ref is None:
        return None
    f = feature.astype(np.float32)
    f = f / (np.linalg.norm(f) + 1e-12)
    sims = ref["features"] @ f
    top = np.partition(sims, -ref["k"])[-ref["k"]:]
    return float(1.0 - top.mean())


def looks_like_oral_photo(image: Image.Image) -> bool:
    """第一關：顏色。沒有參考檔時一律放行。"""
    ref = _reference()
    if ref is None:
        return True
    return red_fraction(image) >= ref["red_min"]


def features_look_oral(feature: np.ndarray) -> bool:
    """第二關：特徵距離。沒有參考檔時一律放行。"""
    ref = _reference()
    distance = knn_distance(feature)
    if ref is None or distance is None:
        return True
    return distance <= ref["knn_max"]

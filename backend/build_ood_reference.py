"""產生 ood_reference.npz：訓練影像的特徵與兩個門檻（給 ood.py 用）。

用法：python build_ood_reference.py /path/to/classification_決策樹
資料夾裡要有 train/ 與 valid/，各有 Normal、Benign、OPMD、Oral Cancer 子資料夾。
門檻：特徵距離取驗證集的最大值再加一點餘裕（0.72），顏色取 0.02（訓練集只有 1 張低於此值）。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

from ood import red_fraction
from predict import eval_transform, load_trained_model

CLASSES = ["Normal", "Benign", "OPMD", "Oral Cancer"]
K = 5
KNN_MAX = 0.72
RED_MIN = 0.02


def features(model, device, paths):
    out = []
    for path in paths:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            x = eval_transform(im).unsqueeze(0).to(device)
        with torch.inference_mode():
            out.append(model.backbone(x).flatten(1)[0].cpu().numpy())
    f = np.stack(out)
    return f / np.linalg.norm(f, axis=1, keepdims=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--weights", type=Path, default=Path(__file__).with_name("best_hierarchical_convnext_mac.pth"))
    args = parser.parse_args()
    model, device = load_trained_model(args.weights)

    def split_paths(split):
        return [p for c in CLASSES for p in sorted((args.data_dir / split / c).glob("*")) if p.is_file()]

    train = features(model, device, split_paths("train"))
    valid_paths = split_paths("valid")
    valid = features(model, device, valid_paths)
    sims = valid @ train.T
    knn = 1 - np.sort(sims, axis=1)[:, -K:].mean(1)
    reds = np.array([red_fraction(ImageOps.exif_transpose(Image.open(p)).convert("RGB")) for p in valid_paths])
    print(f"驗證集 {len(valid)} 張：特徵距離最大 {knn.max():.3f}，門檻 {KNN_MAX}，"
          f"被擋 {int(((knn > KNN_MAX) | (reds < RED_MIN)).sum())} 張")
    np.savez_compressed(
        Path(__file__).with_name("ood_reference.npz"),
        train_features=train.astype(np.float16), k=K, knn_max=KNN_MAX, red_min=RED_MIN,
    )


if __name__ == "__main__":
    main()

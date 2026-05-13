from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import torch
from PIL import Image
from torchvision import transforms

from model import DEFAULT_DROPOUT, HierarchicalConvNeXt


IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]

CLASS_NAMES = ("Normal", "Benign", "OPMD", "Oral Cancer")
RISK_LEVELS = {
    "Normal": "低風險",
    "Benign": "中低風險",
    "OPMD": "中高風險",
    "Oral Cancer": "高風險",
}

eval_transform = transforms.Compose(
    [
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ]
)


def select_device() -> torch.device:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu" and hasattr(torch.backends, "mps"):
        if torch.backends.mps.is_available():
            return torch.device("mps")
    return device


def _load_state_dict(weights_path: Path, device: torch.device) -> Dict[str, Any]:
    try:
        state_dict = torch.load(weights_path, map_location=device, weights_only=True)
    except TypeError:
        state_dict = torch.load(weights_path, map_location=device)

    if not isinstance(state_dict, dict):
        raise ValueError("Unsupported checkpoint format: expected a state_dict mapping.")
    return state_dict


def load_trained_model(
    weights_path: str | Path,
    device: torch.device | None = None,
) -> Tuple[HierarchicalConvNeXt, torch.device]:
    resolved_path = Path(weights_path).expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Model weights not found: {resolved_path}")

    inference_device = device or select_device()
    model = HierarchicalConvNeXt(
        dropout=DEFAULT_DROPOUT,
        initialize_from_imagenet=False,
    )
    state_dict = _load_state_dict(resolved_path, inference_device)
    model.load_state_dict(state_dict, strict=True)
    model.to(inference_device)
    model.eval()
    return model, inference_device


def _round_probability(value: torch.Tensor | float) -> float:
    return float(value.item() if isinstance(value, torch.Tensor) else value)


def predict_image(
    image: Image.Image,
    model: HierarchicalConvNeXt,
    device: torch.device,
) -> Dict[str, Any]:
    rgb_image = image.convert("RGB")
    input_tensor = eval_transform(rgb_image).unsqueeze(0).to(device)

    with torch.inference_mode():
        logit_s1, logit_s2, logit_s3 = model(input_tensor)
        p_s1 = torch.softmax(logit_s1, dim=1)[0].detach().cpu()
        p_s2 = torch.softmax(logit_s2, dim=1)[0].detach().cpu()
        p_s3 = torch.softmax(logit_s3, dim=1)[0].detach().cpu()

    normal_prob = p_s1[0]
    abnormal_prob = p_s1[1]
    benign_prob = abnormal_prob * p_s2[0]
    malignant_prob = abnormal_prob * p_s2[1]
    opmd_prob = malignant_prob * p_s3[0]
    oral_cancer_prob = malignant_prob * p_s3[1]

    class_probabilities = {
        "Normal": _round_probability(normal_prob),
        "Benign": _round_probability(benign_prob),
        "OPMD": _round_probability(opmd_prob),
        "Oral Cancer": _round_probability(oral_cancer_prob),
    }
    prediction = max(class_probabilities, key=class_probabilities.get)
    confidence = class_probabilities[prediction]

    return {
        "prediction": prediction,
        "confidence": confidence,
        "risk_level": RISK_LEVELS[prediction],
        "class_probabilities": class_probabilities,
        "stage_probabilities": {
            "stage_1": {
                "Normal": _round_probability(p_s1[0]),
                "Abnormal": _round_probability(p_s1[1]),
            },
            "stage_2": {
                "Benign": _round_probability(p_s2[0]),
                "Malignant": _round_probability(p_s2[1]),
            },
            "stage_3": {
                "OPMD": _round_probability(p_s3[0]),
                "Oral Cancer": _round_probability(p_s3[1]),
            },
        },
    }

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from predict import load_trained_model, predict_image


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run local CNN inference for one oral image."
    )
    parser.add_argument("image_path", type=Path, help="Path to jpg, jpeg, or png file.")
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path(__file__).with_name("best_hierarchical_convnext_mac.pth"),
        help="Path to the trained .pth checkpoint.",
    )
    args = parser.parse_args()

    if not args.image_path.exists():
        raise FileNotFoundError(f"Image not found: {args.image_path}")

    model, device = load_trained_model(args.weights)
    with Image.open(args.image_path) as image:
        result = predict_image(image, model, device)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

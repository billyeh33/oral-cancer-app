from __future__ import annotations

import logging
import os
from threading import Lock
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError


load_dotenv()

LOGGER = logging.getLogger("oral_lesion_screening")
logging.basicConfig(level=logging.INFO)

MODEL_PATH = Path(__file__).with_name("best_hierarchical_convnext_mac.pth")
MODEL_LOCK = Lock()
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
DISCLAIMER = (
    "本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、"
    "病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，"
    "請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。"
)


def _fallback_explanation(
    prediction: str,
    risk_level: str,
) -> str:
    return (
        "目前尚未啟用 LLM 說明功能。本系統的 CNN 模型判定此影像為 "
        f"{prediction}，風險等級為 {risk_level}。此結果僅供初步參考，"
        "不能取代醫師診斷。"
    )


def generate_explanation(
    prediction: str,
    confidence: float,
    risk_level: str,
    class_probabilities: Dict[str, float],
) -> str:
    fallback = _fallback_explanation(prediction, risk_level)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        return fallback

    prompt = f"""
你是一位醫療衛教說明助手，請使用繁體中文，根據下列 AI 初步風險篩檢文字結果，
產生一段保守、清楚、適合一般民眾理解的衛教說明。

限制：
1. 不可診斷疾病。
2. 不可說「你有癌症」或「你沒有癌症」。
3. 不可把結果描述成確診。
4. 必須說明這只是 AI 初步風險篩檢，不能取代醫師診斷、病理切片或正式醫療建議。
5. 若風險等級為高風險或中高風險，請建議盡快至牙科、口腔外科或耳鼻喉科檢查。
6. 若使用者有口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，也要提醒就醫。
7. 不要描述影像內容，因為你沒有看到圖片。

CNN 輸出：
- prediction: {prediction}
- confidence: {confidence:.4f}
- risk_level: {risk_level}
- class_probabilities: {class_probabilities}
""".strip()

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = getattr(response, "text", "")
        return text.strip() or fallback
    except Exception:
        LOGGER.exception("Gemini explanation generation failed; using fallback.")
        return fallback


def _parse_cors_origins() -> list[str]:
    raw_value = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if raw_value == "*":
        return ["*"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.model = None
    app.state.device = None
    app.state.model_load_error = None
    yield


def get_model() -> tuple[Any, Any]:
    if app.state.model is not None and app.state.device is not None:
        return app.state.model, app.state.device

    with MODEL_LOCK:
        if app.state.model is not None and app.state.device is not None:
            return app.state.model, app.state.device
        try:
            from predict import load_trained_model

            model, device = load_trained_model(MODEL_PATH)
            app.state.model = model
            app.state.device = device
            app.state.model_load_error = None
            LOGGER.info("Model loaded on device: %s", device)
            return model, device
        except Exception as exc:
            app.state.model_load_error = str(exc)
            LOGGER.exception("Model loading failed.")
            raise HTTPException(
                status_code=503,
                detail="Model is not available. Please check backend logs.",
            ) from exc


app = FastAPI(
    title="Oral Lesion Screening API",
    version="0.1.0",
    description="Research prototype for preliminary oral lesion image risk screening.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> Dict[str, str]:
    return {
        "status": "ok",
        "service": "oral-lesion-screening-api",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": app.state.model is not None,
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)) -> Dict[str, Any]:
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only jpg, jpeg, and png images are supported.",
        )

    image_bytes = await file.read()
    await file.close()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    try:
        with Image.open(BytesIO(image_bytes)) as uploaded_image:
            image = uploaded_image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400,
            detail="Unable to read the uploaded image.",
        )

    model, device = get_model()
    from predict import predict_image

    result = predict_image(image, model, device)
    result["explanation"] = generate_explanation(
        prediction=result["prediction"],
        confidence=result["confidence"],
        risk_level=result["risk_level"],
        class_probabilities=result["class_probabilities"],
    )
    result["disclaimer"] = DISCLAIMER
    return result

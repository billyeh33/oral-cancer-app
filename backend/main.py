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
GEMINI_KEY_ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
INVALID_GEMINI_KEYS = {
    "",
    "your_gemini_api_key_here",
    "your_google_api_key_here",
}
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
        f"AI 初步風險篩檢結果顯示，此影像的分類為 {prediction}，"
        f"風險等級為 {risk_level}。此結果僅供衛教與就醫溝通參考，"
        "不能取代醫師診斷、病理切片或正式醫療建議。"
    )


def _fallback_care_guidance(prediction: str, risk_level: str) -> str:
    if prediction == "Normal":
        return (
            "就診建議：本次 AI 初步風險篩檢未顯示明顯高風險特徵，但仍不能排除所有口腔疾病。"
            "若口腔潰瘍、白斑、紅斑、腫塊、疼痛或出血持續超過兩週，或反覆出現，"
            "建議安排牙科、口腔外科或耳鼻喉科檢查。"
        )
    if prediction == "Benign":
        return (
            "就診建議：目前屬於中低風險初步分級，建議安排牙科或口腔外科門診評估，"
            "由醫師確認是否需要追蹤或進一步檢查。若病灶快速變大、出血、疼痛加劇，"
            "或持續超過兩週，請提早就醫。"
        )
    if prediction == "OPMD":
        return (
            "就診建議：目前屬於中高風險初步分級，建議盡快安排口腔外科、牙科或耳鼻喉科檢查。"
            "就診時可帶著影像、病灶出現時間、是否疼痛或出血、是否有菸酒或檳榔使用史等資訊，"
            "讓醫師判斷是否需要進一步檢查。"
        )
    return (
        "就診建議：目前屬於高風險初步分級，請盡快至口腔外科、牙科或耳鼻喉科就醫檢查。"
        "此結果不是正式醫療判定，但不建議延後處理；是否需要病理切片或其他檢查，應由醫師現場評估。"
    )


def get_gemini_api_key() -> str:
    for env_name in GEMINI_KEY_ENV_NAMES:
        api_key = os.getenv(env_name, "").strip()
        if api_key and api_key not in INVALID_GEMINI_KEYS:
            return api_key
    return ""


def is_llm_configured() -> bool:
    return bool(get_gemini_api_key())


def generate_explanation(
    prediction: str,
    confidence: float,
    risk_level: str,
    class_probabilities: Dict[str, float],
) -> str:
    fallback = _fallback_explanation(prediction, risk_level)
    api_key = get_gemini_api_key()
    if not api_key:
        return fallback

    prompt = f"""
你是一位醫療衛教說明助手，請使用繁體中文，根據下列 AI 初步風險篩檢文字結果，
產生一段保守、清楚、適合一般民眾理解的衛教說明。

限制：
1. 不可診斷疾病。
2. 不可用罹患或未罹患等斷定語氣描述癌症風險。
3. 不可把結果描述成正式醫療判定。
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


def generate_care_guidance(
    prediction: str,
    confidence: float,
    risk_level: str,
    class_probabilities: Dict[str, float],
) -> str:
    fallback = _fallback_care_guidance(prediction, risk_level)
    api_key = get_gemini_api_key()
    if not api_key:
        return fallback

    prompt = f"""
你是一位醫療衛教與就診分流說明助手。請根據 CNN 的文字結果，使用繁體中文產生一段保守的就診建議。

嚴格限制：
1. 不可診斷疾病。
2. 不可用罹患或未罹患等斷定語氣描述癌症風險。
3. 不可提供治療處方、用藥劑量或保證預後。
4. 不可讀取或推論圖片內容，因為你沒有看到圖片。
5. 必須說明這只是 AI 初步風險篩檢，不取代醫師診斷、病理切片或正式醫療建議。
6. 建議內容限於：看哪一科、急迫性、就診前可準備的資訊、哪些症狀應提早就醫。
7. 若風險等級為中高風險或高風險，請建議盡快至口腔外科、牙科或耳鼻喉科檢查。
8. 若口腔潰瘍、白斑、紅斑、腫塊、疼痛或出血持續超過兩週，請提醒就醫檢查。

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
        LOGGER.exception("Gemini care guidance generation failed; using fallback.")
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
        "llm_configured": is_llm_configured(),
        "llm_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
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
    result["care_guidance"] = generate_care_guidance(
        prediction=result["prediction"],
        confidence=result["confidence"],
        risk_level=result["risk_level"],
        class_probabilities=result["class_probabilities"],
    )
    result["disclaimer"] = DISCLAIMER
    return result

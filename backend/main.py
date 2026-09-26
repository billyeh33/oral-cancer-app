from __future__ import annotations

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from typing import Any, AsyncIterator, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ValidationError, field_validator

from labels import CLASS_NAMES, RISK_LEVELS


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
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
LLM_TIMEOUT_MS = 20_000
# Top-two probabilities closer than this are reported to the LLM as an uncertain call.
CLOSE_CALL_MARGIN = 0.25
DISCLAIMER = (
    "本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、"
    "病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，"
    "請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。"
)
CLASS_LABELS_ZH = {
    "Normal": "未見明顯異常",
    "Benign": "良性病灶",
    "OPMD": "口腔潛在惡性疾患（癌前病變）",
    "Oral Cancer": "疑似口腔癌病灶",
}
ADVICE_SYSTEM_INSTRUCTION = """
你是台灣口腔健康衛教網站的說明助手。使用者上傳了一張口腔照片，影像 AI 已經算出初步風險篩檢結果；你只會收到這些數字，沒有看到照片。

請輸出 JSON：
- explanation：70～140 字的一段話，用白話說明這次結果代表什麼：最可能的類別與大約機率。若標示「前兩名接近：是」，要說明 AI 在這兩類之間難以明確區分，所以更需要由醫師檢查確認。
- care_steps：2～3 點具體的下一步，每點 15～45 字，內容只能是：建議看哪一科、多快去看、就診時可以帶或告訴醫師的資訊。

寫作規則：
1. 繁體中文、台灣用語，語氣溫和清楚，不嚇人也不輕描淡寫。
2. 不可診斷，不可用「罹患」「確診」「一定是」「沒事」「健康」等斷定說法；機率一律寫成「約 X%」，不要說「接近 100%」「幾乎確定」。
3. 完全不寫免責聲明，也不寫「僅供參考」「不能取代醫師判斷」這類句子（網頁已固定顯示）；不自我介紹，不用「根據您提供的資料」之類的開場白。
4. 不出現「CNN」「模型」「信心指數」「JSON」等技術用語，統一稱為「AI 篩檢」。
5. 不描述照片內容，不提供治療、用藥或預後。
6. 不要假設使用者有吸菸、喝酒、嚼檳榔等習慣或任何症狀；需要提到時寫成「如果有……」。
7. 純文字，不用 Markdown 符號，care_steps 每點不要加編號。
8. 類別一律使用這些名稱：未見明顯異常、良性病灶、口腔潛在惡性疾患（癌前病變）、疑似口腔癌病灶。
""".strip()


class AdviceOutput(BaseModel):
    explanation: str
    care_steps: List[str]


class ExplainRequest(BaseModel):
    class_probabilities: Dict[str, float]

    @field_validator("class_probabilities")
    @classmethod
    def _check_probabilities(cls, value: Dict[str, float]) -> Dict[str, float]:
        if set(value) != set(CLASS_NAMES):
            raise ValueError(
                f"class_probabilities must contain exactly: {', '.join(CLASS_NAMES)}."
            )
        if any(not 0.0 <= probability <= 1.0 for probability in value.values()):
            raise ValueError("Each probability must be between 0 and 1.")
        if abs(sum(value.values()) - 1.0) > 0.05:
            raise ValueError("Probabilities must sum to 1.")
        return value


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


def get_llm_model_name() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def is_llm_configured() -> bool:
    return bool(get_gemini_api_key())


def _format_percent(probability: float) -> str:
    if probability < 0.01:
        return "不到 1%"
    return f"{round(probability * 100)}%"


def _build_advice_prompt(class_probabilities: Dict[str, float]) -> str:
    ranked = sorted(class_probabilities.items(), key=lambda item: item[1], reverse=True)
    (top_name, top_probability), (second_name, second_probability) = ranked[:2]
    others = "、".join(
        f"{CLASS_LABELS_ZH[name]} {_format_percent(probability)}"
        for name, probability in ranked[2:]
    )
    is_close_call = top_probability - second_probability < CLOSE_CALL_MARGIN
    return "\n".join(
        [
            "篩檢結果：",
            f"- 最可能：{CLASS_LABELS_ZH[top_name]}，{_format_percent(top_probability)}",
            f"- 第二：{CLASS_LABELS_ZH[second_name]}，{_format_percent(second_probability)}",
            f"- 其他：{others}",
            f"- 風險分級：{RISK_LEVELS[top_name]}",
            f"- 前兩名接近：{'是' if is_close_call else '否'}",
        ]
    )


def _clean_advice_line(text: str) -> str:
    without_marker = re.sub(r"^\s*(?:\d+\s*[.、)）]|[-•*])\s*", "", text)
    return without_marker.replace("**", "").strip()


def _parse_advice(raw_text: str) -> Dict[str, str] | None:
    try:
        advice = AdviceOutput.model_validate_json(raw_text)
    except ValidationError:
        return None

    explanation = _clean_advice_line(advice.explanation)
    steps = [_clean_advice_line(step) for step in advice.care_steps]
    steps = [step for step in steps if step]
    if not 20 <= len(explanation) <= 400:
        return None
    if not 1 <= len(steps) <= 5 or any(len(step) > 120 for step in steps):
        return None

    return {
        "explanation": explanation,
        "care_guidance": "\n".join(
            f"{number}. {step}" for number, step in enumerate(steps, start=1)
        ),
    }


@lru_cache(maxsize=1)
def _gemini_client(api_key: str) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=LLM_TIMEOUT_MS),
    )


def generate_advice(class_probabilities: Dict[str, float]) -> Dict[str, str]:
    prediction = max(class_probabilities, key=class_probabilities.get)
    risk_level = RISK_LEVELS[prediction]
    fallback = {
        "explanation": _fallback_explanation(prediction, risk_level),
        "care_guidance": _fallback_care_guidance(prediction, risk_level),
        "source": "fallback",
    }
    api_key = get_gemini_api_key()
    if not api_key:
        return fallback

    from google.genai import types

    model_name = get_llm_model_name()
    config = types.GenerateContentConfig(
        system_instruction=ADVICE_SYSTEM_INSTRUCTION,
        temperature=0.3,
        max_output_tokens=1024,
        response_mime_type="application/json",
        response_schema=AdviceOutput,
        # 2.5 Flash thinks before answering by default, which mostly adds latency
        # to a short templated task like this one.
        thinking_config=(
            types.ThinkingConfig(thinking_budget=0) if "2.5-flash" in model_name else None
        ),
    )
    started = time.perf_counter()
    try:
        response = _gemini_client(api_key).models.generate_content(
            model=model_name,
            contents=_build_advice_prompt(class_probabilities),
            config=config,
        )
        advice = _parse_advice(getattr(response, "text", "") or "")
    except Exception:
        LOGGER.exception("Gemini advice generation failed; using fallback.")
        return fallback

    elapsed = time.perf_counter() - started
    if advice is None:
        LOGGER.warning("Gemini advice was unusable after %.1fs; using fallback.", elapsed)
        return fallback
    LOGGER.info("Gemini advice generated in %.1fs with %s.", elapsed, model_name)
    return {**advice, "source": "llm"}


def _parse_cors_origins() -> list[str]:
    raw_value = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    if raw_value == "*":
        return ["*"]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def _preload_model() -> None:
    try:
        get_model()
    except Exception:
        # get_model already logged the failure; /predict retries on demand.
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.model = None
    app.state.device = None
    app.state.model_load_error = None
    # Load the weights in the background: the port opens right away, and the first
    # request after a restart no longer waits for the model to load.
    Thread(target=_preload_model, name="model-preload", daemon=True).start()
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
    version="0.2.0",
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
        "llm_model": get_llm_model_name(),
        "commit": os.getenv("RENDER_GIT_COMMIT", "local")[:7],
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

    # Loading and inference are CPU-bound; running them in the threadpool keeps
    # /health and /explain responsive in the meantime.
    model, device = await run_in_threadpool(get_model)
    from predict import predict_image

    result = await run_in_threadpool(predict_image, image, model, device)
    # The LLM-written texts come from /explain so the CNN result can be shown
    # immediately; these fixed texts are what clients see if they skip it.
    result["explanation"] = _fallback_explanation(result["prediction"], result["risk_level"])
    result["care_guidance"] = _fallback_care_guidance(
        result["prediction"], result["risk_level"]
    )
    result["disclaimer"] = DISCLAIMER
    return result


@app.post("/explain")
def explain(request: ExplainRequest) -> Dict[str, str]:
    return generate_advice(request.class_probabilities)

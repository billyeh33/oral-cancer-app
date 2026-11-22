from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from typing import Any, AsyncIterator, Dict, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError

try:  # iPhone 照片預設是 HEIC，Pillow 要靠 pillow-heif 才讀得到
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass
from pydantic import BaseModel, field_validator

from labels import CLASS_NAMES
from rag import answer_question, build_report, get_retriever
from rag.lesion_education import generate as generate_lesion_report, stored_report as stored_lesion_report
from rag import config as rag_config


load_dotenv()

LOGGER = logging.getLogger("oral_lesion_screening")
logging.basicConfig(level=logging.INFO)

MODEL_PATH = Path(__file__).with_name("best_hierarchical_convnext_mac.pth")
MODEL_LOCK = Lock()
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif"}
# 有些瀏覽器不認得 HEIC，會送空白或 application/octet-stream，這時改看副檔名。
ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".heic", ".heif")
MAX_IMAGE_SIDE = 1600
QUESTION_MAX_CHARS = 300
DISCLAIMER = (
    "本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、"
    "病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，"
    "請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。"
)


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


class AskRequest(BaseModel):
    question: str
    # Optional screening result, so answers can focus on what the user was shown.
    prediction: Optional[Literal["Normal", "Benign", "OPMD", "Oral Cancer"]] = None

    @field_validator("question")
    @classmethod
    def _check_question(cls, value: str) -> str:
        value = value.strip()
        if not 2 <= len(value) <= QUESTION_MAX_CHARS:
            raise ValueError(f"question must be 2-{QUESTION_MAX_CHARS} characters.")
        return value


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
    Thread(target=get_retriever().warm_up, name="rag-preload", daemon=True).start()
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
        "llm_configured": bool(rag_config.gemini_api_key()),
        "llm_model": rag_config.gemini_chat_model(),
        "rag": get_retriever().status(),
        "commit": os.getenv("RENDER_GIT_COMMIT", "local")[:7],
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)) -> Dict[str, Any]:
    name_ok = (file.filename or "").lower().endswith(ALLOWED_EXTENSIONS)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES and not name_ok:
        raise HTTPException(
            status_code=400,
            detail="Only jpg, jpeg, png, and heic images are supported.",
        )

    image_bytes = await file.read()
    await file.close()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    try:
        with Image.open(BytesIO(image_bytes)) as uploaded_image:
            # 手機原圖很大，免費方案只有 512 MB 記憶體，先縮小再處理（模型只用 224×224）。
            # JPEG 用 draft 直接以低解析度解碼，其他格式解碼後立刻縮小。
            if uploaded_image.format in ("JPEG", "MPO"):  # 很多手機與相機照片是 MPO（多張 JPEG）
                uploaded_image.draft("RGB", (MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            uploaded_image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            # 手機照片的方向常存在 EXIF 裡，先轉正再分析。
            image = ImageOps.exif_transpose(uploaded_image).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400,
            detail="Unable to read the uploaded image.",
        )

    from ood import NOT_ORAL_MESSAGE, features_look_oral, looks_like_oral_photo

    # 模型只會在四類裡選一個，X 光、風景或截圖也會被判成某一類，所以先擋掉不像口腔的照片。
    if not looks_like_oral_photo(image):
        raise HTTPException(status_code=422, detail=NOT_ORAL_MESSAGE)

    # Loading and inference are CPU-bound; running them in the threadpool keeps
    # /health and /explain responsive in the meantime.
    model, device = await run_in_threadpool(get_model)
    from predict import predict_image

    result = await run_in_threadpool(predict_image, image, model, device)
    feature = result.pop("_feature")
    if not features_look_oral(feature):
        raise HTTPException(status_code=422, detail=NOT_ORAL_MESSAGE)
    # The full result page (summary, care, education, handbook link) needs no LLM
    # call, so it comes back with the prediction; /explain returns the same content.
    result.update(build_report(result["class_probabilities"]))
    result["disclaimer"] = DISCLAIMER
    return result


@app.post("/explain")
def explain(request: ExplainRequest) -> Dict[str, Any]:
    """Result-page content for given class probabilities (same as in /predict)."""
    return build_report(request.class_probabilities)


@app.post("/education")
def education(request: ExplainRequest) -> Dict[str, Any]:
    """結構化衛教說明：依病灶知識庫逐一病灶、逐一欄位，由 RAG + Gemini 為這次結果撰寫。

    Gemini 無法使用或內容沒通過檢查時，回傳事先產生的同結構內容，頁面不會空白。"""
    try:
        report = generate_lesion_report(request.class_probabilities)
    except Exception:
        LOGGER.exception("Lesion report failed.")
        report = None
    if report:
        return {"lesion_report": report, "source": "llm"}
    return {"lesion_report": stored_lesion_report(request.class_probabilities), "source": "curated"}


@app.post("/ask")
def ask(request: AskRequest) -> Dict[str, Any]:
    """Answer an oral-health question from the education documents (RAG)."""
    try:
        return answer_question(request.question, request.prediction)
    except Exception:
        LOGGER.exception("RAG /ask failed.")
        raise HTTPException(status_code=503, detail="衛教問答暫時無法使用，請稍後再試。")

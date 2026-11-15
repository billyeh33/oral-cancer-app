# 口腔病灶影像輔助篩檢網站

這是一個研究型 prototype，採正式前後端分離架構：

- Frontend：Next.js + React + TypeScript
- Backend：FastAPI + PyTorch + Torchvision + PIL
- CNN：Hierarchical ConvNeXt-Tiny
- LLM：Gemini API，僅接收 CNN 的文字輸出，不接收圖片
- RAG：Qdrant 向量資料庫＋官方口腔衛教文件，提供有出處的衛教問答（說明見 [backend/rag/README.md](backend/rag/README.md)）

本系統只提供「AI 初步風險篩檢」與「繁體中文衛教說明」，不能取代醫師診斷、病理切片或正式醫療建議。

## 專案結構

```text
oral-lesion-screening/
├── backend/
│   ├── main.py
│   ├── labels.py
│   ├── model.py
│   ├── predict.py
│   ├── test_predict.py
│   ├── requirements.txt
│   ├── .env.example
│   └── best_hierarchical_convnext_mac.pth
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── next-env.d.ts
│   ├── .env.example
│   ├── public/
│   │   └── hero-oral-screening.png
│   ├── app/
│   ├── components/
│   └── lib/
├── .github/
│   └── workflows/
│       └── keep-backend-awake.yml
├── .gitignore
└── README.md
```

## 模型流程

模型輸出三組 binary logits：

1. Stage 1：Normal vs Abnormal
2. Stage 2：Benign vs Malignant
3. Stage 3：OPMD vs Oral Cancer

後端使用 softmax 後的 hierarchical path probability 轉成四分類：

- Normal = `P(S1 = Normal)`
- Benign = `P(S1 = Abnormal) × P(S2 = Benign)`
- OPMD = `P(S1 = Abnormal) × P(S2 = Malignant) × P(S3 = OPMD)`
- Oral Cancer = `P(S1 = Abnormal) × P(S2 = Malignant) × P(S3 = Oral Cancer)`

`confidence` 為最高四分類機率。

## 本機啟動 Backend

```bash
cd oral-lesion-screening/backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.3.1 torchvision==0.18.1
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

啟動後可檢查：

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
```

`/health` 會回傳：

```json
{
  "status": "ok",
  "model_loaded": true
}
```

## 本機啟動 Frontend

```bash
cd oral-lesion-screening/frontend
npm install
cp .env.example .env.local
npm run dev
```

預設前端：

```text
http://localhost:3000
```

預設 backend：

```text
http://localhost:8000
```

## 環境變數

### Backend

建立 `backend/.env`：

```env
GEMINI_API_KEY=your_gemini_api_key_here
# GOOGLE_API_KEY=your_google_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
CORS_ALLOW_ORIGINS=*
```

說明：

- `GEMINI_API_KEY` 只放在 backend。
- 如果你的部署平台已使用 Google SDK 慣例，也可以改用 `GOOGLE_API_KEY`。
- 沒有設定 `GEMINI_API_KEY` 時，API 仍可正常運作，會回傳 fallback explanation。
- `TORCH_NUM_THREADS`（選填）：CNN 推論使用的 CPU 執行緒數。在 Render 上預設為 1，因為免費方案只分到一小部分 CPU，多開執行緒反而更慢。
- 開發期可暫用 `CORS_ALLOW_ORIGINS=*`。
- 正式部署時建議改成指定前端網域，例如 Vercel 網址。

### Frontend

建立 `frontend/.env.local`：

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

部署到 Vercel 後，請把它改成正式 backend 公開網址。

## 測試 `/predict`

### 方式一：使用測試腳本

```bash
cd oral-lesion-screening/backend
source .venv/bin/activate
python test_predict.py /absolute/path/to/example.jpg
```

### 方式二：使用 HTTP API

```bash
curl -X POST http://localhost:8000/predict \
  -F "file=@/absolute/path/to/example.jpg"
```

API 回傳欄位：

- `prediction`
- `confidence`
- `risk_level`
- `class_probabilities`
- `stage_probabilities`
- `summary`、`care`、`education`、`handbook`（結果頁三個區塊與手冊連結）
- `explanation`、`care_guidance`（舊欄位，保留相容）
- `disclaimer`

`/predict` 會連同結果頁內容一起回傳，不需要即時呼叫 Gemini，所以會馬上回傳。各欄位說明見 [backend/rag/README.md](backend/rag/README.md)。

## 影像與隱私設計

- 不儲存使用者上傳的原始圖片。
- 圖片只送入 backend CNN 推論。
- Gemini 不會接收圖片，也不會接收篩檢機率；結果頁內容是預先產生並人工審核的。
- 只有衛教問答（`/ask`）會把使用者輸入的問題送給 Gemini。
- `GEMINI_API_KEY` 不會暴露在 frontend。
- `.env` 與 `.env.local` 已加入 `.gitignore`。

## Frontend 內容

- 首頁：
  - 系統定位
  - 研究型 prototype 說明
  - 完整免責聲明
- 上傳頁：
  - jpg / jpeg / png 上傳
  - 圖片預覽
  - 進入頁面時先呼叫 `/health` 喚醒 backend，並顯示伺服器狀態
  - loading 狀態
  - 錯誤訊息
  - AI 初步風險篩檢結果（CNN 算完立刻顯示）
  - 四分類機率
  - 三階段機率
  - 結果說明、就診建議、衛教說明（附手冊頁碼與官方手冊連結），與 CNN 結果一起回傳
  - 免責聲明

## Backend API

### `GET /`

回傳 API 基本狀態。

### `GET /health`

回傳模型是否已載入、是否設定 Gemini、使用的 Gemini 模型，以及 Render 上目前部署的 commit（`commit`）。backend 啟動時會在背景預先載入模型。

### `POST /predict`

接收圖片並回傳：

```json
{
  "prediction": "Oral Cancer",
  "confidence": 0.82,
  "risk_level": "高風險",
  "class_probabilities": {
    "Normal": 0.01,
    "Benign": 0.02,
    "OPMD": 0.15,
    "Oral Cancer": 0.82
  },
  "stage_probabilities": {
    "stage_1": {
      "Normal": 0.01,
      "Abnormal": 0.99
    },
    "stage_2": {
      "Benign": 0.02,
      "Malignant": 0.98
    },
    "stage_3": {
      "OPMD": 0.15,
      "Oral Cancer": 0.85
    }
  },
  "summary": "AI 篩檢最可能為「疑似口腔癌病灶」，約 82%。……",
  "care": { "department": "…", "timing": "…", "bring": "…", "sources": [] },
  "education": [{ "heading": "…", "text": "…", "sources": [] }],
  "handbook": { "title": "口腔黏膜異常患者之口腔保健指導手冊（民眾版）", "url": "https://dep.mohw.gov.tw/DOOH/cp-6545-77332-124.html" },
  "explanation": "同 summary（舊欄位）",
  "care_guidance": "care 的三行文字（舊欄位）",
  "disclaimer": "本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。"
}
```

### `POST /explain`

接收四類機率，回傳和 `/predict` 相同的結果頁內容（`summary`、`care`、`education`、`handbook` 等）。`/predict` 已經包含這些內容，網站前端不會呼叫它；保留給只有機率、想重新取得說明文字的情況（例如測試）。

```json
{
  "class_probabilities": {
    "Normal": 0.01,
    "Benign": 0.02,
    "OPMD": 0.57,
    "Oral Cancer": 0.40
  }
}
```

### `POST /ask`

衛教問答（RAG）：只根據衛教文件回答並附出處。請求、回應與前端顯示方式見 [backend/rag/README.md](backend/rag/README.md)。

## 部署到 Vercel

Frontend 只部署 Next.js，不放 CNN 推論：

1. 將專案 push 到 GitHub。
2. 在 Vercel 匯入 `frontend` 專案。
3. 設定環境變數：
   - `NEXT_PUBLIC_API_BASE_URL=https://your-backend.example.com`
4. 重新部署。

## 部署到 Render

Backend 建議建立 Web Service：

1. Root Directory：`backend`
2. Build Command：

```bash
pip install --upgrade pip
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.3.1 torchvision==0.18.1
pip install -r requirements.txt
```

3. Start Command：

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

4. 設定環境變數：
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL`
   - `CORS_ALLOW_ORIGINS=https://your-frontend.vercel.app`

### 保持喚醒

Render 免費方案在 15 分鐘沒有流量後會休眠，喚醒可能要好幾分鐘。`.github/workflows/keep-backend-awake.yml` 每 10 分鐘 ping 一次 `/health` 讓它保持喚醒（網址可用 GitHub repository variable `BACKEND_URL` 覆寫）。

注意：

- Render 每個 workspace 每月有 750 小時免費時數，一個服務全天不休眠約用掉 744 小時；同一個 workspace 若還有其他免費服務，時數會不夠，用完後所有免費服務會暫停到下個月。
- GitHub 的排程偶爾會延遲，服務仍可能偶爾休眠。
- 公開 repository 超過 60 天沒有任何活動時，GitHub 會自動停用排程 workflow，需要到 Actions 頁面重新啟用。

## 部署到 Hugging Face Spaces

> 2026-09 查證：Hugging Face 現在需要付費方案才能建立 Gradio / Docker Space（Static Space 仍免費），CPU Basic 硬體本身不收時數費。

如果模型權重較大，或 Render 對部署大小、啟動時間、CPU 記憶體不夠友善，可改用 Hugging Face Spaces：

- Docker / FastAPI 方式較適合保留目前架構。
- 也可以改成 Gradio / Streamlit 做展示版。
- 請確認 `best_hierarchical_convnext_mac.pth` 能在容器內讀取。
- 將 `GEMINI_API_KEY` 設成 Space Secret。

## 大型權重檔建議

`best_hierarchical_convnext_mac.pth` 約 106 MB。若 GitHub、Render 或其他 hosting 對大檔處理不便，可考慮：

- Git LFS
- Hugging Face Spaces / Hub
- 物件儲存服務，部署時下載權重
- 將 backend 部署到更適合大型模型檔案的 VM 或 container 平台

## 免責聲明

本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。

# 口腔病灶影像輔助篩檢網站

這是一個研究型 prototype，採正式前後端分離架構：

- Frontend：Next.js + React + TypeScript
- Backend：FastAPI + PyTorch + Torchvision + PIL
- CNN：Hierarchical ConvNeXt-Tiny
- LLM：Gemini API，僅接收 CNN 的文字輸出，不接收圖片

本系統只提供「AI 初步風險篩檢」與「繁體中文衛教說明」，不能取代醫師診斷、病理切片或正式醫療建議。

## 專案結構

```text
oral-lesion-screening/
├── backend/
│   ├── main.py
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
GEMINI_MODEL=gemini-2.5-flash
CORS_ALLOW_ORIGINS=*
```

說明：

- `GEMINI_API_KEY` 只放在 backend。
- 沒有設定 `GEMINI_API_KEY` 時，API 仍可正常運作，會回傳 fallback explanation。
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
- `explanation`
- `disclaimer`

## 影像與隱私設計

- 不儲存使用者上傳的原始圖片。
- 圖片只送入 backend CNN 推論。
- Gemini 不會接收圖片。
- Gemini 只接收 CNN 的文字輸出：
  - prediction
  - confidence
  - risk_level
  - class_probabilities
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
  - loading 狀態
  - 錯誤訊息
  - AI 初步風險篩檢結果
  - 四分類機率
  - 三階段機率
  - Gemini 繁體中文衛教說明
  - 免責聲明

## Backend API

### `GET /`

回傳 API 基本狀態。

### `GET /health`

回傳模型是否成功載入。

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
  "explanation": "繁體中文衛教說明",
  "disclaimer": "本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。"
}
```

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

## 部署到 Hugging Face Spaces

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

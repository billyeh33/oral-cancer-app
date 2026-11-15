# 交接文件：RAG 衛教問答與結果頁改版

> **給 Claude（或任何接手的 AI 助手）**：這份文件說明這次對網站前後端做了哪些修改、為什麼這樣設計，以及合併和部署時要注意什麼。動手修改之前，請先讀完這份文件和 `backend/rag/README.md`。第 9 節列出了「不要改回去」的設計決定。
>
> 交接日期：2026-11-16。比對基準：原本的專案壓縮檔 `口腔癌網站_程式碼與模型.zip` 裡的 `oral-lesion-screening/`。

---

## 1. 一句話總結

網站新增了以衛福部官方衛教文件為知識庫的 **RAG**，向量資料庫使用 **Qdrant**。有兩個用途：

1. **結果頁改成三個區塊**：結果說明、就診建議、衛教說明。內容都和 `/predict` 一起回傳，**不再即時呼叫 Gemini**。
2. **新增衛教問答**：`POST /ask` 加上前端的問答框，只根據文件回答，並標示出處頁碼。

另外，文字中提到的官方查詢網站（例如「口腔癌確認診斷及治療醫院名單」）會自動變成超連結。

---

## 2. 檔案清單

### 2.1 新增（27 個）

壓縮檔 `交接_RAG_前後端修改.zip` 收錄了 2.1 和 2.2 節列出的全部 36 個檔案，路徑和專案相同（`oral-lesion-screening/...`），解壓縮後直接覆蓋到專案即可。

**後端：`backend/rag/`（整個資料夾都是新的）**

| 檔案 | 用途 |
|---|---|
| `__init__.py` | 對外提供的 API：`answer_question`、`build_report`、`get_retriever`、`retrieve` |
| `config.py` | 路徑與環境變數（Gemini key／模型、Qdrant 連線） |
| `chunking.py` | 文件切分規則與來源清單（`SOURCES`） |
| `sparse.py` | 中文雙字詞（bigram）的 BM25 關鍵字向量 |
| `embeddings.py` | Gemini embedding（`gemini-embedding-001`，768 維） |
| `store.py` | Qdrant：建立 collection、payload index、上傳、混合檢索（RRF） |
| `retriever.py` | `retrieve(query, k, source_ids, chapters)`；Qdrant Cloud 連不上時會自動改用記憶體版 |
| `answer.py` | `/ask` 的 prompt、回答、驗證與 fallback |
| `explain.py` | 結果頁內容：結果說明模板、就診建議（`CARE`）、手冊連結 |
| `links.py` | 官方查詢網站清單（`LOOKUP_LINKS`）與 `find_links()` |
| `build_index.py` | 指令：切分 → 計算向量 → 上傳 Qdrant |
| `build_explain_content.py` | 指令：用 RAG 產生四種結果的「衛教說明」 |
| `evaluate.py` | 指令：檢索評估（Hit@k、MRR） |
| `eval_questions.json` | 24 題評估題目與正確頁碼 |
| `requirements-build.txt` | 重建索引時才需要的套件（PyMuPDF） |
| `README.md` | RAG 模組的詳細說明（API、前端用法、重建方式、評估結果） |
| `sources/口腔黏膜異常患者之口腔保健指導手冊(民眾版).pdf` | 知識庫來源（18 MB） |
| `sources/口腔黏膜檢查陽性個案後續確診及治療處置流程.pdf` | 知識庫來源（原檔） |
| `sources/處置流程_整理.md` | 流程圖的人工轉寫版本（實際建索引用的是這份） |
| `data/chunks.jsonl` | 68 個切分後的段落，**網站執行時會讀取** |
| `data/dense_vectors.json` | 預先算好的向量，**網站執行時會讀取**（Qdrant Cloud 連不上時的備援） |
| `data/index_meta.json` | 索引的建置資訊 |
| `data/explain_content.json` | 結果頁「衛教說明」內容，**網站執行時會讀取**（尚未人工審核） |

**前端：`frontend/components/`**

| 檔案 | 用途 |
|---|---|
| `AskPanel.tsx` | 衛教問答框 |
| `LinkedText.tsx` | 把文字中的查詢網站名稱換成超連結 |
| `SourceTags.tsx` | 「手冊 p.18」這類出處標籤 |

**根目錄**：`HANDOFF_RAG.md`（就是這份文件）

### 2.2 修改（9 個）

| 檔案 | 修改內容 |
|---|---|
| `backend/main.py` | 刪除即時 Gemini 說明的程式；`/predict` 直接回傳結果頁內容；`/explain` 改成回傳同樣的內容；新增 `/ask`；`/health` 加上 `rag` 狀態 |
| `backend/requirements.txt` | 加入 `qdrant-client>=1.12.0` |
| `backend/.env.example` | `GEMINI_MODEL` 改成 `gemini-3.5-flash-lite`；加入 Qdrant 相關變數 |
| `frontend/components/ResultPanel.tsx` | 重寫成三個區塊，詳細機率移到最下面 |
| `frontend/components/UploadAnalyzer.tsx` | 刪除第二次呼叫 `/explain` 和載入中的骨架畫面；加入 `<AskPanel>`；修改使用提醒的文字 |
| `frontend/lib/types.ts` | 新增 `ResultReport`、`PredictResult`、`AskResponse`、`RagSource`、`LookupLink` |
| `frontend/lib/api.ts` | `analyzeImage()` 改成回傳 `PredictResult`；刪除 `fetchAdvice()`；新增 `askQuestion()` |
| `frontend/app/globals.css` | 刪除舊的 `.formatted-*`、`.advice-loading`、`.skeleton-*` 樣式；新增三區塊、問答框、連結的樣式 |
| `README.md` | 更新 API 說明與隱私設計段落 |

### 2.3 不要交出去或不要 commit 的檔案

| 檔案 | 原因 |
|---|---|
| `backend/.env` | 裡面有 Gemini 和 Qdrant 的 key。已經在 `.gitignore` 裡，請各自依 `.env.example` 建立 |
| `frontend/package-lock.json` | 是交接方測試時 `npm install` 產生的，原專案沒有這個檔案；交出去可能會改變同學那邊安裝到的套件版本 |
| `frontend/node_modules/`、`frontend/.next/`、`**/__pycache__/` | 建置產物 |

---

## 3. 架構與資料流

```
                ┌──────────── 建置時（離線，維護 RAG 的人執行） ────────────┐
 PDF / 整理.md ─► chunking ─► Gemini embedding ─► Qdrant Cloud（collection: oral_health_kb）
                   │                              └► rag/data/（chunks、向量，作為備援）
                   └► build_explain_content：分章節 RAG ＋ Gemini ─► rag/data/explain_content.json（待人工審核）

                ┌──────────────── 網站執行時 ────────────────┐
 上傳照片 ─► POST /predict ─► CNN ─► 機率
                              └► build_report(機率)   ← 不呼叫 LLM
                                   ├ summary   ：模板
                                   ├ care      ：explain.py 的 CARE（人工撰寫，附依據）
                                   ├ education ：讀取 explain_content.json
                                   └ handbook  ：一個官方手冊連結
 問題 ──► POST /ask ─► 混合檢索（Qdrant：語意向量＋BM25，RRF 合併）─► Gemini 依段落回答 ─► 回答＋出處＋查詢網站連結
```

- **知識庫**：衛福部《口腔黏膜異常患者之口腔保健指導手冊（民眾版）》77 頁（跳過封面、目錄和版權頁），加上國健署《口腔黏膜檢查陽性個案後續確診及治療處置流程》（流程圖，用人工轉寫的 3 段文字），總共 68 個 chunk。
- **切分方式**：手冊第二章每頁介紹一種病變，所以以頁為單位切分（頁碼就是出處）。超過 650 字的頁面依句號再切，前後重疊一句。每個 chunk 計算向量時，前面會加上「文件｜章節｜病名」作為上下文。
- **混合檢索**：語意向量（Gemini）負責口語說法，例如「擦不掉的白色東西」能找到白斑；BM25 雙字詞負責縮寫和專有名詞，例如 OSF、PMD。兩邊的排名用 RRF 合併。

---

## 4. 後端 API

### `POST /predict`（回應有修改）

除了原本的欄位（`prediction`、`confidence`、`risk_level`、`class_probabilities`、`stage_probabilities`、`disclaimer`），還會回傳整個結果頁的內容：

```jsonc
{
  "summary": "AI 篩檢最可能為「口腔潛在惡性疾患（癌前病變）」，約 61%。其次為…。這只是依照片做的初步分類，實際情況要由醫師檢查確認。",
  "care": {
    "department": "口腔顎面外科，或具頭頸癌診治專業的耳鼻喉科；可先查衛福部「口腔癌確認診斷及治療醫院名單」",
    "timing": "盡快就醫，由醫師評估是否需要切片檢查",
    "bring": "這次上傳的照片、發現異狀的時間與位置、是否疼痛或出血；…",
    "sources": [RagSource, ...],   // 依據
    "links": [LookupLink, ...]     // 文字中提到的查詢網站
  },
  "education": [
    { "heading": "認識口腔白斑與紅斑", "text": "…", "sources": [RagSource], "links": [LookupLink] }
  ],
  "handbook": { "title": "口腔黏膜異常患者之口腔保健指導手冊（民眾版）", "publisher": "衛生福利部", "url": "https://dep.mohw.gov.tw/DOOH/cp-6545-77332-124.html" },
  "content_reviewed": false,          // explain_content.json 是否已經人工審核
  "explanation": "（同 summary，舊欄位）",
  "care_guidance": "1. 建議科別：…\n2. 就醫時機：…\n3. 就診時可以告訴醫師：…（舊欄位）",
  "source": "curated",
  "sources": [RagSource, ...]         // 以上所有出處，已去除重複
}
```

- `RagSource`：`chunk_id`、`source_title`、`publisher`、`file`、`page`、`chapter`、`section`、`title`、`text`、`score`、`citation`（現成的出處文字）
- `LookupLink`：`text`（文字中出現的網站名稱）、`url`、`label`（滑鼠提示用的全名）

### `POST /explain`（行為有修改）

請求格式不變，仍然是 `{ "class_probabilities": {...} }`，但**不再呼叫 Gemini**。現在回傳的內容和上面 `/predict` 的結果頁欄位相同。前端已經不會呼叫它，保留下來是為了測試和相容。

### `POST /ask`（新增）

```jsonc
// 請求
{ "question": "白斑會變成口腔癌嗎？", "prediction": "OPMD" }   // prediction 可以省略或傳 null；question 限 2～300 字
// 回應
{ "answer": "…", "status": "answered" | "not_found" | "fallback", "sources": [RagSource], "links": [LookupLink] }
```

| status | 意思 |
|---|---|
| `answered` | 依據文件回答；`sources` 是實際引用的段落 |
| `not_found` | 文件沒有提到、問題跟口腔健康無關、要求診斷或開藥、或試圖改變規則；`answer` 是固定的「查不到，建議詢問醫師」 |
| `fallback` | Gemini 無法使用（超過額度、逾時等）；`answer` 是提示文字，`sources` 是最相關的 3 段原文 |

錯誤時：`422` 代表問題長度不合；`503` 代表檢索本身失敗。

### `GET /health`

多了 `rag` 欄位：`{ ready, mode: "cloud"|"memory", chunks, hybrid, error }`。這個欄位**不會觸發任何外部連線**，GitHub Actions 每 10 分鐘 ping 一次也沒問題。

---

## 5. 後端設計細節

### 5.1 結果頁三個區塊（`rag/explain.py`）

| 區塊 | 產生方式 | 原因 |
|---|---|---|
| 結果說明 `summary` | 套用模板。≥99.5% 顯示「99% 以上」；<1% 顯示「不到 1%」；前兩名相差小於 0.25 時，說明「AI 難以明確區分」 | 原本四捨五入成「約 100%」，看起來像 AI 很確定 |
| 就診建議 `care` | `CARE` 字典人工撰寫，每類附 `basis`（chunk id） | 就醫建議要穩定、可以審核，不能讓模型自由發揮 |
| 衛教說明 `education` | `build_explain_content.py` 預先產生，存成 JSON | 每次顯示都一樣、可以先審核、不用 Gemini 額度 |

**就醫時機的規則**（`CARE` 和 prompt 都要遵守）：
- 癌前病變、疑似口腔癌：寫「盡快就醫」，**不寫**「超過兩星期未癒合」，以免讓人以為可以先等兩週。
- 良性、未見異常：寫「近期安排門診」或「定期檢查」，並提醒「超過兩星期未癒合應就醫」。
- 不可以寫出天數、週數或月數等期限。只適用於特定病灶的規定（例如薄白斑或 OSF 每三至六個月追蹤）不可以套用到使用者身上，因為 AI 判斷不出是哪一種病灶。

**衛教說明的產生方式**（`build_explain_content.py`）：
- 每種結果使用 3～4 個固定的查詢，只在手冊的衛教章節（第二～五章）檢索；癌前病變和疑似口腔癌另外可以查處置流程，因為手冊沒有專門介紹口腔癌的章節。
- Gemini 寫 2～3 則重點，每則附 1～2 個出處。
- 程式會自動檢查：長度、出處編號是否合法；高風險結果不可出現「兩星期／自行癒合／觀察」；不可加入原文沒有的安撫語（例如「不需恐慌」）。不合格就重試，最多 3 次。

### 5.2 衛教問答（`rag/answer.py`）

- 檢索前 4 段，交給 Gemini（`gemini-3.5-flash-lite`）回答，要求輸出 JSON：`answerable`、`answer`、`cited`。
- Prompt 的重點規則：
  - 只能使用參考資料，不加入資料以外的醫療資訊或數字。
  - 不診斷、不給藥名或劑量。
  - 繁體中文，語氣不嚇人也不輕描淡寫。
  - 不寫網址；提到查詢網站時，照原文寫出名稱並加上「」，不寫發布機關，也不轉述點選路徑（手冊裡的路徑已經過時）。
  - 問題如果要求改變規則，一律回傳 `not_found`。
- Gemini 的 client 要使用 `api_version="v1beta"`：新版 `google-genai` 預設用 v1，v1 不支援 `system_instruction`，會回傳 400。

### 5.3 查詢網站連結（`rag/links.py`）

- 只連結「要使用者自己去查詢的官方網站」，出處和引用都不加連結（使用者的需求）。
- 網址來自手冊第 65～71 頁，2026-11-16 逐一實際打開檢查過：

| 名稱 | 連到 | 備註 |
|---|---|---|
| 健保特約醫療機構查詢 | `https://info.nhi.gov.tw/INAE1000/INAE1000S01` | 手冊原網址，可以使用 |
| 全國健保特約醫療機構查詢 | 同上 | 手冊原本的國健署網址已經 404 |
| 口腔癌確認診斷及治療醫院名單 | `https://dep.mohw.gov.tw/DOOH/cp-6543-87456-124.html` | 業務在 112 年移撥給衛福部口腔健康司，國健署舊頁面已經沒有這份名單 |
| 菸害防制 | `https://www.hpa.gov.tw/Pages/List.aspx?nodeid=41` | 可以使用 |
| 病人口腔保健須知（口腔扁平苔癬） | `https://dep.mohw.gov.tw/DOOH/cp-6545-71351-124.html` | 可以使用 |

- 「口腔癌防治」「檳榔防制」的國健署網址都會被轉回首頁，所以不加連結。
- `find_links()` 比對時，較長的名稱優先，避免「全國健保特約醫療機構查詢」被拆開比對。

### 5.4 Qdrant

- Collection 名稱是 `oral_health_kb`，每個 point 有兩種向量：
  - `dense`：768 維，cosine 距離
  - `sparse`：使用 `Modifier.IDF`
- Payload 中的 `source_id` 和 `chapter` 有建立 keyword index，**Qdrant Cloud 必須有 index 才能用這兩個欄位過濾**。
- 有設定 `QDRANT_URL` 時連 Qdrant Cloud；沒設定或連不上時，會用 `rag/data/` 在記憶體中建一個 Qdrant。所以 **`rag/data/` 一定要 commit**。
- 目前的 cluster 位於 GCP australia-southeast1（雪梨）；從台灣查詢一次大約 0.12 秒。

### 5.5 評估結果（24 題）

| 設定 | Hit@4 | MRR@4 |
|---|---|---|
| 只用 BM25 | 92% | 0.917 |
| 只用語意向量 | 100% | 0.958 |
| 混合檢索（網站實際使用） | 100% | 0.938 |

`/ask` 測了 8 題：4 題正常問題都有回答並附上正確出處；藥物劑量、超出範圍的問題、要求改規則、問天氣這 4 題都回傳 `not_found`。每題約 1.5～4 秒。

---

## 6. 前端修改

- **`ResultPanel.tsx`**：依序顯示
  1. 結果說明：三格資訊（類別改成中文、下方附英文），加上 `summary`
  2. 就診建議：`<dl>` 三列（看哪一科／什麼時候去／就診時可以告訴醫師），下方是依據標籤
  3. 衛教說明：每則有 `heading`、`text` 和頁碼標籤，區塊底部是「查看完整衛教手冊」按鈕（`handbook.url`）。**整個結果頁只有這一個手冊連結**，另外就是文字裡的查詢網站連結
  4. 詳細機率：四分類、三階段（內容沒有改）

  原本約 230 行的「把 AI 自由文字切成段落」解析程式已經刪除。
- **`AskPanel.tsx`**：
  - 放在上傳頁最下面，還沒分析時也可以使用；有結果時會一起送出 `prediction`。
  - 建議問題會依結果改變（`SUGGESTIONS`），點一下就直接送出。
  - Enter 送出、Shift+Enter 換行；中文輸入法選字時按 Enter 不會送出（`isComposing`）。
  - 保留最近 5 筆問答，最新的在最上面。`not_found` 和 `fallback` 用黃色邊框標示，`fallback` 會列出原文段落。
- **`LinkedText.tsx`**：依照 `links` 把文字中的網站名稱換成 `<a target="_blank" rel="noopener noreferrer">`，連結後面會加上 ↗ 符號。
- **`UploadAnalyzer.tsx`**：分析流程簡化成只呼叫一次 `/predict`。使用提醒改成「圖片只用於本站的 AI 篩檢，不會傳給 Gemini 或其他外部服務」，這是事實：現在只有使用者在問答框輸入的問題會送給 Gemini。
- **CSS 新增的 class**：
  - 結果頁：`.report-summary`、`.care-list`、`.report-basis`、`.source-tag(s)`、`.education-list/item`、`.handbook-link`
  - 問答框：`.ask-*`
  - 連結與無障礙：`.lookup-link`、`.sr-only`
  - 手機版（≤720px）時，`.care-list` 會改成上下排列。

---

## 7. 部署步驟

### 後端（Render）

1. 先合併程式碼，確認 `backend/rag/data/` 有 commit。`backend/rag/sources/` 的 PDF 只有重建索引時才需要（約 18 MB），要不要 commit 可以自行決定。
2. 在 Render 設定環境變數：

| 變數 | 值 |
|---|---|
| `GEMINI_API_KEY` | 原本就有的那把 |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite`（如果 Render 上原本設成 `gemini-2.5-flash`，一定要改；新用戶已經不能用 `gemini-2.5-flash-lite`） |
| `QDRANT_URL` | Qdrant Cloud cluster 網址，向 RAG 負責人私下索取 |
| `QDRANT_API_KEY` | 向 RAG 負責人私下索取，**不要貼在 repo 或群組裡** |
| `QDRANT_COLLECTION` | `oral_health_kb`（可以省略） |

3. 部署完成後檢查 `GET /health`：`rag.ready` 應該是 `true`，`rag.mode` 應該是 `"cloud"`。如果 `mode` 是 `"memory"`，代表 Qdrant Cloud 連不上，請查看 `rag.error`。

### 前端（Vercel）

不用改任何設定。`NEXT_PUBLIC_API_BASE_URL` 維持原樣即可。

---

## 8. 本機驗證

```bash
cd backend
pip install -r requirements.txt          # PyTorch 照原本 README 的方式安裝
uvicorn main:app --reload --port 8000

# 另一個終端機
curl http://localhost:8000/health
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"白斑會變成口腔癌嗎？\"}"
python -m rag.evaluate                   # 預期 Hit@4 = 24/24

cd ../frontend && npm install && npm run build && npm run dev
```

交接方已經完成的驗證：後端 `pyflakes` 檢查乾淨；`next build` 成功（型別檢查通過）；用瀏覽器實際操作上傳和問答，桌面版和 375px 手機版都正常，沒有橫向捲動。
**還沒驗證**：交接方的環境沒有 PyTorch，`/predict` 是用替身模型（固定回傳 OPMD 的機率）測試的。**請在有真實 CNN 的環境，四種結果都跑一次**。

---

## 9. 不要改回去的設計決定

1. **不要讓 `/explain` 或 `/predict` 再即時呼叫 Gemini 產生說明。** 原因是免費額度太少（`gemini-2.5-flash` 每天只有 20 次），而且模型曾經自己編出「一至兩週內就醫」、未經查證的安撫語，還會把機率寫成「約 100%」。
2. **修改 `CARE` 時，要同步更新 `basis`，並遵守 5.1 節的就醫時機規則。**
3. **重新產生衛教說明之後，必須人工逐則對照手冊原文**，確認無誤再把 `explain_content.json` 的 `"reviewed"` 改成 `true`。
4. **不要在 `/ask` 的回應或出處裡加入文件網址。** 只有查詢網站（`links.py`）可以變成連結；結果頁只放一個手冊連結。
5. **不要移除 Gemini client 的 `api_version="v1beta"`。**
6. **換 embedding 模型或修改切分規則之後，要重新執行 `python -m rag.build_index`**，並 commit `rag/data/`。

---

## 10. 待辦事項與已知限制

- [ ] **人工審核 `backend/rag/data/explain_content.json`**（目前 `reviewed: false`）。特別注意兩點：
  - 疑似口腔癌的兩則內容在講確診流程，和就診建議有些重複，因為手冊沒有專門介紹口腔癌的章節。之後可以考慮加入衛福部口腔健康司的口腔癌衛教頁面作為來源。
  - 癌前病變那則的「每三個月定期檢查」，是原文針對 OSF 的說法。
- [ ] 用真實 CNN 測試四種結果的畫面。
- [ ] 部署前，確認 Render 上的 `GEMINI_MODEL` 和兩個 Qdrant 變數都設定好了。
- **Gemini 額度**：現在只剩 `/ask` 會用到。超過額度時會回傳 `fallback`，網站不會壞。實際額度請到 AI Studio 的 rate limit 頁面查看。
- **Qdrant Cloud 免費 cluster**：一段時間沒有使用會被暫停。網站會自動改用記憶體索引，不會壞；展示前請登入確認 cluster 還在運作，或執行 `python -m rag.build_index` 重新上傳。
- **Render 記憶體**：`qdrant-client` 會額外載入 numpy 和 grpc。如果免費方案（512 MB）的記憶體不夠，可以先觀察部署後的記憶體用量。
- **手冊本身部分內容已經過時**：例如國健署的業務移撥、網址失效。這部分已經用 `links.py` 和 prompt 規則處理，但 RAG 回答的內容仍然以手冊原文為準。

---

## 11. 合併時的注意事項

- 如果同學那邊的 `main.py`、`ResultPanel.tsx`、`UploadAnalyzer.tsx`、`globals.css` 在這段期間也有修改，這四個檔案**很可能會衝突**：
  - `ResultPanel.tsx` 幾乎整個重寫，建議以新版為基礎，再把對方的修改加回來。
  - `main.py` 刪除的部分包括：`ADVICE_SYSTEM_INSTRUCTION`、`AdviceOutput`、`generate_advice`、`_fallback_explanation`、`_fallback_care_guidance`、`_gemini_client` 和 Gemini 相關常數。如果對方有修改這些部分，那些修改已經不需要了。
- `backend/.env` 不要 commit。
- 詳細的 API 用法、重建索引的指令和評估方式，請看 `backend/rag/README.md`。

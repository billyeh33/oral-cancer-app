"use client";

import Image from "next/image";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CircleCheck,
  ImagePlus,
  LoaderCircle,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { analyzeImage, fetchAdvice, wakeBackend } from "../lib/api";
import type { PredictionResponse } from "../lib/types";
import { ResultPanel } from "./ResultPanel";

const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png"];
const ALLOWED_TYPES = ["image/jpeg", "image/png"];

type ServerStatus = "waking" | "ready" | "offline";

const SERVER_STATUS_TEXT: Record<ServerStatus, string> = {
  waking: "正在喚醒分析伺服器，閒置一段時間後的第一次連線可能需要 1～3 分鐘。",
  ready: "分析伺服器已就緒。",
  offline: "暫時連不到分析伺服器，按下開始分析時會再試一次。",
};

function isSupportedImage(file: File) {
  const lowerName = file.name.toLowerCase();
  return (
    ALLOWED_TYPES.includes(file.type) ||
    ALLOWED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))
  );
}

export function UploadAnalyzer() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState<ServerStatus>("waking");
  // Bumped on every new analysis or file change, so a late response from an
  // earlier request can't overwrite the current one.
  const requestIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    wakeBackend().then((ok) => {
      if (!cancelled) {
        setServerStatus(ok ? "ready" : "offline");
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return undefined;
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  const helperText = useMemo(() => {
    if (!file) {
      return "支援 jpg、jpeg、png。系統不會保存原始上傳影像。";
    }
    return `${file.name} 已選取，可開始 AI 初步風險篩檢。`;
  }, [file]);

  function handleFileChange(nextFile: File | null) {
    requestIdRef.current += 1;
    setLoading(false);
    setAdviceLoading(false);
    setResult(null);
    setError(null);

    if (!nextFile) {
      setFile(null);
      return;
    }

    if (!isSupportedImage(nextFile)) {
      setFile(null);
      setError("請上傳 jpg、jpeg 或 png 格式的口腔影像。");
      return;
    }

    setFile(nextFile);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("請先選擇一張口腔影像。");
      return;
    }

    const requestId = ++requestIdRef.current;
    setLoading(true);
    setAdviceLoading(false);
    setError(null);
    setResult(null);

    let prediction: PredictionResponse;
    try {
      prediction = await analyzeImage(file);
    } catch (caughtError) {
      if (requestId === requestIdRef.current) {
        const message =
          caughtError instanceof Error
            ? caughtError.message
            : "分析失敗，請稍後再試。";
        setError(message);
        setLoading(false);
      }
      return;
    }

    if (requestId !== requestIdRef.current) {
      return;
    }

    // Show the CNN result right away; the AI-written advice fills in afterwards.
    setServerStatus("ready");
    setResult(prediction);
    setLoading(false);
    setAdviceLoading(true);

    try {
      const advice = await fetchAdvice(prediction.class_probabilities);
      if (requestId === requestIdRef.current) {
        setResult({
          ...prediction,
          explanation: advice.explanation,
          care_guidance: advice.care_guidance,
        });
      }
    } catch {
      // Keep the fixed texts that came with the prediction.
    } finally {
      if (requestId === requestIdRef.current) {
        setAdviceLoading(false);
      }
    }
  }

  return (
    <div className="analyzer-layout">
      <form className="upload-card" onSubmit={handleSubmit}>
        <div className="section-kicker">
          <Sparkles size={18} />
          上傳口腔影像
        </div>

        <label className="dropzone">
          <input
            accept=".jpg,.jpeg,.png,image/jpeg,image/png"
            onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
            type="file"
          />
          <UploadCloud size={28} />
          <strong>選擇影像檔案</strong>
          <span>{helperText}</span>
        </label>

        {previewUrl ? (
          <div className="preview-frame">
            <Image
              alt="待分析的口腔影像預覽"
              fill
              sizes="(max-width: 900px) 100vw, 520px"
              src={previewUrl}
              unoptimized
            />
          </div>
        ) : (
          <div className="preview-placeholder">
            <ImagePlus size={28} />
            <span>影像預覽會顯示在這裡</span>
          </div>
        )}

        {error ? (
          <p className="inline-error" role="alert">
            <AlertCircle size={16} />
            {error}
          </p>
        ) : null}

        <button className="primary-button" disabled={loading} type="submit">
          {loading ? (
            <>
              <LoaderCircle className="spin" size={18} />
              分析中
            </>
          ) : (
            <>
              <Sparkles size={18} />
              開始分析
            </>
          )}
        </button>

        <p className={`server-status server-status-${serverStatus}`} role="status">
          {serverStatus === "waking" ? (
            <LoaderCircle className="spin" size={14} />
          ) : serverStatus === "ready" ? (
            <CircleCheck size={14} />
          ) : (
            <AlertCircle size={14} />
          )}
          {SERVER_STATUS_TEXT[serverStatus]}
        </p>
      </form>

      <aside className="guidance-panel">
        <div className="section-kicker">
          <AlertCircle size={18} />
          使用提醒
        </div>
        <ul>
          <li>請使用清晰、光線足夠的口腔影像。</li>
          <li>系統僅提供 AI 初步風險篩檢與衛教說明。</li>
          <li>不會把圖片傳給 Gemini，LLM 只接收 CNN 的文字結果。</li>
          <li>若症狀持續超過兩週，建議就醫檢查。</li>
        </ul>
      </aside>

      {result ? <ResultPanel adviceLoading={adviceLoading} result={result} /> : null}
    </div>
  );
}

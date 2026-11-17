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
import { analyzeImage, fetchEducation, wakeBackend } from "../lib/api";
import { isHeic, prepareImage } from "../lib/prepareImage";
import type { PredictResult } from "../lib/types";
import { AskPanel } from "./AskPanel";
import { ResultPanel, type EducationStatus } from "./ResultPanel";

const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".heic", ".heif"];
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/heic", "image/heif"];

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
  const [originalName, setOriginalName] = useState<string | null>(null);
  const [converting, setConverting] = useState(false);
  const [previewable, setPreviewable] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictResult | null>(null);
  const [educationStatus, setEducationStatus] = useState<EducationStatus>("idle");
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
    if (!file || !previewable) {
      setPreviewUrl(null);
      return undefined;
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file, previewable]);

  const helperText = useMemo(() => {
    if (converting) {
      return "正在處理照片…";
    }
    if (!file) {
      return "支援 jpg、jpeg、png、heic（iPhone 照片）。系統不會保存原始上傳影像。";
    }
    return `${originalName ?? file.name} 已選取，可開始 AI 初步風險篩檢。`;
  }, [file, originalName, converting]);

  async function handleFileChange(nextFile: File | null) {
    const changeId = ++requestIdRef.current;
    setLoading(false);
    setResult(null);
    setEducationStatus("idle");
    setError(null);

    setConverting(false);
    setOriginalName(null);
    setPreviewable(true);

    if (!nextFile) {
      setFile(null);
      return;
    }

    if (!isSupportedImage(nextFile)) {
      setFile(null);
      setError("請上傳 jpg、jpeg、png 或 heic 格式的口腔影像。");
      return;
    }

    setFile(null);
    setConverting(true);
    const prepared = await prepareImage(nextFile);
    if (changeId !== requestIdRef.current) {
      return;
    }
    setConverting(false);
    setOriginalName(nextFile.name);
    if (prepared) {
      setFile(prepared);
    } else {
      // 瀏覽器處理不了就上傳原檔給後端，HEIC 只是沒有預覽。
      setPreviewable(!isHeic(nextFile));
      setFile(nextFile);
    }
  }

  // The page shows the reviewed per-class text first, then swaps in points written
  // for this exact result once /education answers (a few seconds).
  async function loadEducation(requestId: number, prediction: PredictResult) {
    setEducationStatus("loading");
    const response = await fetchEducation(prediction.class_probabilities);
    if (requestId !== requestIdRef.current) {
      return;
    }
    if (response?.source === "llm" && response.lesion_report) {
      const report = response.lesion_report;
      setResult((current) => (current ? { ...current, lesion_report: report } : current));
      setEducationStatus("llm");
    } else {
      setEducationStatus("curated");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (converting) {
      setError("照片還在處理，請稍等一下。");
      return;
    }
    if (!file) {
      setError("請先選擇一張口腔影像。");
      return;
    }

    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    setResult(null);
    setEducationStatus("idle");

    try {
      // /predict returns the prediction together with all three result sections.
      const prediction = await analyzeImage(file);
      if (requestId === requestIdRef.current) {
        setServerStatus("ready");
        setResult(prediction);
        void loadEducation(requestId, prediction);
      }
    } catch (caughtError) {
      if (requestId === requestIdRef.current) {
        setError(
          caughtError instanceof Error ? caughtError.message : "分析失敗，請稍後再試。",
        );
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
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
            accept=".jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png,image/heic,image/heif"
            onChange={(event) => void handleFileChange(event.target.files?.[0] ?? null)}
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
            {converting ? <LoaderCircle className="spin" size={28} /> : <ImagePlus size={28} />}
            <span>
              {converting
                ? "正在處理照片"
                : file && !previewable
                  ? "這個瀏覽器無法預覽 HEIC，仍可直接分析"
                  : "影像預覽會顯示在這裡"}
            </span>
          </div>
        )}

        {error ? (
          <p className="inline-error" role="alert">
            <AlertCircle size={16} />
            {error}
          </p>
        ) : null}

        <button className="primary-button" disabled={loading || converting} type="submit">
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
          <li>圖片只用於本站的 AI 篩檢，不會傳給 Gemini 或其他外部服務。</li>
          <li>若症狀持續超過兩週，建議就醫檢查。</li>
        </ul>
      </aside>

      {result ? <ResultPanel educationStatus={educationStatus} result={result} /> : null}

      <AskPanel prediction={result?.prediction} />
    </div>
  );
}

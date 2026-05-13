"use client";

import Image from "next/image";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { AlertCircle, ImagePlus, LoaderCircle, Sparkles, UploadCloud } from "lucide-react";
import { analyzeImage } from "../lib/api";
import type { PredictionResponse } from "../lib/types";
import { ResultPanel } from "./ResultPanel";

const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png"];
const ALLOWED_TYPES = ["image/jpeg", "image/png"];

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

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await analyzeImage(file);
      setResult(response);
    } catch (caughtError) {
      const message =
        caughtError instanceof Error
          ? caughtError.message
          : "分析失敗，請稍後再試。";
      setError(message);
    } finally {
      setLoading(false);
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

      {result ? <ResultPanel result={result} /> : null}
    </div>
  );
}

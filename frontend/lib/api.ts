import type { AskResponse, EducationResponse, Prediction, PredictResult } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

/** Runs the CNN; the response already includes the full result-page content (ResultReport). */
export async function analyzeImage(file: File): Promise<PredictResult> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/predict`, {
      method: "POST",
      body: formData,
    });
  } catch {
    // 連線中斷（伺服器重開或網路問題）時瀏覽器只會說 Failed to fetch。
    throw new Error("連不到分析伺服器，伺服器可能正在重新啟動，請等 1 分鐘後再試。");
  }

  if (!response.ok) {
    let message = "分析失敗，請稍後再試。";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        message = payload.detail;
      }
    } catch {
      message = "分析失敗，後端未回傳可讀取的錯誤訊息。";
    }
    throw new Error(message);
  }

  return (await response.json()) as PredictResult;
}

/**
 * 衛教說明 written by RAG + Gemini for these exact probabilities. Returns null on any
 * error, so the page simply keeps the education text that came with /predict.
 */
export async function fetchEducation(
  classProbabilities: PredictResult["class_probabilities"],
): Promise<EducationResponse | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/education`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_probabilities: classProbabilities }),
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as EducationResponse;
  } catch {
    return null;
  }
}

/**
 * Ask an oral-health question answered from the education documents (RAG).
 * Pass the screening result, if there is one, so the answer can focus on it.
 * The question must be 2-300 characters.
 */
export async function askQuestion(
  question: string,
  prediction?: Prediction,
): Promise<AskResponse> {
  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, prediction: prediction ?? null }),
  });

  if (!response.ok) {
    if (response.status === 422) {
      throw new Error("請輸入 2～300 字的問題。");
    }
    throw new Error("衛教問答暫時無法使用，請稍後再試。");
  }

  return (await response.json()) as AskResponse;
}

// The Render free plan sleeps when idle; calling this on page load starts waking it
// while the user is still picking a photo.
export async function wakeBackend(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

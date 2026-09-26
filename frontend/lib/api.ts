import type { AdviceResponse, PredictionResponse } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export async function analyzeImage(file: File): Promise<PredictionResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/predict`, {
    method: "POST",
    body: formData,
  });

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

  return (await response.json()) as PredictionResponse;
}

export async function fetchAdvice(
  classProbabilities: PredictionResponse["class_probabilities"],
): Promise<AdviceResponse> {
  const response = await fetch(`${API_BASE_URL}/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ class_probabilities: classProbabilities }),
  });

  if (!response.ok) {
    throw new Error("AI 說明暫時無法產生。");
  }

  return (await response.json()) as AdviceResponse;
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

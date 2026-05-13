"use client";

import { BarChart3, FileText, ShieldCheck } from "lucide-react";
import type { PredictionResponse, RiskLevel } from "../lib/types";
import { DisclaimerBanner } from "./DisclaimerBanner";

interface ResultPanelProps {
  result: PredictionResponse;
}

const RISK_CLASS: Record<RiskLevel, string> = {
  低風險: "risk-low",
  中低風險: "risk-midlow",
  中高風險: "risk-midhigh",
  高風險: "risk-high",
};

const CLASS_LABELS = [
  "Normal",
  "Benign",
  "OPMD",
  "Oral Cancer",
] as const;

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function ResultPanel({ result }: ResultPanelProps) {
  return (
    <section className="result-stack" aria-live="polite">
      <article className="result-summary">
        <div className="section-kicker">
          <ShieldCheck size={18} />
          AI 初步風險篩檢
        </div>
        <div className="summary-grid">
          <div>
            <span>AI 初步判定</span>
            <strong>{result.prediction}</strong>
          </div>
          <div>
            <span>影像風險分級</span>
            <strong className={`risk-pill ${RISK_CLASS[result.risk_level]}`}>
              {result.risk_level}
            </strong>
          </div>
          <div>
            <span>Confidence</span>
            <strong>{formatPercent(result.confidence)}</strong>
          </div>
        </div>
      </article>

      <article className="detail-card">
        <div className="section-kicker">
          <BarChart3 size={18} />
          四分類機率
        </div>
        <div className="probability-list">
          {CLASS_LABELS.map((label) => {
            const value = result.class_probabilities[label];
            return (
              <div className="probability-row" key={label}>
                <div className="probability-head">
                  <span>{label}</span>
                  <strong>{formatPercent(value)}</strong>
                </div>
                <div className="probability-track" aria-hidden="true">
                  <span style={{ width: `${Math.max(value * 100, 2)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </article>

      <article className="detail-card">
        <div className="section-kicker">
          <BarChart3 size={18} />
          三階段機率
        </div>
        <div className="stage-grid">
          <div className="stage-box">
            <span>Stage 1</span>
            <strong>Normal {formatPercent(result.stage_probabilities.stage_1.Normal)}</strong>
            <small>
              Abnormal {formatPercent(result.stage_probabilities.stage_1.Abnormal)}
            </small>
          </div>
          <div className="stage-box">
            <span>Stage 2</span>
            <strong>Benign {formatPercent(result.stage_probabilities.stage_2.Benign)}</strong>
            <small>
              Malignant {formatPercent(result.stage_probabilities.stage_2.Malignant)}
            </small>
          </div>
          <div className="stage-box">
            <span>Stage 3</span>
            <strong>OPMD {formatPercent(result.stage_probabilities.stage_3.OPMD)}</strong>
            <small>
              Oral Cancer{" "}
              {formatPercent(result.stage_probabilities.stage_3["Oral Cancer"])}
            </small>
          </div>
        </div>
      </article>

      <article className="detail-card explanation-card">
        <div className="section-kicker">
          <FileText size={18} />
          繁體中文衛教說明
        </div>
        <p>{result.explanation}</p>
      </article>

      <DisclaimerBanner text={result.disclaimer} />
    </section>
  );
}

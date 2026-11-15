"use client";

import {
  BarChart3,
  BookOpen,
  ClipboardList,
  Clock,
  ExternalLink,
  Hospital,
  MessageSquareText,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import type { PredictResult, RiskLevel } from "../lib/types";
import { LinkedText } from "./LinkedText";
import { SourceTags } from "./SourceTags";

interface ResultPanelProps {
  result: PredictResult;
}

const RISK_CLASS: Record<RiskLevel, string> = {
  低風險: "risk-low",
  中低風險: "risk-midlow",
  中高風險: "risk-midhigh",
  高風險: "risk-high",
};

const CLASS_LABELS = ["Normal", "Benign", "OPMD", "Oral Cancer"] as const;

const PREDICTION_LABELS_ZH: Record<PredictResult["prediction"], string> = {
  Normal: "未見明顯異常",
  Benign: "良性病灶",
  OPMD: "口腔潛在惡性疾患",
  "Oral Cancer": "疑似口腔癌病灶",
};

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function ResultPanel({ result }: ResultPanelProps) {
  const { care, education, handbook } = result;

  return (
    <section className="result-stack" aria-live="polite">
      <article className="result-summary">
        <div className="section-kicker">
          <ShieldCheck size={18} />
          結果說明
        </div>
        <div className="summary-grid">
          <div>
            <span>AI 初步判定</span>
            <strong>{PREDICTION_LABELS_ZH[result.prediction]}</strong>
            <small>{result.prediction}</small>
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
        <p className="report-summary">{result.summary}</p>
      </article>

      <article className="detail-card">
        <div className="section-kicker">
          <Stethoscope size={18} />
          就診建議
        </div>
        <dl className="care-list">
          <div>
            <dt>
              <Hospital size={16} />
              看哪一科
            </dt>
            <dd>
              <LinkedText links={care.links} text={care.department} />
            </dd>
          </div>
          <div>
            <dt>
              <Clock size={16} />
              什麼時候去
            </dt>
            <dd>
              <LinkedText links={care.links} text={care.timing} />
            </dd>
          </div>
          <div>
            <dt>
              <MessageSquareText size={16} />
              就診時可以告訴醫師
            </dt>
            <dd>
              <LinkedText links={care.links} text={care.bring} />
            </dd>
          </div>
        </dl>
        {care.sources.length > 0 ? (
          <p className="report-basis">
            依據
            <SourceTags sources={care.sources} />
          </p>
        ) : null}
      </article>

      <article className="detail-card">
        <div className="section-kicker">
          <BookOpen size={18} />
          衛教說明
        </div>
        {education.length > 0 ? (
          <div className="education-list">
            {education.map((item) => (
              <section className="education-item" key={item.heading}>
                <h3>{item.heading}</h3>
                <p>
                  <LinkedText links={item.links} text={item.text} />
                  <SourceTags sources={item.sources} />
                </p>
              </section>
            ))}
          </div>
        ) : null}
        <a
          className="handbook-link"
          href={handbook.url}
          rel="noopener noreferrer"
          target="_blank"
        >
          <ClipboardList size={18} />
          <span>
            查看完整衛教手冊
            <small>
              {handbook.title}（{handbook.publisher}）
            </small>
          </span>
          <ExternalLink size={16} />
        </a>
      </article>

      <article className="detail-card">
        <div className="section-kicker">
          <BarChart3 size={18} />
          詳細機率：四分類
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
          詳細機率：三階段
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
    </section>
  );
}

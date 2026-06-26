"use client";

import { BarChart3, FileText, ShieldCheck, Stethoscope } from "lucide-react";
import type { PredictionResponse, RiskLevel } from "../lib/types";

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

type TextBlock =
  | {
      kind: "paragraph";
      text: string;
    }
  | {
      kind: "numbered";
      number: string;
      text: string;
    };

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function splitLongParagraph(text: string) {
  if (text.length <= 150) {
    return [text];
  }

  const sentences = text.match(/[^。！？]+[。！？]?/g) ?? [text];
  const groups: string[] = [];
  let current = "";

  sentences.forEach((sentence) => {
    const next = sentence.trim();
    if (!next) {
      return;
    }

    if (current && current.length + next.length > 150) {
      groups.push(current);
      current = next;
      return;
    }

    current = current ? `${current}${next}` : next;
  });

  if (current) {
    groups.push(current);
  }

  return groups.length > 0 ? groups : [text];
}

function toReadableBlocks(text: string): TextBlock[] {
  const sectionMarkers = [
    "重要提示：",
    "請務必注意：",
    "我們的建議：",
    "您可以考慮以下專科就醫：",
    "如果您",
    "若您",
    "同時，",
    "再次提醒，",
    "請務必遵循醫囑",
  ];

  let normalized = text
    .replace(/\r\n/g, "\n")
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/---+/g, "")
    .replace(/\s+/g, " ")
    .trim();

  sectionMarkers.forEach((marker) => {
    normalized = normalized.replaceAll(marker, `\n${marker}`);
  });

  normalized = normalized.replace(/\s+(\d+\.\s*)/g, "\n$1");

  const lines = normalized
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  const blocks: TextBlock[] = [];

  lines.forEach((line) => {
    const numbered = line.match(/^(\d+)\.\s*(.+)$/);

    if (numbered) {
      blocks.push({
        kind: "numbered",
        number: numbered[1],
        text: numbered[2].trim(),
      });
      return;
    }

    splitLongParagraph(line).forEach((paragraph) => {
      blocks.push({
        kind: "paragraph",
        text: paragraph,
      });
    });
  });

  return blocks;
}

function FormattedAdviceText({ text }: { text: string }) {
  const blocks = toReadableBlocks(text);

  return (
    <div className="formatted-advice">
      {blocks.map((block, index) => {
        if (block.kind === "numbered") {
          return (
            <div className="formatted-step" key={`${block.number}-${index}`}>
              <span>{block.number}</span>
              <p>{block.text}</p>
            </div>
          );
        }

        return <p key={index}>{block.text}</p>;
      })}
    </div>
  );
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
          <Stethoscope size={18} />
          AI 就診建議
        </div>
        <FormattedAdviceText text={result.care_guidance} />
      </article>

      <article className="detail-card explanation-card">
        <div className="section-kicker">
          <FileText size={18} />
          繁體中文衛教說明
        </div>
        <FormattedAdviceText text={result.explanation} />
      </article>
    </section>
  );
}

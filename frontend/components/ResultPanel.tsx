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
      kind: "heading";
      text: string;
    }
  | {
      kind: "paragraph";
      text: string;
    }
  | {
      kind: "numbered";
      number: string;
      title?: string;
      text: string;
    }
  | {
      kind: "bullet";
      title?: string;
      text: string;
    };

const SECTION_LABELS = [
  "AI 初步風險篩檢結果說明：",
  "AI初步風險篩檢結果說明：",
  "重要提示：",
  "重要提醒：",
  "請務必注意：",
  "就診建議：",
  "看哪一科：",
  "建議看診科別：",
  "急迫性：",
  "就診前可準備的資訊：",
  "哪些症狀應提早就醫：",
  "出現以下情況請立即就醫：",
  "我們的建議：",
  "您可以考慮以下專科就醫：",
  "關於口腔潛在癌前病變（OPMD）：",
  "關於口腔潛在癌前病變 (OPMD)：",
  "關於口腔癌：",
  "關於良性病變：",
  "關於正常影像：",
];

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

function cleanInlineText(text: string) {
  return text
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/^[\-•]\s*/, "")
    .replace(/\s+([，。！？；：])/g, "$1")
    .replace(/([（「『【])\s+/g, "$1")
    .replace(/\s+([）」』】])/g, "$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function splitTitle(text: string) {
  const cleaned = cleanInlineText(text);
  const match = cleaned.match(/^([^：:。！？]{2,30})[：:]\s*(.*)$/);

  if (!match) {
    return { text: cleaned };
  }

  return {
    title: match[1].trim(),
    text: match[2].trim(),
  };
}

function addBreakBeforeSectionLabel(text: string, label: string) {
  let result = text;
  let searchFrom = 0;

  while (true) {
    const index = result.indexOf(label, searchFrom);
    if (index === -1) {
      return result;
    }

    const previous = result.slice(Math.max(0, index - 36), index);
    const alreadySeparated = index === 0 || /\n\s*$/.test(previous);
    const insideNumberedTitle = /\d+\.\s*[^。！？\n]*$/.test(previous);
    const insideSentence = /[，、：:]\s*$/.test(previous);

    if (alreadySeparated || insideNumberedTitle || insideSentence) {
      searchFrom = index + label.length;
      continue;
    }

    result = `${result.slice(0, index)}\n${result.slice(index)}`;
    searchFrom = index + label.length + 1;
  }
}

function pushParagraphs(blocks: TextBlock[], text: string) {
  splitLongParagraph(cleanInlineText(text)).forEach((paragraph) => {
    if (paragraph) {
      blocks.push({
        kind: "paragraph",
        text: paragraph,
      });
    }
  });
}

function addLineAsBlocks(blocks: TextBlock[], line: string) {
  const cleaned = cleanInlineText(line);
  if (!cleaned) {
    return;
  }

  const numbered = cleaned.match(/^(\d+)\.\s*(.+)$/);
  if (numbered) {
    const item = splitTitle(numbered[2]);
    blocks.push({
      kind: "numbered",
      number: numbered[1],
      title: item.title,
      text: item.text,
    });
    return;
  }

  const bullet = line.trim().match(/^[-•]\s*(.+)$/);
  if (bullet) {
    const item = splitTitle(bullet[1]);
    blocks.push({
      kind: "bullet",
      title: item.title,
      text: item.text,
    });
    return;
  }

  const sectionLabel = SECTION_LABELS.find((label) => cleaned.startsWith(label));
  if (sectionLabel) {
    const title = cleanInlineText(sectionLabel).replace(/[，：:]\s*$/, "");
    const rest = cleaned.slice(sectionLabel.length).trim();

    blocks.push({
      kind: "heading",
      text: title,
    });

    if (rest) {
      pushParagraphs(blocks, rest);
    }
    return;
  }

  pushParagraphs(blocks, cleaned);
}

function toReadableBlocks(text: string): TextBlock[] {
  let normalized = text
    .replace(/\r\n/g, "\n")
    .replace(/---+/g, "\n")
    .replace(/\*\*([^*]+?)\*\*/g, "$1")
    .replace(/\s+\*\s+(?=\S)/g, "\n- ")
    .replace(/\s+•\s+(?=\S)/g, "\n- ")
    .replace(/\s+(\d+)\.\s+/g, "\n$1. ")
    .replace(/[ \t]+/g, " ")
    .trim();

  SECTION_LABELS.forEach((label) => {
    normalized = addBreakBeforeSectionLabel(normalized, label);
  });

  const lines = normalized
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  const blocks: TextBlock[] = [];

  lines.forEach((line) => {
    addLineAsBlocks(blocks, line);
  });

  return blocks;
}

function FormattedAdviceText({ text }: { text: string }) {
  const blocks = toReadableBlocks(text);

  return (
    <div className="formatted-advice">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return <h3 key={`${block.text}-${index}`}>{block.text}</h3>;
        }

        if (block.kind === "numbered") {
          return (
            <div className="formatted-step" key={`${block.number}-${index}`}>
              <span>{block.number}</span>
              <p>
                {block.title ? <strong>{block.title}</strong> : null}
                {block.text}
              </p>
            </div>
          );
        }

        if (block.kind === "bullet") {
          return (
            <div className="formatted-bullet" key={`${block.text}-${index}`}>
              <span aria-hidden="true" />
              <p>
                {block.title ? <strong>{block.title}</strong> : null}
                {block.text}
              </p>
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

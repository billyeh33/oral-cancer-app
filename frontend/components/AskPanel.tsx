"use client";

import { FormEvent, useRef, useState } from "react";
import { AlertCircle, LoaderCircle, MessageCircleQuestion, Send } from "lucide-react";
import { askQuestion } from "../lib/api";
import type { AskResponse, Prediction } from "../lib/types";
import { LinkedText } from "./LinkedText";
import { SourceTags, sourceLabel } from "./SourceTags";

const MAX_CHARS = 300;
const MAX_HISTORY = 5;

const SUGGESTIONS: Record<Prediction | "none", string[]> = {
  none: ["誰可以免費做口腔黏膜檢查？", "嘴巴破洞多久沒好要看醫生？", "白斑會變成口腔癌嗎？"],
  Normal: ["誰可以免費做口腔黏膜檢查？", "抽菸喝酒會增加口腔癌風險嗎？", "嘴巴破洞多久沒好要看醫生？"],
  Benign: ["嘴巴破洞多久沒好要看醫生？", "口腔破皮可以塗鹽水嗎？", "口腔黏膜破洞就是口腔癌嗎？"],
  OPMD: ["白斑會變成口腔癌嗎？", "癌前病變要去哪裡檢查？", "要怎麼查確診醫院？"],
  "Oral Cancer": ["要怎麼查確診醫院？", "切片檢查是什麼流程？", "口腔癌的危險因子有哪些？"],
};

interface Exchange {
  id: number;
  question: string;
  response: AskResponse;
}

function AnswerCard({ exchange }: { exchange: Exchange }) {
  const { question, response } = exchange;

  return (
    <article className={`ask-exchange ask-${response.status}`}>
      <p className="ask-question">{question}</p>
      <p className="ask-answer">
        <LinkedText links={response.links} text={response.answer} />
      </p>

      {response.status === "answered" && response.sources.length > 0 ? (
        <p className="report-basis">
          依據
          <SourceTags sources={response.sources} />
        </p>
      ) : null}

      {response.status === "fallback" ? (
        <ul className="ask-passages">
          {response.sources.map((source) => (
            <li key={source.chunk_id}>
              <span className="source-tag" title={source.citation}>
                {sourceLabel(source)}
              </span>
              {source.title ? <strong>{source.title}</strong> : null}
              <p>
                <LinkedText links={response.links} text={source.text} />
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

export function AskPanel({ prediction }: { prediction?: Prediction }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Exchange[]>([]);
  const nextId = useRef(0);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 2) {
      setError("請輸入至少 2 個字的問題。");
      return;
    }
    if (trimmed.length > MAX_CHARS) {
      setError(`問題請在 ${MAX_CHARS} 字以內。`);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await askQuestion(trimmed, prediction);
      const exchange = { id: nextId.current++, question: trimmed, response };
      setHistory((previous) => [exchange, ...previous].slice(0, MAX_HISTORY));
      setQuestion("");
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "衛教問答暫時無法使用，請稍後再試。");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <section className="detail-card ask-panel" aria-labelledby="ask-title">
      <div className="section-kicker" id="ask-title">
        <MessageCircleQuestion size={18} />
        衛教問答
      </div>
      <p className="ask-intro">
        回答只根據衛福部《口腔黏膜異常患者之口腔保健指導手冊》與國健署處置流程，並標示出處頁碼；資料沒有提到的問題不會回答。
      </p>

      <form className="ask-form" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="ask-input">
          輸入口腔健康問題
        </label>
        <textarea
          id="ask-input"
          maxLength={MAX_CHARS}
          onChange={(event) => {
            setQuestion(event.target.value);
            if (error) {
              setError(null);
            }
          }}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter adds a new line. Skip while composing Chinese input.
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void ask(question);
            }
          }}
          placeholder="例如：白斑會變成口腔癌嗎？"
          rows={2}
          value={question}
        />
        <div className="ask-form-footer">
          <span className="ask-count">
            {question.length}/{MAX_CHARS}
          </span>
          <button className="ask-submit" disabled={loading} type="submit">
            {loading ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}
            {loading ? "查詢中" : "送出"}
          </button>
        </div>
      </form>

      <div className="ask-suggestions" aria-label="常見問題">
        {SUGGESTIONS[prediction ?? "none"].map((suggestion) => (
          <button
            className="ask-chip"
            disabled={loading}
            key={suggestion}
            onClick={() => {
              setQuestion(suggestion);
              void ask(suggestion);
            }}
            type="button"
          >
            {suggestion}
          </button>
        ))}
      </div>

      {error ? (
        <p className="inline-error" role="alert">
          <AlertCircle size={16} />
          {error}
        </p>
      ) : null}

      {history.length > 0 ? (
        <div className="ask-history" aria-live="polite">
          {history.map((exchange) => (
            <AnswerCard exchange={exchange} key={exchange.id} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

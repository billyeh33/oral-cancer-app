export type RiskLevel = "低風險" | "中低風險" | "中高風險" | "高風險";

export interface StageProbabilities {
  stage_1: {
    Normal: number;
    Abnormal: number;
  };
  stage_2: {
    Benign: number;
    Malignant: number;
  };
  stage_3: {
    OPMD: number;
    "Oral Cancer": number;
  };
}

export interface PredictionResponse {
  prediction: "Normal" | "Benign" | "OPMD" | "Oral Cancer";
  confidence: number;
  risk_level: RiskLevel;
  class_probabilities: {
    Normal: number;
    Benign: number;
    OPMD: number;
    "Oral Cancer": number;
  };
  stage_probabilities: StageProbabilities;
  explanation: string;
  care_guidance: string;
  disclaimer: string;
}

/** /predict returns the prediction and the full result-page content together. */
export type PredictResult = PredictionResponse & ResultReport;

export type Prediction = PredictionResponse["prediction"];

/** One passage from the education documents that an answer is based on. */
export interface RagSource {
  chunk_id: string;
  source_title: string;
  publisher: string;
  file: string;
  page: number;
  chapter: string;
  section: string;
  title: string;
  text: string;
  score: number;
  /** Ready-made label, e.g. 《口腔黏膜異常患者之口腔保健指導手冊（民眾版）》第 18 頁・白斑 Leukoplakia */
  citation: string;
}

/**
 * An official lookup website named in a text (e.g. 「口腔癌確認診斷及治療醫院名單」).
 * Every occurrence of `text` in that text should become a link to `url`.
 */
export interface LookupLink {
  text: string;
  url: string;
  /** Full name and publisher, for a tooltip */
  label: string;
}

/**
 * Result-page content, one field per section (returned by /predict and /explain).
 *   結果說明 -> summary
 *   就診建議 -> care
 *   衛教說明 -> education, plus the handbook link
 */
export interface ResultReport {
  summary: string;
  care: {
    /** 看哪一科 */
    department: string;
    /** 什麼時候去看 */
    timing: string;
    /** 就診時可以帶或告訴醫師的資訊 */
    bring: string;
    /** Documents the advice is based on */
    sources: RagSource[];
    /** Lookup sites named in department / timing / bring */
    links: LookupLink[];
  };
  /** 2-3 points; may be empty if the content file is missing */
  education: {
    heading: string;
    text: string;
    sources: RagSource[];
    links: LookupLink[];
  }[];
  /** The one link on the page: the official handbook */
  handbook: {
    title: string;
    publisher: string;
    url: string;
  };
  /** false until someone has checked the education text against the handbook */
  content_reviewed: boolean;
  /** Older fields, kept for the current UI: explanation = summary; care_guidance = care as a numbered list */
  explanation: string;
  care_guidance: string;
  source: "curated";
  /** All sources above, without duplicates */
  sources: RagSource[];
}

/** @deprecated use ResultReport */
export type AdviceResponse = ResultReport;

export interface AskResponse {
  answer: string;
  /**
   * answered  - answer written from the documents; sources = passages it used
   * not_found - the documents do not cover the question; sources = []
   * fallback  - AI unavailable; answer is a notice, sources = closest passages to show instead
   */
  status: "answered" | "not_found" | "fallback";
  sources: RagSource[];
  /** Lookup sites named in the answer (or, for fallback, in the shown passages) */
  links: LookupLink[];
}

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
  disclaimer: string;
}

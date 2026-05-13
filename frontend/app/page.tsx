import Link from "next/link";
import { ArrowRight, BrainCircuit, FlaskConical, Stethoscope } from "lucide-react";
import { DisclaimerBanner } from "../components/DisclaimerBanner";
import { SiteHeader } from "../components/SiteHeader";

export default function HomePage() {
  return (
    <main>
      <SiteHeader />

      <section className="hero-section">
        <div className="hero-overlay" />
        <div className="hero-content">
          <span className="eyebrow">口腔病灶影像輔助篩檢系統</span>
          <h1>研究型 AI 初步風險篩檢</h1>
          <p>
            使用 Hierarchical ConvNeXt-Tiny 對口腔影像進行初步風險分級，
            搭配繁體中文衛教說明，適合專題展示與產學案 demo。
          </p>
          <div className="hero-actions">
            <Link className="primary-link" href="/upload">
              開始上傳分析
              <ArrowRight size={18} />
            </Link>
            <a className="secondary-link" href="#scope">
              查看系統定位
            </a>
          </div>
        </div>
      </section>

      <section className="feature-band" id="scope">
        <article>
          <FlaskConical size={22} />
          <h2>研究型 Prototype</h2>
          <p>用於展示影像 AI 流程、前後端整合與衛教說明，不作正式醫療診斷。</p>
        </article>
        <article>
          <BrainCircuit size={22} />
          <h2>三階段模型邏輯</h2>
          <p>依 Normal、Benign、OPMD、Oral Cancer 的層級路徑回傳四分類機率。</p>
        </article>
        <article>
          <Stethoscope size={22} />
          <h2>保守醫療表述</h2>
          <p>介面採保守語氣，聚焦 AI 初步風險篩檢、影像分級與建議就醫檢查。</p>
        </article>
      </section>

      <section className="home-disclaimer-wrap">
        <DisclaimerBanner />
      </section>
    </main>
  );
}

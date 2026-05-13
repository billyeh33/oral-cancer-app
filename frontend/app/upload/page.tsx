import { DisclaimerBanner } from "../../components/DisclaimerBanner";
import { SiteHeader } from "../../components/SiteHeader";
import { UploadAnalyzer } from "../../components/UploadAnalyzer";

export default function UploadPage() {
  return (
    <main className="upload-page">
      <SiteHeader />
      <section className="page-heading">
        <span className="eyebrow">AI 初步風險篩檢</span>
        <h1>上傳口腔影像，查看影像風險分級</h1>
        <p>
          系統會回傳四分類機率、三階段機率與繁體中文衛教說明。這不是正式診斷工具。
        </p>
      </section>

      <section className="upload-content">
        <UploadAnalyzer />
      </section>

      <section className="page-disclaimer-wrap">
        <DisclaimerBanner />
      </section>
    </main>
  );
}

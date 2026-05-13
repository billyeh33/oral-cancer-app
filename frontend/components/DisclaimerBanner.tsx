import { ShieldAlert } from "lucide-react";

const FULL_DISCLAIMER =
  "本系統僅作為口腔影像初步風險篩檢與衛教輔助工具，不能取代醫師診斷、病理切片或正式醫療建議。若口腔潰瘍、白斑、紅斑、腫塊或疼痛持續超過兩週，請盡快至牙科、口腔外科或耳鼻喉科就醫檢查。";

interface DisclaimerBannerProps {
  text?: string;
}

export function DisclaimerBanner({ text = FULL_DISCLAIMER }: DisclaimerBannerProps) {
  return (
    <section className="disclaimer-banner" aria-label="免責聲明">
      <ShieldAlert size={20} aria-hidden="true" />
      <p>{text}</p>
    </section>
  );
}

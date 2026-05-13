import Link from "next/link";
import { Activity, ScanSearch } from "lucide-react";

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link className="brand-lockup" href="/">
        <span className="brand-mark" aria-hidden="true">
          <Activity size={20} />
        </span>
        <span>
          <strong>口腔病灶影像輔助篩檢</strong>
          <small>Research Prototype</small>
        </span>
      </Link>

      <nav className="top-nav" aria-label="主要導覽">
        <Link href="/">首頁</Link>
        <Link className="nav-action" href="/upload">
          <ScanSearch size={16} />
          開始分析
        </Link>
      </nav>
    </header>
  );
}

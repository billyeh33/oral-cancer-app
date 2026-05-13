import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "口腔病灶影像輔助篩檢",
  description:
    "研究型 prototype，提供口腔影像 AI 初步風險篩檢與衛教說明，不取代醫師診斷。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}

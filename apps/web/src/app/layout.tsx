import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OCR Workspace - Tamil Nadu Electoral Roll OCR",
  description:
    "PaddleOCR-backed structured form extraction, verification queue, and export engine for Tamil Nadu Electoral Roll PDFs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen overflow-hidden">
        {children}
      </body>
    </html>
  );
}

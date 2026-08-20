import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Serena Batch OCR | Neural Electoral Roll Pipeline",
  description: "High-performance folder explorer and batch OCR workstation for electoral roll parsing",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('serena-theme');
                if (theme === 'light') {
                  document.documentElement.classList.remove('dark');
                } else {
                  document.documentElement.classList.add('dark');
                }
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className="bg-slate-50 dark:bg-obsidian-950 text-slate-900 dark:text-slate-100 min-h-screen selection:bg-serena-indigo selection:text-white antialiased overflow-hidden">
        <Toaster position="top-right" richColors />
        {children}
      </body>
    </html>
  );
}

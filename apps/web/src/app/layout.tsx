import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VI-MC | Voter Intelligence Management Center",
  description:
    "Enterprise AI-powered structured voter extraction, polling station intelligence, and electoral analysis platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-foreground min-h-screen overflow-hidden antialiased">
        {children}
      </body>
    </html>
  );
}

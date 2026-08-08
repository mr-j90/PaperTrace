import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "PaperTrace",
  description:
    "Agentic RAG assistant over the RAG / agents / evaluation / LLMOps slice of arXiv — every answer shows its paper trail.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-white text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
        {children}
      </body>
    </html>
  );
}

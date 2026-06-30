import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Eightfold Candidate Transformer",
  description:
    "Multi-source candidate data transformation pipeline: merge CSV, ATS JSON, GitHub, resumes, and recruiter notes into a canonical profile.",
  keywords: ["eightfold", "candidate", "transformer", "NLP", "resume parser", "ATS"],
  openGraph: {
    title: "Eightfold Candidate Transformer",
    description: "Merge multi-source candidate data into a canonical profile",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}

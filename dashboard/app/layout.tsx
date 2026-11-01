import type { Metadata } from "next";
import { Inter, Fraunces } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  title: "EdgeScout — Price-Discipline & Bet-Tracking",
  description: "Quantifies bookmaker margin and expected loss. Disciplined paper trading ledger with zero predictive spin.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable} dark`}>
      <body className="bg-charcoal-950 text-textPrimary antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "EdgeScout — Football Price Discipline & Paper Ledger",
  description: "Disciplined football odds analysis, lowest-cost shortlist, and paper trading ledger.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark font-sans">
      <body className="bg-bg-950 text-text-primary antialiased selection:bg-lemon selection:text-bg-950">
        {children}
        <Toaster
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: "#17171A",
              border: "1px solid #232327",
              color: "#F4F2EA",
              borderRadius: "12px",
            },
          }}
        />
      </body>
    </html>
  );
}

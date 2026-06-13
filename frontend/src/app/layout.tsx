import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hunter Leads",
  description: "SEC EDGAR Form D funding lead tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}

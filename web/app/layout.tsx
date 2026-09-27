import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";
import { Shell } from "@/components/shell";
import "./globals.css";

// next/font downloads at BUILD time and self-hosts the files: no font CDN at runtime (air-gap safe).
const space = Space_Grotesk({ subsets: ["latin"], variable: "--font-space", display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const jet = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jet", display: "swap" });

export const metadata: Metadata = {
  title: "EKALOG · One schema for every log",
  description: "Air-gapped, AI-assisted log normalization to OCSF with provable losslessness.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${space.variable} ${inter.variable} ${jet.variable}`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}

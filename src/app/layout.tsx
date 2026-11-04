import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vox — voice-controlled PC agent",
  description: "Voice-first PC agent with a virtual notch, tiered safety model, provider failover and an offline guarantee.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-[#07080b] text-white antialiased">{children}</body>
    </html>
  );
}

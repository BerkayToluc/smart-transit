import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Instrument_Sans } from "next/font/google";
import "./globals.css";

// Başlıklar, büyük süreler ve marka: değişken ağırlık/genişlik eksenli, karakterli bir grotesk.
const baslik = Bricolage_Grotesque({
  variable: "--font-baslik",
  subsets: ["latin", "latin-ext"],   // Türkçe karakterler (ğ ş ı İ) latin-ext içinde
  axes: ["opsz", "wdth"],
});

// Arayüz metni: sade, okunaklı, rakamları hizalı.
const govde = Instrument_Sans({
  variable: "--font-govde",
  subsets: ["latin", "latin-ext"],
});

export const metadata: Metadata = {
  title: "SmartTransit: İstanbul'da aktarmalı rota",
  description: "Metro, tramvay, Marmaray, vapur, metrobüs ve otobüsü birleştiren İstanbul rota planlayıcı.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eaf0f2" },
    { media: "(prefers-color-scheme: dark)", color: "#08141b" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" className={`${baslik.variable} ${govde.variable} h-full antialiased`}>
      <body className="h-full">{children}</body>
    </html>
  );
}

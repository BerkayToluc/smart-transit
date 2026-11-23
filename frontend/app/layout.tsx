import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Instrument_Sans } from "next/font/google";
import "./globals.css";
import PwaKayit from "@/components/rota/PwaKayit";

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
  applicationName: "smarttransit",
  appleWebApp: { capable: true, title: "smarttransit", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e8eff1" },
    { media: "(prefers-color-scheme: dark)", color: "#06121a" },
  ],
  width: "device-width",
  initialScale: 1,
};

// Sayfa boyanmadan önce kayıtlı temayı uygular (yanlış temada parlama olmasın). Depolama erişilemezse sistem teması kalır.
const ERKEN_TEMA = `try{var t=localStorage.getItem("smarttransit-tema");if(t==="acik"||t==="koyu"){document.documentElement.setAttribute("data-theme",t==="acik"?"light":"dark")}}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" className={`${baslik.variable} ${govde.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: ERKEN_TEMA }} />
      </head>
      <body className="h-full">
        {children}
        <PwaKayit />
      </body>
    </html>
  );
}

import type { MetadataRoute } from "next";

// Ana ekrana eklenebilir uygulama bildirimi (PWA). Renkler tema belirteçleriyle aynı: gündüz "Sis".
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SmartTransit: İstanbul'da aktarmalı rota",
    short_name: "smarttransit",
    description: "Metro, tramvay, Marmaray, vapur, metrobüs ve otobüsü birleştiren İstanbul rota planlayıcı.",
    lang: "tr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#e8eff1",
    theme_color: "#e8eff1",
    categories: ["travel", "navigation"],
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}

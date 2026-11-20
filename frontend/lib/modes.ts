// Mod ve hat görünümü: Türkçe adlar, hat renkleri, yazı rengi seçimi.
import type { Mod } from "@/lib/plan";

export const MODLAR: { id: Mod; ad: string; kisa: string }[] = [
  { id: "metro", ad: "Metro", kisa: "Metro" },
  { id: "tram", ad: "Tramvay", kisa: "Tramvay" },
  { id: "rail", ad: "Marmaray ve banliyö", kisa: "Marmaray" },
  { id: "ferry", ad: "Vapur", kisa: "Vapur" },
  { id: "metrobus", ad: "Metrobüs", kisa: "Metrobüs" },
  { id: "bus", ad: "Otobüs", kisa: "Otobüs" },
  { id: "funicular", ad: "Füniküler", kisa: "Füniküler" },
  { id: "cable_car", ad: "Teleferik", kisa: "Teleferik" },
];

export function modAdi(mod: string): string {
  if (mod === "walk") return "Yürüme";
  return MODLAR.find((m) => m.id === mod)?.ad ?? mod;
}

// Metro İstanbul hatlarının yaklaşık işletme renkleri (kısa ada göre). Eşleşmeyenler mod rengini alır.
const HAT_RENKLERI: [RegExp, string][] = [
  [/^M1[AB]?$/i, "#1f9bd6"],
  [/^M2A?$/i, "#00a651"],
  [/^M3A?$/i, "#00a99d"],
  [/^M4$/i, "#e4007e"],
  [/^M5$/i, "#7b3f98"],
  [/^M6$/i, "#a87b4f"],
  [/^M7$/i, "#f08cb8"],
  [/^M8$/i, "#0072bc"],
  [/^M9$/i, "#f2b705"],
  [/^M11$/i, "#8a8d91"],
  [/^T1$/i, "#0b5ba8"],
  [/^T3$/i, "#c0392b"],
  [/^T4$/i, "#f58220"],
  [/^T5$/i, "#5fae3c"],
  [/^F[123]$/i, "#8a5a2b"],
  [/^TF[12]$/i, "#8a5a2b"],
  [/marmaray/i, "#1a56a7"],
];

/** Çizgi/rozet rengi: bilinen hatta özel renk, değilse mod belirteci (CSS değişkeni). */
export function hatRengi(mod: string, kisaAd?: string | null): string {
  if (kisaAd) {
    for (const [re, renk] of HAT_RENKLERI) if (re.test(kisaAd.trim())) return renk;
  }
  return `var(--mod-${mod})`;
}

/** Rozet üzerindeki yazı rengi: açık renklerde koyu, koyularda beyaz. */
export function yaziRengi(renk: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(renk);
  if (!m) return "#ffffff";
  const n = parseInt(m[1], 16);
  const lin = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const l = 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  return l > 0.4 ? "#0c2a38" : "#ffffff";
}

/** Google Maps çizgisi CSS değişkenini çözemez; gerçek renk değerine çevirir. */
export function renkCoz(renk: string): string {
  const m = /^var\((--[a-z-_]+)\)$/.exec(renk);
  if (!m || typeof window === "undefined") return m ? "#14657f" : renk;
  return getComputedStyle(document.documentElement).getPropertyValue(m[1]).trim() || "#14657f";
}

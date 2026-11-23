"use client";
// Tema seçimi: açık / koyu / sistem. Seçim localStorage'da saklanır (erişilemezse sistem teması).
// Uygulama: <html data-theme="light|dark">; "sistem"de öznitelik yoktur ve CSS prefers-color-scheme'i izler.
import { useCallback, useSyncExternalStore } from "react";

export type TemaSecimi = "sistem" | "acik" | "koyu";
export type EtkinTema = "acik" | "koyu";

export const TEMA_ANAHTARI = "smarttransit-tema";
export const TEMA_RENGI: Record<EtkinTema, string> = { acik: "#e8eff1", koyu: "#06121a" };

const dinleyiciler = new Set<() => void>();
const bildir = () => dinleyiciler.forEach((f) => f());

export function secimOku(): TemaSecimi {
  try {
    const v = window.localStorage.getItem(TEMA_ANAHTARI);
    return v === "acik" || v === "koyu" ? v : "sistem";
  } catch {
    return "sistem"; // gizli pencere / engelli depolama
  }
}

function sistemKoyu(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** <html> özniteliğini ve tarayıcı çubuğu rengini (theme-color) seçime uydurur. */
export function temaUygula(secim: TemaSecimi): void {
  const k = document.documentElement;
  if (secim === "sistem") k.removeAttribute("data-theme");
  else k.setAttribute("data-theme", secim === "acik" ? "light" : "dark");
  const etkin: EtkinTema = secim === "sistem" ? (sistemKoyu() ? "koyu" : "acik") : secim;
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((m) => {
    if (m.dataset.orijinal === undefined) m.dataset.orijinal = m.content;
    m.content = secim === "sistem" ? (m.dataset.orijinal ?? TEMA_RENGI[etkin]) : TEMA_RENGI[etkin];
  });
}

export function temaKaydet(secim: TemaSecimi): void {
  const k = document.documentElement;
  k.classList.add("tema-gecis");
  window.setTimeout(() => k.classList.remove("tema-gecis"), 400);
  try {
    if (secim === "sistem") window.localStorage.removeItem(TEMA_ANAHTARI);
    else window.localStorage.setItem(TEMA_ANAHTARI, secim);
  } catch {
    /* depolama yoksa seçim yalnızca bu oturumda geçerli */
  }
  temaUygula(secim);
  bildir();
}

function abone(cb: () => void): () => void {
  dinleyiciler.add(cb);
  const m = window.matchMedia("(prefers-color-scheme: dark)");
  const sistemDegisti = () => {
    if (secimOku() === "sistem") temaUygula("sistem");
    cb();
  };
  const depo = (e: StorageEvent) => {
    if (e.key === TEMA_ANAHTARI || e.key === null) {
      temaUygula(secimOku());
      cb();
    }
  };
  m.addEventListener("change", sistemDegisti);
  window.addEventListener("storage", depo);
  temaUygula(secimOku()); // ilk bağlanışta theme-color'u eşitle
  return () => {
    dinleyiciler.delete(cb);
    m.removeEventListener("change", sistemDegisti);
    window.removeEventListener("storage", depo);
  };
}

/** Anlık tema: seçim ("sistem" dahil) ve gerçekten uygulanan (açık/koyu). */
export function useTema(): { secim: TemaSecimi; etkin: EtkinTema; sec: (s: TemaSecimi) => void } {
  // Tek string anlık görüntü: "<seçim>|<sistem koyu mu>" (useSyncExternalStore kararlı değer ister)
  const anlik = useSyncExternalStore(
    abone,
    () => `${secimOku()}|${sistemKoyu() ? 1 : 0}`,
    () => "sistem|0",
  );
  const [secim, sk] = anlik.split("|") as [TemaSecimi, string];
  const etkin: EtkinTema = secim === "sistem" ? (sk === "1" ? "koyu" : "acik") : secim;
  const sec = useCallback((s: TemaSecimi) => temaKaydet(s), []);
  return { secim, etkin, sec };
}

"use client";
// Kayıtlı yerler (Eve / İşe / favoriler / son aramalar): yalnızca bu cihazda, localStorage'ta. Depolama yoksa özellik gizlenir.
import { useCallback, useSyncExternalStore } from "react";
import {
  bosDepo, depoCoz, evKaydet, favoriEkle, favoriSil, isKaydet, sonEkle, sonlariSil, type Depo, type KayitliYer,
} from "@/lib/yerlerMantik";

export type { KayitliYer, Depo } from "@/lib/yerlerMantik";
export { favoriMi, yerOlustur } from "@/lib/yerlerMantik";

const ANAHTAR = "smarttransit-yerler";
const BOS = bosDepo();
const dinleyiciler = new Set<() => void>();
let onbellek: { ham: string | null; depo: Depo } = { ham: null, depo: BOS };

function oku(): string | null {
  try {
    return window.localStorage.getItem(ANAHTAR);
  } catch {
    return null;
  }
}

/** Kararlı anlık görüntü: ham metin değişmedikçe aynı nesne döner (useSyncExternalStore gereği). */
function anlik(): Depo {
  const ham = oku();
  if (ham !== onbellek.ham) onbellek = { ham, depo: depoCoz(ham) };
  return onbellek.depo;
}

function yaz(d: Depo): void {
  try {
    window.localStorage.setItem(ANAHTAR, JSON.stringify(d));
  } catch {
    /* depolama dolu/engelli: değişiklik bu oturumda uygulanmaz */
  }
  dinleyiciler.forEach((f) => f());
}

function abone(cb: () => void): () => void {
  dinleyiciler.add(cb);
  const depo = (e: StorageEvent) => {
    if (e.key === ANAHTAR || e.key === null) cb();
  };
  window.addEventListener("storage", depo);
  return () => {
    dinleyiciler.delete(cb);
    window.removeEventListener("storage", depo);
  };
}

/** Depolama gerçekten yazılabiliyor mu (gizli pencere / engelli çerez)? Değilse kaydetme düğmeleri gösterilmez. */
function yazilabilir(): boolean {
  try {
    const k = "smarttransit-deneme";
    window.localStorage.setItem(k, "1");
    window.localStorage.removeItem(k);
    return true;
  } catch {
    return false;
  }
}

export function useYerler() {
  const depo = useSyncExternalStore(abone, anlik, () => BOS);
  const kullanilabilir = useSyncExternalStore(
    () => () => {},
    yazilabilir,
    () => false,
  );
  const degistir = useCallback((f: (d: Depo) => Depo) => yaz(f(anlik())), []);
  return {
    depo,
    kullanilabilir,
    evKaydet: (y: KayitliYer | null) => degistir((d) => evKaydet(d, y)),
    isKaydet: (y: KayitliYer | null) => degistir((d) => isKaydet(d, y)),
    favoriEkle: (y: KayitliYer) => degistir((d) => favoriEkle(d, y)),
    favoriSil: (y: KayitliYer) => degistir((d) => favoriSil(d, y)),
    sonEkle: (y: KayitliYer) => degistir((d) => sonEkle(d, y)),
    sonlariSil: () => degistir(sonlariSil),
    hepsiniSil: () => yaz(bosDepo()),
  };
}

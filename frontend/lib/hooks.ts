"use client";
import { useSyncExternalStore } from "react";

/** Tarayıcı olayından beslenen değer (effect içinde setState yapmadan). */
function useOlay<T>(olay: "resize", al: () => T, sunucu: T): T {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(olay, cb);
      return () => window.removeEventListener(olay, cb);
    },
    al,
    () => sunucu,
  );
}

export function usePencereYuksekligi(): number {
  return useOlay("resize", () => window.innerHeight, 800);
}

/** CSS medya sorgusu eşleşiyor mu ("(prefers-color-scheme: dark)", "(max-width: 767px)" ...). */
export function useMedya(sorgu: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(sorgu);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(sorgu).matches,
    () => false,
  );
}

"use client";
// Google Maps betik yükleyicisi: tüm ekranlar AYNI ayarları kullanmalı (kütüphane aynı seçeneklerle bir kez yükler).
import { useEffect, useState } from "react";
import { useJsApiLoader, type Libraries } from "@react-google-maps/api";

const KUTUPHANELER: Libraries = ["places"];

export type HaritaDurumu = "yukleniyor" | "hazir" | "kullanilamiyor";

/** `kullanilamiyor`: betik yüklenemedi ya da anahtar reddedildi (gm_authFailure); arayüz yer aramasını düz girişe düşürür. */
export function useGoogleHarita(): { isLoaded: boolean; durum: HaritaDurumu } {
  const { isLoaded, loadError } = useJsApiLoader({
    id: "google-map-script",
    googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
    libraries: KUTUPHANELER,
    language: "tr",
    region: "TR",
  });
  const [anahtarHatali, setAnahtarHatali] = useState(false);
  useEffect(() => {
    const w = window as unknown as { gm_authFailure?: () => void };
    w.gm_authFailure = () => setAnahtarHatali(true);
    return () => {
      delete w.gm_authFailure;
    };
  }, []);
  const durum: HaritaDurumu = loadError || anahtarHatali ? "kullanilamiyor" : isLoaded ? "hazir" : "yukleniyor";
  return { isLoaded: durum === "hazir", durum };
}

export const ISTANBUL_MERKEZ = { lat: 41.04, lng: 28.98 };
// Aranan yerler İstanbul çevresine öncelikli olsun
export const ISTANBUL_SINIRLARI = { south: 40.8, west: 28.4, north: 41.4, east: 29.6 };

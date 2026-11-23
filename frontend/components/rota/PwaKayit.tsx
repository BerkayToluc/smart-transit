"use client";
import { useEffect } from "react";

/** Servis çalışanını yalnızca üretim sürümünde kaydeder (geliştirmede önbellek karışıklığı olmasın). */
export default function PwaKayit() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => {
      /* kayıt başarısızsa uygulama yine çalışır, yalnızca çevrimdışı kabuk olmaz */
    });
  }, []);
  return null;
}

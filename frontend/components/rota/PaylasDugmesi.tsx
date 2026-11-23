"use client";
import { useEffect, useRef, useState } from "react";
import { Paylas } from "@/components/rota/Ikonlar";

interface Props {
  baslik: string;
  /** Başlangıç "Konumum" ise bağlantıya yazılmaz; kullanıcıya söylenir */
  konumumGizli: boolean;
}

/** Rota bağlantısını paylaşır: Web Share API varsa sistem paylaşım menüsü, yoksa panoya kopyalar. */
export default function PaylasDugmesi({ baslik, konumumGizli }: Props) {
  const [durum, setDurum] = useState<"" | "kopyalandi" | "hata">("");
  const zamanlayici = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (zamanlayici.current) clearTimeout(zamanlayici.current);
  }, []);

  const bildir = (d: "kopyalandi" | "hata") => {
    setDurum(d);
    if (zamanlayici.current) clearTimeout(zamanlayici.current);
    zamanlayici.current = setTimeout(() => setDurum(""), 4000);
  };

  const paylas = async () => {
    const url = window.location.href; // adres çubuğu, plan durumuyla eşitlenmiş bağlantıdır (lib/baglanti.ts)
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: "smarttransit", text: baslik, url });
        return;
      } catch (e) {
        if ((e as Error).name === "AbortError") return; // kullanıcı vazgeçti
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      bildir("kopyalandi");
    } catch {
      bildir("hata");
    }
  };

  return (
    <div className="flex items-center gap-2">
      <span role="status" aria-live="polite" className={`text-[12px] ${durum === "hata" ? "text-hata" : "text-murekkep-2"}`}>
        {durum === "kopyalandi" && (konumumGizli ? "Bağlantı kopyalandı. Konumunuz eklenmedi." : "Bağlantı kopyalandı.")}
        {durum === "hata" && "Kopyalanamadı. Adres çubuğundaki bağlantıyı kullanın."}
      </span>
      <button
        type="button"
        onClick={() => void paylas()}
        className="inline-flex items-center gap-1.5 rounded-full border border-cizgi bg-yuzey px-3 py-1.5 text-[13px] font-semibold text-murekkep transition-colors hover:bg-yuzey-2"
      >
        <Paylas className="text-base text-bogaz" /> Rotayı paylaş
      </button>
    </div>
  );
}

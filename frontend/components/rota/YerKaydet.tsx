"use client";
import { useEffect, useRef, useState } from "react";
import { Ev, Is, Yerimi, Yildiz } from "@/components/rota/Ikonlar";
import { favoriMi, type Depo, type KayitliYer } from "@/lib/yerler";

interface Props {
  yer: KayitliYer;
  depo: Depo;
  onEv: () => void;
  onIs: () => void;
  onFavori: () => void;
  onFavoriKaldir: () => void;
}

/** Seçili yeri Eve / İşe / favori olarak kaydetme menüsü (klavye: Enter/Space açar, Esc kapatır, ok tuşları gezer). */
export default function YerKaydet({ yer, depo, onEv, onIs, onFavori, onFavoriKaldir }: Props) {
  const [acik, setAcik] = useState(false);
  const kap = useRef<HTMLDivElement>(null);
  const favori = favoriMi(depo, yer);

  useEffect(() => {
    if (!acik) return;
    const disTik = (e: MouseEvent) => {
      if (kap.current && !kap.current.contains(e.target as Node)) setAcik(false);
    };
    document.addEventListener("mousedown", disTik);
    return () => document.removeEventListener("mousedown", disTik);
  }, [acik]);

  const tus = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setAcik(false);
      kap.current?.querySelector<HTMLButtonElement>("button")?.focus();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const ogeler = [...(kap.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])];
    const i = ogeler.indexOf(document.activeElement as HTMLButtonElement);
    if (!ogeler.length) return;
    e.preventDefault();
    ogeler[(i + (e.key === "ArrowDown" ? 1 : -1) + ogeler.length) % ogeler.length]?.focus();
  };

  const sec = (yap: () => void) => () => {
    yap();
    setAcik(false);
  };

  const oge = (ikon: React.ReactNode, metin: string, yap: () => void, aktif = false) => (
    <button
      type="button"
      role="menuitem"
      onClick={sec(yap)}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[14px] font-medium text-murekkep transition-colors hover:bg-yuzey-2"
    >
      <span className="text-[17px] text-bogaz">{ikon}</span>
      <span className="flex-1">{metin}</span>
      {aktif && <span className="text-[12px] font-semibold text-bogaz">kayıtlı</span>}
    </button>
  );

  return (
    <div ref={kap} className="relative shrink-0" onKeyDown={tus}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={acik}
        aria-label="Bu yeri kaydet"
        title="Bu yeri kaydet"
        onClick={() => setAcik((a) => !a)}
        className={`grid h-10 w-10 place-items-center rounded-full text-xl transition-colors hover:bg-yuzey-2 ${favori || depo.ev?.id === yer.id || depo.is?.id === yer.id ? "text-iskele" : "text-murekkep-2"}`}
      >
        <Yerimi />
      </button>
      {acik && (
        <div role="menu" aria-label="Yeri kaydet" className="absolute right-0 top-full z-40 mt-1 w-56 rounded-2xl border border-cizgi bg-yuzey p-1.5 shadow-[var(--gol)]">
          {oge(<Ev />, "Eve olarak kaydet", onEv, depo.ev?.id === yer.id)}
          {oge(<Is />, "İşe olarak kaydet", onIs, depo.is?.id === yer.id)}
          {favori ? oge(<Yildiz />, "Favorilerden çıkar", onFavoriKaldir) : oge(<Yildiz />, "Favorilere ekle", onFavori)}
        </div>
      )}
    </div>
  );
}

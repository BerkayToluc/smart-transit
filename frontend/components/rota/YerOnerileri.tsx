"use client";
import { useEffect, useRef } from "react";
import { Ev, Is, Kapat, Saat, Yildiz } from "@/components/rota/Ikonlar";
import type { Depo, KayitliYer } from "@/lib/yerler";

interface Props {
  depo: Depo;
  onSec: (y: KayitliYer) => void;
  onEvSil: () => void;
  onIsSil: () => void;
  onFavoriSil: (y: KayitliYer) => void;
  onSonlariSil: () => void;
  onHepsiniSil: () => void;
}

/** Yer alanı boşken açılan liste: Eve, İşe, favoriler, son aramalar. Her satır tek dokunuşla alanı doldurur. */
export default function YerOnerileri({ depo, onSec, onEvSil, onIsSil, onFavoriSil, onSonlariSil, onHepsiniSil }: Props) {
  const kap = useRef<HTMLDivElement>(null);
  useEffect(() => {
    kap.current?.scrollIntoView({ block: "nearest" }); // telefonda liste çekmecenin altında kalmasın
  }, []);

  const satir = (key: string, ikon: React.ReactNode, baslik: string, alt: string, yer: KayitliYer, sil?: { etiket: string; yap: () => void }) => (
    <li key={key} className="flex items-center gap-1">
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => onSec(yer)}
        className="flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-yuzey-2"
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-yuzey-2 text-[17px] text-bogaz">{ikon}</span>
        <span className="min-w-0">
          <span className="block truncate text-[14px] font-semibold text-murekkep">{baslik}</span>
          {alt && <span className="block truncate text-[12px] text-murekkep-3">{alt}</span>}
        </span>
      </button>
      {sil && (
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={sil.yap}
          aria-label={sil.etiket}
          title={sil.etiket}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-base text-murekkep-3 transition-colors hover:bg-yuzey-2 hover:text-murekkep"
        >
          <Kapat />
        </button>
      )}
    </li>
  );

  const baslik = (m: string) => <li className="px-2.5 pb-1 pt-2 text-[12px] font-semibold text-murekkep-3">{m}</li>;

  return (
    <div
      ref={kap}
      role="region"
      aria-label="Kayıtlı yerler"
      className="absolute inset-x-0 top-full z-30 mt-1 max-h-[22rem] overflow-y-auto rounded-2xl border border-cizgi bg-yuzey p-1.5 shadow-[var(--gol)] kaydir"
    >
      <ul className="m-0 list-none p-0">
        {depo.ev && satir("ev", <Ev />, "Eve", depo.ev.ad, depo.ev, { etiket: "Ev kaydını sil", yap: onEvSil })}
        {depo.is && satir("is", <Is />, "İşe", depo.is.ad, depo.is, { etiket: "İş kaydını sil", yap: onIsSil })}
        {depo.favoriler.length > 0 && baslik("Favoriler")}
        {depo.favoriler.map((y) => satir(`f-${y.id}`, <Yildiz dolu />, y.ad, "", y, { etiket: `${y.ad} favorisini sil`, yap: () => onFavoriSil(y) }))}
        {depo.son.length > 0 && (
          <>
            <li className="flex items-center justify-between px-2.5 pb-1 pt-2 text-[12px] font-semibold text-murekkep-3">
              <span>Son aramalar</span>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={onSonlariSil}
                className="rounded-md px-1.5 py-0.5 font-semibold text-bogaz hover:underline"
              >
                Temizle
              </button>
            </li>
            {depo.son.map((y) => satir(`s-${y.id}`, <Saat />, y.ad, "", y))}
          </>
        )}
      </ul>
      <div className="mt-1 flex items-center justify-between gap-2 border-t border-cizgi px-2.5 pt-2 text-[12px] text-murekkep-3">
        <span>Yalnızca bu cihazda saklanır.</span>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={onHepsiniSil}
          className="rounded-md px-1.5 py-0.5 font-semibold text-hata hover:underline"
        >
          Kayıtlı yerleri sil
        </button>
      </div>
    </div>
  );
}

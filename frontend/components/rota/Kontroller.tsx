"use client";
import { istanbulSimdi } from "@/lib/format";
import { MODLAR } from "@/lib/modes";
import type { Mod, Tercih } from "@/lib/plan";
import { ModIkonu, Saat } from "@/components/rota/Ikonlar";

export type ZamanDurumu = { tip: "simdi" | "sec"; deger: string };

/** "Şimdi" ya da seçilen tarih-saat. datetime-local değeri (YYYY-MM-DDTHH:mm) İstanbul saati sayılır. */
export function ZamanSecici({ zaman, onDegis }: { zaman: ZamanDurumu; onDegis: (z: ZamanDurumu) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="radiogroup" aria-label="Kalkış zamanı" className="flex rounded-full bg-yuzey-2 p-1">
        {(
          [
            ["simdi", "Şimdi"],
            ["sec", "Kalkış zamanı seç"],
          ] as const
        ).map(([id, ad]) => (
          <button
            key={id}
            role="radio"
            aria-checked={zaman.tip === id}
            onClick={() => onDegis({ tip: id, deger: id === "sec" && !zaman.deger ? istanbulSimdi() : zaman.deger })}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors ${
              zaman.tip === id ? "bg-iskele text-[#2a1a00]" : "text-murekkep-2 hover:text-murekkep"
            }`}
          >
            {ad}
          </button>
        ))}
      </div>
      {zaman.tip === "sec" && (
        <label className="flex items-center gap-2 rounded-full bg-yuzey-2 py-1 pl-3 pr-1 text-sm text-murekkep-2">
          <Saat className="text-lg" />
          <span className="sr-only">Tarih ve saat</span>
          <input
            type="datetime-local"
            step={60}
            value={zaman.deger}
            onChange={(e) => onDegis({ tip: "sec", deger: e.target.value })}
            className="tnum rounded-full bg-transparent px-2 py-1 text-sm font-medium text-murekkep"
          />
        </label>
      )}
    </div>
  );
}

const TERCIHLER: { id: Tercih; ad: string }[] = [
  { id: "fastest", ad: "En hızlı" },
  { id: "fewest_transfers", ad: "Az aktarma" },
  { id: "least_walking", ad: "Az yürüme" },
];

export function TercihSecici({ tercih, onDegis }: { tercih: Tercih; onDegis: (t: Tercih) => void }) {
  return (
    <div role="radiogroup" aria-label="Sıralama" className="flex rounded-full bg-yuzey-2 p-1">
      {TERCIHLER.map((t) => (
        <button
          key={t.id}
          role="radio"
          aria-checked={tercih === t.id}
          onClick={() => onDegis(t.id)}
          className={`flex-1 rounded-full px-3 py-1.5 text-sm font-semibold transition-colors ${
            tercih === t.id ? "bg-murekkep text-yuzey" : "text-murekkep-2 hover:text-murekkep"
          }`}
        >
          {t.ad}
        </button>
      ))}
    </div>
  );
}

/** Ulaşım türü seçimi: kapalı olanlar rotada kullanılmaz. */
export function ModSecici({ secili, onDegis }: { secili: Set<Mod>; onDegis: (s: Set<Mod>) => void }) {
  const degistir = (m: Mod) => {
    const yeni = new Set(secili);
    if (yeni.has(m)) {
      if (yeni.size === 1) return; // en az bir tür açık kalmalı
      yeni.delete(m);
    } else yeni.add(m);
    onDegis(yeni);
  };
  return (
    <fieldset className="m-0 border-0 p-0">
      <legend className="sr-only">Ulaşım türleri</legend>
      <div className="flex flex-wrap gap-1.5">
        {MODLAR.map((m) => {
          const acik = secili.has(m.id);
          return (
            <button
              key={m.id}
              type="button"
              aria-pressed={acik}
              onClick={() => degistir(m.id)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                acik
                  ? "border-transparent bg-yuzey-2 text-murekkep"
                  : "border-cizgi bg-transparent text-murekkep-3 line-through decoration-murekkep-3/50"
              }`}
            >
              <span className="text-base" style={{ color: acik ? `var(--mod-${m.id})` : undefined }}>
                <ModIkonu mod={m.id} />
              </span>
              {m.kisa}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

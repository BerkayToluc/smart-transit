"use client";
import { useState } from "react";
import { istanbulSimdi } from "@/lib/format";
import { MODLAR } from "@/lib/modes";
import type { Mod, Tercih } from "@/lib/plan";
import { Asagi, ModIkonu, Saat } from "@/components/rota/Ikonlar";

export type ZamanDurumu = { tip: "simdi" | "kalkis" | "varis"; deger: string };

/** Şimdi, belirli bir kalkış anı ya da belirli bir varış anı. datetime-local değeri (YYYY-MM-DDTHH:mm) İstanbul saati sayılır. */
export function ZamanSecici({ zaman, onDegis }: { zaman: ZamanDurumu; onDegis: (z: ZamanDurumu) => void }) {
  const SECENEKLER = [
    ["simdi", "Şimdi"],
    ["kalkis", "Kalkış"],
    ["varis", "Varış"],
  ] as const;
  return (
    <div className="space-y-2">
      <div role="radiogroup" aria-label="Zaman" className="flex rounded-full bg-yuzey-2 p-1">
        {SECENEKLER.map(([id, ad]) => (
          <button
            key={id}
            role="radio"
            aria-checked={zaman.tip === id}
            onClick={() => onDegis({ tip: id, deger: id !== "simdi" && !zaman.deger ? istanbulSimdi() : zaman.deger })}
            className={`flex-1 rounded-full px-3.5 py-1.5 text-sm font-semibold transition-colors ${
              zaman.tip === id ? "bg-iskele text-[#2a1a00]" : "text-murekkep-2 hover:text-murekkep"
            }`}
          >
            {ad}
          </button>
        ))}
      </div>
      {zaman.tip !== "simdi" && (
        <label className="flex items-center gap-3 rounded-2xl bg-yuzey-2 px-3.5 py-2">
          <Saat className="shrink-0 text-xl text-murekkep-2" />
          <span className="min-w-0 flex-1">
            <span className="block text-[13px] text-murekkep-2">
              {zaman.tip === "kalkis" ? "Şu saatte yola çıkmak istiyorum" : "En geç şu saatte varmak istiyorum"}
            </span>
            <input
              type="datetime-local"
              step={60}
              value={zaman.deger}
              onChange={(e) => onDegis({ tip: zaman.tip, deger: e.target.value })}
              aria-label={zaman.tip === "kalkis" ? "Kalkış tarihi ve saati" : "Varış tarihi ve saati"}
              className="tnum mt-0.5 w-full min-w-0 rounded-md bg-transparent text-[15px] font-semibold text-murekkep"
            />
          </span>
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

/** Ulaşım türü filtresi: açılır bölüm. Kapatılan türler rotada kullanılmaz. */
export function ModSecici({ secili, onDegis }: { secili: Set<Mod>; onDegis: (s: Set<Mod>) => void }) {
  const [acik, setAcik] = useState(false);
  const kapali = MODLAR.length - secili.size;
  const degistir = (m: Mod) => {
    const yeni = new Set(secili);
    if (yeni.has(m)) {
      if (yeni.size === 1) return; // en az bir tür açık kalmalı
      yeni.delete(m);
    } else yeni.add(m);
    onDegis(yeni);
  };
  return (
    <div>
      <button
        type="button"
        aria-expanded={acik}
        onClick={() => setAcik((a) => !a)}
        className="flex w-full items-center justify-between rounded-xl bg-yuzey-2 px-3.5 py-2.5 text-left"
      >
        <span className="text-sm font-semibold text-murekkep">Ulaşım türleri</span>
        <span className="flex items-center gap-1.5 text-[13px] text-murekkep-2">
          {kapali === 0 ? "Tümü açık" : `${kapali} tür kapalı`}
          <Asagi className={`text-lg transition-transform ${acik ? "rotate-180" : ""}`} />
        </span>
      </button>
      {acik && (
        <fieldset className="m-0 mt-2.5 border-0 p-0">
          <legend className="mb-2 text-[13px] leading-relaxed text-murekkep-2">
            Rotada kullanmak istemediğiniz ulaşım türlerinin işaretini kaldırın; o türler hiç önerilmez.
          </legend>
          <div className="flex flex-wrap gap-1.5">
            {MODLAR.map((m) => {
              const acikTur = secili.has(m.id);
              return (
                <button
                  key={m.id}
                  type="button"
                  aria-pressed={acikTur}
                  onClick={() => degistir(m.id)}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                    acikTur
                      ? "border-transparent bg-yuzey-2 text-murekkep"
                      : "border-cizgi bg-transparent text-murekkep-3 line-through decoration-murekkep-3/50"
                  }`}
                >
                  <span className="text-base" style={{ color: acikTur ? `var(--mod-${m.id})` : undefined }}>
                    <ModIkonu mod={m.id} />
                  </span>
                  {m.kisa}
                </button>
              );
            })}
          </div>
          {kapali > 0 && (
            <button
              type="button"
              onClick={() => onDegis(new Set(MODLAR.map((m) => m.id)))}
              className="mt-2.5 text-[13px] font-semibold text-bogaz"
            >
              Tümünü aç
            </button>
          )}
        </fieldset>
      )}
    </div>
  );
}

"use client";
import type { CSSProperties } from "react";
import { dakika, mesafeMetni, saatMetni, sureMetni } from "@/lib/format";
import { hatRengi, modAdi, yaziRengi } from "@/lib/modes";
import type { Etap, Yolculuk } from "@/lib/plan";
import { Otobus, ModIkonu, Saat, Yurume } from "@/components/rota/Ikonlar";

export function HatRozeti({ etap, buyuk }: { etap: Etap; buyuk?: boolean }) {
  const renk = hatRengi(etap.mode, etap.route_short_name);
  const ad = etap.route_short_name || modAdi(etap.mode);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md font-bold leading-none ${buyuk ? "px-2.5 py-1.5 text-sm" : "px-2 py-1 text-xs"}`}
      style={{ background: renk, color: yaziRengi(renk) }}
    >
      <ModIkonu mod={etap.mode} className={buyuk ? "text-base" : "text-sm"} />
      <span className="tnum">{ad}</span>
    </span>
  );
}

// Hat şeması: tren içindeki istasyon şeritleri gibi; kalın hat çizgisi üzerinde duraklar.
function Satir({ saat, renk, parca, noktali, children }: {
  saat?: string;
  renk: string;
  parca: "ust" | "orta" | "alt" | "tek";
  noktali?: boolean;
  children: React.ReactNode;
}) {
  const stil = { "--renk": renk } as CSSProperties;
  const cizgi =
    parca === "ust" ? "before:top-1/2 before:bottom-0" : parca === "alt" ? "before:top-0 before:bottom-1/2" : "before:inset-y-0";
  const nokta = parca === "ust" || parca === "alt" || parca === "tek";
  return (
    <div className="grid grid-cols-[3rem_1.75rem_1fr] items-stretch gap-x-2" style={stil}>
      <div className="tnum pt-3 text-right text-sm font-semibold text-murekkep">{saat}</div>
      <div
        className={`relative ${parca !== "tek" ? "before:absolute before:left-1/2 before:-translate-x-1/2" : ""} ${parca !== "tek" ? cizgi : ""} ${
          noktali ? "before:w-0 before:border-l-[3px] before:border-dotted before:border-[var(--renk)]" : "before:w-1.5 before:bg-[var(--renk)]"
        }`}
      >
        {nokta && (
          <span className="absolute left-1/2 top-[1.05rem] z-10 h-3.5 w-3.5 -translate-x-1/2 rounded-full border-[3.5px] bg-yuzey" style={{ borderColor: renk }} />
        )}
      </div>
      <div className="min-w-0 py-2">{children}</div>
    </div>
  );
}

function Bekleme({ dk }: { dk: number }) {
  return (
    <div className="grid grid-cols-[3rem_1.75rem_1fr] gap-x-2">
      <span />
      <span className="relative">
        <span className="absolute inset-y-0 left-1/2 w-0 -translate-x-1/2 border-l-[3px] border-dotted border-cizgi" />
      </span>
      <p className="flex items-center gap-1.5 py-1 text-[13px] text-murekkep-2">
        <Saat className="text-sm" />
        {dk} dk bekleme
      </p>
    </div>
  );
}

/** Yürüme etabını doğal bir cümleyle anlatır: koordinat uçları durak değildir (stop_id yok). */
function yurumeYonu(e: Etap): string {
  const baslangic = !e.from.stop_id;
  const varis = !e.to.stop_id;
  if (baslangic && varis) return "Başlangıçtan varış noktasına";
  if (baslangic) return `${e.to.name} durağına`;
  if (varis) return `${e.from.name} durağından varış noktasına`;
  return `${e.from.name} ile ${e.to.name} arası`;
}

/** Otobüs bacağı için "Otobüsleri gör": açık olan bacağın anahtarı, açma/kapama ve açılınca gösterilecek panel. */
export interface CanliKancasi {
  acikAnahtar: string | null;
  onToggle: (anahtar: string, etap: Etap) => void;
}

export default function AdimAdim({ yolculuk, canli }: { yolculuk: Yolculuk; canli?: CanliKancasi }) {
  const { legs } = yolculuk;
  return (
    <ol className="m-0 list-none p-0" aria-label="Adım adım yolculuk">
      {legs.map((e, i) => {
        const sonraki = legs[i + 1];
        const bekle = sonraki ? dakika(sonraki.from.time) - dakika(e.to.time) : 0;
        return (
          <li key={i}>
            {e.type === "walk" ? (
              <Satir renk="var(--mod-walk)" parca="tek" noktali saat={saatMetni(e.from.time)}>
                <p className="flex items-center gap-2 text-[15px] text-murekkep">
                  <Yurume className="text-lg text-murekkep-2" />
                  <span className="font-semibold">{sureMetni(e.duration)} yürü</span>
                  {e.distance_m != null && <span className="text-murekkep-2">{mesafeMetni(e.distance_m)}</span>}
                </p>
                <p className="mt-0.5 truncate text-[13px] text-murekkep-2">{yurumeYonu(e)}</p>
              </Satir>
            ) : (
              <>
                <Satir renk={hatRengi(e.mode, e.route_short_name)} parca="ust" saat={saatMetni(e.from.time)}>
                  <p className="text-[15px] font-semibold leading-snug text-murekkep">{e.from.name}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <HatRozeti etap={e} buyuk />
                    {e.headsign && <span className="text-[13px] text-murekkep-2">{e.headsign} yönü</span>}
                  </div>
                  {canli && (e.mode === "bus" || e.mode === "metrobus") && e.from.stop_id && e.to.stop_id && (
                    <button
                      type="button"
                      aria-expanded={canli.acikAnahtar === String(i)}
                      onClick={() => canli.onToggle(String(i), e)}
                      className={`mt-2.5 inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-semibold transition-colors ${
                        canli.acikAnahtar === String(i)
                          ? "border-transparent bg-murekkep text-yuzey"
                          : "border-cizgi text-bogaz hover:border-bogaz"
                      }`}
                    >
                      <Otobus className="text-base" />
                      {canli.acikAnahtar === String(i) ? "Otobüsleri gizle" : "Otobüsleri gör"}
                    </button>
                  )}
                </Satir>
                <Satir renk={hatRengi(e.mode, e.route_short_name)} parca="orta">
                  <p className="py-1 text-[13px] text-murekkep-2">
                    {e.num_stops} durak, {sureMetni(e.duration)}
                  </p>
                </Satir>
                <Satir renk={hatRengi(e.mode, e.route_short_name)} parca="alt" saat={saatMetni(e.to.time)}>
                  <p className="text-[15px] font-semibold leading-snug text-murekkep">{e.to.name}</p>
                </Satir>
              </>
            )}
            {bekle >= 2 && sonraki && <Bekleme dk={bekle} />}
          </li>
        );
      })}
    </ol>
  );
}

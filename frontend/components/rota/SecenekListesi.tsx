"use client";
import { mesafeMetni, saatMetni, sureMetni } from "@/lib/format";
import { hatRengi, yaziRengi } from "@/lib/modes";
import type { Yolculuk } from "@/lib/plan";
import AdimAdim from "@/components/rota/AdimAdim";
import { Asagi, ModIkonu, Yurume } from "@/components/rota/Ikonlar";

function sureParcalari(sn: number): { n: number; birim: string }[] {
  const dk = Math.max(1, Math.round(sn / 60));
  if (dk < 60) return [{ n: dk, birim: "dk" }];
  const s = Math.floor(dk / 60);
  const k = dk % 60;
  return k ? [{ n: s, birim: "sa" }, { n: k, birim: "dk" }] : [{ n: s, birim: "sa" }];
}

/** Zaman şeridi: her etap süresiyle orantılı; çubuğun toplam uzunluğu en uzun seçeneğe göredir. */
export function ZamanSeridi({ y, olcek }: { y: Yolculuk; olcek: number }) {
  return (
    <div className="flex h-7 items-stretch gap-[3px]" style={{ width: `${Math.max(olcek, 0.28) * 100}%` }} aria-hidden="true">
      {y.legs.map((e, i) => {
        const agirlik = Math.max(e.duration, 150);
        if (e.type === "walk") {
          return (
            <span
              key={i}
              className="serit-parca relative flex min-w-[0.9rem] items-center justify-center text-murekkep-2"
              style={{ flex: `${agirlik} 1 0%` }}
            >
              <span className="absolute inset-x-0 top-1/2 border-t-[3px] border-dotted border-murekkep-3" />
              {e.duration >= 420 && (
                <span className="relative z-10 grid h-6 w-6 place-items-center rounded-full bg-yuzey text-sm">
                  <Yurume />
                </span>
              )}
            </span>
          );
        }
        const renk = hatRengi(e.mode, e.route_short_name);
        // Dar bölümde isim yarım kalmasın: bölümün şeritteki payı küçükse yalnızca ikon gösterilir.
        const pay = (e.duration / y.total_duration) * Math.max(olcek, 0.28);
        const adGoster = pay >= 0.2;
        return (
          <span
            key={i}
            title={`${e.route_short_name ?? ""} ${e.route_long_name ?? ""}`.trim()}
            className="serit-parca flex min-w-[2rem] items-center justify-center gap-1 overflow-hidden rounded-md px-1 text-xs font-bold"
            style={{ flex: `${agirlik} 1 0%`, background: renk, color: yaziRengi(renk) }}
          >
            <ModIkonu mod={e.mode} className="shrink-0 text-sm" />
            {adGoster && <span className="tnum min-w-0 truncate">{e.route_short_name}</span>}
          </span>
        );
      })}
    </div>
  );
}

function ozet(y: Yolculuk): string {
  const araclar = y.legs.filter((e) => e.type === "transit").map((e) => e.route_short_name || e.mode);
  return `${sureMetni(y.total_duration)}, ${saatMetni(y.departure_time)} ile ${saatMetni(y.arrival_time)} arası, ${y.transfers} aktarma, ${araclar.join(", ")}`;
}

interface Props {
  secenekler: Yolculuk[];
  secili: number;
  onSec: (i: number) => void;
}

export default function SecenekListesi({ secenekler, secili, onSec }: Props) {
  const enUzun = Math.max(...secenekler.map((s) => s.total_duration));
  const enHizli = secenekler.reduce((a, s, i) => (s.total_duration < secenekler[a].total_duration ? i : a), 0);
  const azAktarma = secenekler.reduce((a, s, i) => (s.transfers < secenekler[a].transfers ? i : a), 0);
  const enAzYuruyen = secenekler.reduce((a, s, i) => (s.walk_distance < secenekler[a].walk_distance ? i : a), 0);
  const etiket = (i: number): string | null => {
    if (secenekler.length < 2) return null;
    if (i === enHizli) return "En hızlı";
    if (i === azAktarma && secenekler[i].transfers < secenekler[enHizli].transfers) return "En az aktarma";
    if (i === enAzYuruyen && secenekler[i].walk_distance < secenekler[enHizli].walk_distance) return "En az yürüme";
    return null;
  };

  return (
    <ul className="m-0 list-none divide-y divide-cizgi p-0" aria-label="Rota seçenekleri">
      {secenekler.map((y, i) => {
        const acik = i === secili;
        const eti = etiket(i);
        return (
          <li key={i} className={acik ? "bg-yuzey" : ""}>
            <button
              type="button"
              aria-expanded={acik}
              aria-label={ozet(y)}
              onClick={() => onSec(i)}
              className="relative block w-full px-5 py-4 text-left transition-colors hover:bg-yuzey-2"
            >
              {acik && <span className="absolute inset-y-3 left-0 w-1 rounded-r-full bg-iskele" />}
              <div className="flex items-start justify-between gap-3">
                <div className="font-display flex items-baseline gap-1 leading-none">
                  {sureParcalari(y.total_duration).map((p) => (
                    <span key={p.birim} className="flex items-baseline gap-0.5">
                      <span className="tnum text-[2.1rem] font-bold">{p.n}</span>
                      <span className="mr-1 text-base font-semibold text-murekkep-2">{p.birim}</span>
                    </span>
                  ))}
                </div>
                <div className="flex flex-col items-end gap-1.5 pt-0.5">
                  <span className="tnum text-[15px] font-semibold text-murekkep">
                    {saatMetni(y.departure_time)}–{saatMetni(y.arrival_time)}
                  </span>
                  {eti && (
                    <span className="rounded-full bg-iskele-zemin px-2 py-0.5 text-xs font-semibold text-murekkep">{eti}</span>
                  )}
                </div>
              </div>
              <div className="mt-3">
                <ZamanSeridi y={y} olcek={y.total_duration / enUzun} />
              </div>
              <div className="mt-2.5 flex items-center justify-between text-[13px] text-murekkep-2">
                <span className="flex gap-4">
                  <span>{y.transfers === 0 ? "Aktarmasız" : `${y.transfers} aktarma`}</span>
                  <span>{mesafeMetni(y.walk_distance)} yürüme</span>
                </span>
                <Asagi className={`text-lg transition-transform ${acik ? "rotate-180" : ""}`} />
              </div>
            </button>
            {acik && (
              <div className="px-5 pb-5 pt-1">
                <AdimAdim yolculuk={y} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

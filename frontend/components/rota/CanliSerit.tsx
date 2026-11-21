"use client";
import { hatRengi, yaziRengi } from "@/lib/modes";
import type { Yolculuk } from "@/lib/plan";
import { Otobus } from "@/components/rota/Ikonlar";

export function otobusBacaklari(y: Yolculuk) {
  return y.legs
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => e.mode === "bus" && e.from.stop_id && e.to.stop_id); // yalnız İETT otobüsleri (metrobüs hariç)
}

interface Props {
  yolculuk: Yolculuk;
  acikAnahtar: string | null;
  onToggle: (anahtar: string, etapIndeksi: number) => void;
  panel: React.ReactNode;
}

/** Seçili rotadaki otobüs bacakları: her biri için "Otobüsleri gör". Panel burada açılır (adım listesindeki düğme de aynı paneli açar). */
export default function CanliSerit({ yolculuk, acikAnahtar, onToggle, panel }: Props) {
  const bacaklar = otobusBacaklari(yolculuk);
  if (bacaklar.length === 0) return null;
  return (
    <section aria-label="Canlı otobüsler" className="px-5 pt-5">
      <h2 className="font-display text-xl font-bold text-murekkep">Canlı otobüsler</h2>
      <p className="mt-1 text-[13px] leading-relaxed text-murekkep-2">
        Binmeniz gereken otobüslerin şu an nerede olduğunu ve durağa kaç dakikada geleceğini görün.
      </p>
      <ul className="m-0 mt-3 list-none space-y-2 p-0">
        {bacaklar.map(({ e, i }) => {
          const renk = hatRengi(e.mode, e.route_short_name);
          const acik = acikAnahtar === String(i);
          return (
            <li key={i} className="rounded-2xl bg-yuzey p-2.5 shadow-[var(--gol)]">
              <div className="flex items-center gap-3">
                <span
                  className="tnum inline-flex min-w-[3rem] justify-center rounded-md px-2 py-1.5 text-sm font-bold"
                  style={{ background: renk, color: yaziRengi(renk) }}
                >
                  {e.route_short_name || "Otobüs"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-semibold text-murekkep">{e.from.name}</p>
                  <p className="truncate text-[12px] text-murekkep-2">durağından biniş</p>
                </div>
                <button
                  type="button"
                  aria-expanded={acik}
                  onClick={() => onToggle(String(i), i)}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-3.5 py-2 text-[13px] font-semibold transition-colors ${
                    acik ? "bg-murekkep text-yuzey" : "bg-iskele text-[#2a1a00] hover:brightness-95"
                  }`}
                >
                  <Otobus className="text-base" />
                  {acik ? "Gizle" : "Otobüsleri gör"}
                </button>
              </div>
              {acik && <div className="mt-2">{panel}</div>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

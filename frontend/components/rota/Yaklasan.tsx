"use client";
import { hatRengi, yaziRengi } from "@/lib/modes";
import type { HatCanli, YaklasanYaniti } from "@/lib/plan";
import { Otobus } from "@/components/rota/Ikonlar";

function HatCipi({ hat, secili, onClick }: { hat: string; secili: boolean; onClick: () => void }) {
  const renk = hatRengi("bus", hat);
  return (
    <button
      type="button"
      aria-pressed={secili}
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border-2 px-2.5 py-1 text-[13px] font-bold transition-colors ${
        secili ? "border-iskele bg-iskele-zemin text-murekkep" : "border-transparent bg-yuzey-2 text-murekkep-2 hover:text-murekkep"
      }`}
    >
      <span className="h-2.5 w-2.5 rounded-full" style={{ background: renk }} aria-hidden="true" />
      <span className="tnum">{hat}</span>
    </button>
  );
}

function HatRozetiKucuk({ hat }: { hat: string }) {
  const renk = hatRengi("bus", hat);
  return (
    <span className="tnum inline-flex min-w-[2.6rem] justify-center rounded-md px-2 py-1 text-xs font-bold" style={{ background: renk, color: yaziRengi(renk) }}>
      {hat}
    </span>
  );
}

interface Props {
  veri: YaklasanYaniti | null;
  yukleniyor: boolean;
  hata: string | null;
  secilenHatlar: string[];
  hepsi: boolean;
  onHat: (hat: string) => void;
  onHepsi: () => void;
}

/** Bir otobüs bacağı için: o iki durak arasında giden hatlar ve canlı araçların biniş durağına kalan süresi. */
export default function YaklasanPanel({ veri, yukleniyor, hata, secilenHatlar, hepsi, onHat, onHepsi }: Props) {
  const gorunen: HatCanli[] = veri ? veri.hatlar.filter((h) => hepsi || secilenHatlar.includes(h.hat)) : [];
  const satirlar = gorunen
    .flatMap((h) => h.araclar.map((a) => ({ ...a, hat: h.hat })))
    .sort((a, b) => a.dakika - b.dakika)
    .slice(0, 12);
  const araciOlmayanlar = gorunen.filter((h) => h.araclar.length === 0);
  const servisYok = gorunen.some((h) => h.canli_erisilemiyor);

  return (
    <div className="mt-1 rounded-2xl bg-yuzey-2 p-3.5" aria-live="polite" aria-busy={yukleniyor}>
      {veri && (
        <>
          <p className="text-[13px] leading-relaxed text-murekkep-2">
            <span className="font-semibold text-murekkep">{veri.binis.name}</span> durağından{" "}
            <span className="font-semibold text-murekkep">{veri.inis.name}</span> durağına giden hatlar. Seçtiğiniz hatların tüm
            araçları haritada görünür.
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5" role="group" aria-label="Hatlar">
            <button
              type="button"
              aria-pressed={hepsi}
              onClick={onHepsi}
              className={`rounded-full border-2 px-2.5 py-1 text-[13px] font-bold transition-colors ${
                hepsi ? "border-iskele bg-iskele-zemin text-murekkep" : "border-transparent bg-yuzey text-murekkep-2 hover:text-murekkep"
              }`}
            >
              Hepsi
            </button>
            {veri.hat_adlari.map((h) => (
              <HatCipi key={h} hat={h} secili={!hepsi && secilenHatlar.includes(h)} onClick={() => onHat(h)} />
            ))}
          </div>
        </>
      )}

      {!veri && yukleniyor && <p className="text-sm text-murekkep-2">Canlı araçlar aranıyor…</p>}
      {hata && (
        <p role="alert" className="text-sm text-hata">
          {hata}
        </p>
      )}

      {veri && satirlar.length > 0 && (
        <ul className="m-0 mt-3 list-none divide-y divide-cizgi p-0" aria-label="Yaklaşan otobüsler">
          {satirlar.map((a) => (
            <li key={`${a.hat}-${a.kapi_no}`} className="flex items-center gap-3 py-2.5">
              <HatRozetiKucuk hat={a.hat} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] text-murekkep-2">
                  Kapı <span className="tnum font-semibold text-murekkep">{a.kapi_no}</span>
                </p>
                <p className="truncate text-[12px] text-murekkep-3">
                  {a.mesafe_km < 0.2 ? "Durakta" : `${a.mesafe_km.toFixed(1).replace(".", ",")} km uzakta`}
                  {a.yon ? `, ${a.yon}` : ""}
                </p>
              </div>
              <p className="font-display tnum shrink-0 text-right leading-none">
                <span className="text-[1.6rem] font-bold">{a.dakika}</span>
                <span className="ml-0.5 text-sm font-semibold text-murekkep-2">dk</span>
              </p>
            </li>
          ))}
        </ul>
      )}

      {veri && servisYok && (
        <p role="status" className="mt-3 text-sm text-hata">
          Canlı araç verisi (İETT) şu an alınamıyor; aşağıda yalnızca planlı seferler görünür. Biraz sonra tekrar denenir.
        </p>
      )}
      {veri && gorunen.length > 0 && satirlar.length === 0 && !servisYok && (
        <p className="mt-3 text-sm text-murekkep">Seçili hatlarda şu an durağınıza yaklaşan canlı araç yok.</p>
      )}
      {araciOlmayanlar.map((h) => (
        <p key={h.hat} className="mt-1.5 text-[13px] text-murekkep-2">
          <span className="tnum font-semibold text-murekkep">{h.hat}</span>
          {h.planli.length > 0 ? `: planlı kalkış ${h.planli.join(", ")}` : ": bugün başka sefer görünmüyor"}
        </p>
      ))}

      {veri && gorunen[0]?.sure_dk != null && satirlar.length > 0 && (
        <p className="mt-2 flex items-center gap-1.5 text-[12px] text-murekkep-3">
          <Otobus className="text-sm" />
          Biniş ile iniş arası tarifede yaklaşık {gorunen[0].sure_dk} dk.
        </p>
      )}
      <p className="mt-2 flex items-center gap-1.5 text-[12px] text-murekkep-3">
        <span className="h-2 w-2 rounded-full bg-[var(--mod-bus)] motion-safe:animate-pulse" aria-hidden="true" />
        Canlı veri, 10 saniyede bir yenilenir.
      </p>
    </div>
  );
}

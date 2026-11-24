"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ModIkonu, Yildiz, Yurume } from "@/components/rota/Ikonlar";
import TemaSecici from "@/components/rota/TemaSecici";
import { baglantiOlustur } from "@/lib/baglanti";
import { hatRengi, modAdi, yaziRengi } from "@/lib/modes";
import { durakKalkislariIste, PlanHatasi, type DurakKalkis, type DurakYaniti } from "@/lib/plan";
import { favoriMi, useYerler, yerOlustur } from "@/lib/yerler";

const YENILEME_MS = 15000;
const ADIM = 12;

function HatRozeti({ hat, mod }: { hat: string; mod: string }) {
  const renk = hatRengi(mod, hat);
  return (
    <span className="tnum inline-flex min-w-[3rem] justify-center rounded-md px-2 py-1 text-[13px] font-bold" style={{ background: renk, color: yaziRengi(renk) }}>
      {hat}
    </span>
  );
}

function Satir({ k }: { k: DurakKalkis }) {
  const canli = k.canli[0];
  const sonraki = k.planli[0];
  const buyuk = canli ? canli.dakika : sonraki?.dk;
  const ileriki = k.planli.slice(canli ? 0 : 1).map((p) => p.saat).join(", ");
  return (
    <li className="flex items-center gap-3 py-3">
      <HatRozeti hat={k.hat} mod={k.mod} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-semibold text-murekkep">{k.yon} yönü</p>
        {canli && (
          <p className="truncate text-[12px] text-murekkep-3">
            Kapı {canli.kapi_no}, {canli.mesafe_km < 0.2 ? "durakta" : `${canli.mesafe_km.toFixed(1).replace(".", ",")} km uzakta`}
          </p>
        )}
        {ileriki && (
          <p className="truncate text-[12px] text-murekkep-3">
            {canli ? "Tarifede" : "Sonra"}: {ileriki}
          </p>
        )}
      </div>
      {buyuk !== undefined && (
        <p className="shrink-0 text-right leading-none">
          <span className="font-display tnum text-[1.7rem] font-bold text-murekkep">{buyuk < 1 ? "şimdi" : buyuk}</span>
          {buyuk >= 1 && <span className="ml-0.5 text-sm font-semibold text-murekkep-2">dk</span>}
          <span className={`mt-1 flex items-center justify-end gap-1 text-[11px] font-semibold ${canli ? "text-[var(--mod-bus)]" : "text-murekkep-3"}`}>
            {canli && <span className="h-1.5 w-1.5 rounded-full bg-[var(--mod-bus)] motion-safe:animate-pulse" aria-hidden="true" />}
            {canli ? "canlı" : sonraki ? sonraki.saat : ""}
          </span>
        </p>
      )}
    </li>
  );
}

/** Bir durağın sayfası: geçen hatlar, sıradaki planlı kalkışlar, otobüslerde canlı kalan dakika (15 sn'de bir yenilenir). */
export default function DurakSayfasi({ id }: { id: string }) {
  const [limit, setLimit] = useState(ADIM);
  const [veri, setVeri] = useState<{ anahtar: string; yanit: DurakYaniti | null; hata: string | null } | null>(null);
  const [tekrar, setTekrar] = useState(0);
  const yerler = useYerler();
  const anahtar = `${id}|${limit}|${tekrar}`;

  useEffect(() => {
    const ac = new AbortController();
    const getir = async () => {
      try {
        const yanit = await durakKalkislariIste(id, limit, ac.signal);
        setVeri({ anahtar, yanit, hata: null });
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setVeri((onceki) => ({ anahtar, yanit: onceki?.yanit ?? null, hata: e instanceof PlanHatasi ? e.message : "Beklenmeyen bir hata oluştu." }));
      }
    };
    void getir();
    const aralik = setInterval(() => {
      if (document.visibilityState === "visible") void getir();
    }, YENILEME_MS);
    return () => {
      ac.abort();
      clearInterval(aralik);
    };
  }, [id, limit, tekrar, anahtar]);

  const yanit = veri?.yanit ?? null;
  const yukleniyor = !veri || (veri.anahtar !== anahtar && !veri.hata);
  const durak = yanit?.stop;
  useEffect(() => {
    if (durak) document.title = `${durak.name}: smarttransit`;
  }, [durak]);

  const yer = durak ? yerOlustur(durak.name, durak.lat, durak.lng) : null;
  const favori = yer ? favoriMi(yerler.depo, yer) : false;
  const gitBaglanti = (yon: "from" | "to") =>
    durak
      ? baglantiOlustur({
          bas: yon === "from" ? { lat: durak.lat, lng: durak.lng, ad: durak.name } : null,
          bit: yon === "to" ? { lat: durak.lat, lng: durak.lng, ad: durak.name } : null,
          zaman: { tip: "simdi", deger: "" }, tercih: "fastest", modlar: null, maxYurume: 800,
        })
      : "";

  return (
    <main className="mx-auto min-h-full max-w-xl px-5 pb-16 pt-5">
      <div className="flex items-center justify-between gap-3">
        <Link href="/" className="rounded-full px-1 py-1.5 text-[14px] font-semibold text-bogaz hover:underline">
          ← Rota planla
        </Link>
        <TemaSecici />
      </div>

      {durak ? (
        <header className="mt-5">
          <div className="flex items-start justify-between gap-3">
            <h1 className="font-display text-[1.9rem] font-extrabold leading-[1.1] text-murekkep">{durak.name}</h1>
            {yer && yerler.kullanilabilir && (
              <button
                type="button"
                aria-pressed={favori}
                aria-label={favori ? "Favorilerden çıkar" : "Favorilere ekle"}
                title={favori ? "Favorilerden çıkar" : "Favorilere ekle"}
                onClick={() => (favori ? yerler.favoriSil(yer) : yerler.favoriEkle(yer))}
                className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-[22px] transition-colors hover:bg-yuzey-2 ${favori ? "text-iskele" : "text-murekkep-2"}`}
              >
                <Yildiz dolu={favori} />
              </button>
            )}
          </div>
          <ul className="mt-3 flex list-none flex-wrap gap-1.5 p-0" aria-label="Duraktaki ulaşım türleri">
            {durak.modes.map((m) => (
              <li key={m} className="inline-flex items-center gap-1.5 rounded-full bg-yuzey px-2.5 py-1 text-[12px] font-semibold text-murekkep-2">
                <ModIkonu mod={m} className="text-sm" /> {modAdi(m)}
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href={`/${gitBaglanti("from")}`} className="inline-flex items-center gap-1.5 rounded-full bg-iskele px-4 py-2 text-[14px] font-semibold text-[#2a1a00]">
              <Yurume className="text-base" /> Buradan git
            </Link>
            <Link href={`/${gitBaglanti("to")}`} className="inline-flex items-center gap-1.5 rounded-full border border-cizgi bg-yuzey px-4 py-2 text-[14px] font-semibold text-murekkep">
              Buraya git
            </Link>
          </div>
        </header>
      ) : (
        <div className="mt-5 h-24 animate-pulse rounded-2xl bg-yuzey" aria-hidden="true" />
      )}

      <section aria-label="Kalkışlar" aria-busy={yukleniyor} aria-live="polite" className="mt-6">
        {veri?.hata && (
          <div role="alert" className="rounded-2xl bg-hata-zemin p-4 text-hata">
            <p className="text-[15px] font-semibold">Durak bilgisi alınamadı</p>
            <p className="mt-1 text-sm leading-relaxed">{veri.hata}</p>
            <button type="button" onClick={() => { setVeri(null); setTekrar((t) => t + 1); }} className="mt-3 rounded-full border border-current px-3.5 py-1.5 text-sm font-semibold">
              Tekrar dene
            </button>
          </div>
        )}
        {!veri && <div className="space-y-2" aria-hidden="true">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-xl bg-yuzey" />)}</div>}
        {yanit?.canli_erisilemiyor && (
          <p role="status" className="mb-3 rounded-xl bg-yuzey-2 px-3.5 py-2.5 text-[13px] text-hata">
            Canlı otobüs verisi (İETT) şu an alınamıyor; yalnızca planlı kalkışlar gösteriliyor.
          </p>
        )}
        {yanit && yanit.departures.length > 0 && (
          <ul className="m-0 list-none divide-y divide-cizgi rounded-2xl bg-yuzey px-4 shadow-[var(--gol)]" aria-label="Duraktan kalkan hatlar">
            {yanit.departures.map((k) => <Satir key={`${k.hat}-${k.yon}`} k={k} />)}
          </ul>
        )}
        {yanit && yanit.departures.length === 0 && (
          <p className="rounded-2xl bg-yuzey p-4 text-[14px] text-murekkep">Bugün bu duraktan başka kalkış görünmüyor. Bu durak yalnızca iniş için olabilir ya da bugünkü seferler bitmiş olabilir.</p>
        )}
        {yanit && yanit.toplam_hat > yanit.departures.length && limit < 30 && (
          <button type="button" onClick={() => setLimit((l) => Math.min(30, l + ADIM))} className="mt-3 w-full rounded-full border border-cizgi bg-yuzey px-4 py-2.5 text-[14px] font-semibold text-murekkep hover:bg-yuzey-2">
            {yanit.toplam_hat - yanit.departures.length} hat daha göster
          </button>
        )}
        {yanit && yanit.departures.length > 0 && (
          <p className="mt-3 text-[12px] leading-relaxed text-murekkep-3">
            Saatler tarifedir. Canlı kalan süre yalnızca otobüslerde gösterilir ve 15 saniyede bir yenilenir.
          </p>
        )}
      </section>
    </main>
  );
}

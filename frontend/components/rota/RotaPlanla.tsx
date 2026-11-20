"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useGoogleHarita } from "@/lib/google";
import { MODLAR } from "@/lib/modes";
import { PlanHatasi, planIste, type Mod, type Nokta, type PlanYaniti, type Tercih } from "@/lib/plan";
import HaritaHataSiniri from "@/components/rota/HaritaHataSiniri";
import Cekmece, { type Olcu } from "@/components/rota/Cekmece";
import { ModSecici, TercihSecici, ZamanSecici, type ZamanDurumu } from "@/components/rota/Kontroller";
import { Asagi, Degistir, Uyari } from "@/components/rota/Ikonlar";
import RotaHaritasi from "@/components/rota/RotaHaritasi";
import SecenekListesi from "@/components/rota/SecenekListesi";
import YerAlani from "@/components/rota/YerAlani";

interface Yer {
  metin: string;
  nokta: Nokta | null;
}
const BOS: Yer = { metin: "", nokta: null };

// Tek dokunuşla denenebilen örnekler (ilk açılışta boş ekran yerine)
const ORNEKLER: { ad: string; bas: Nokta & { name: string }; bit: Nokta & { name: string } }[] = [
  { ad: "Kadıköy ile Taksim", bas: { lat: 40.9905, lng: 29.02, name: "Kadıköy" }, bit: { lat: 41.037, lng: 28.985, name: "Taksim" } },
  { ad: "Üsküdar ile Sirkeci", bas: { lat: 41.026, lng: 29.014, name: "Üsküdar" }, bit: { lat: 41.014, lng: 28.977, name: "Sirkeci" } },
  { ad: "Bostancı ile Beşiktaş", bas: { lat: 40.952, lng: 29.095, name: "Bostancı" }, bit: { lat: 41.0415, lng: 29.0075, name: "Beşiktaş" } },
];

export default function RotaPlanla() {
  const { isLoaded, durum } = useGoogleHarita();
  const [bas, setBas] = useState<Yer>(BOS);
  const [bit, setBit] = useState<Yer>(BOS);
  const [zaman, setZaman] = useState<ZamanDurumu>({ tip: "simdi", deger: "" });
  const [tercih, setTercih] = useState<Tercih>("fastest");
  const [modlar, setModlar] = useState<Set<Mod>>(() => new Set(MODLAR.map((m) => m.id)));
  const [maxYurume, setMaxYurume] = useState(800);
  const [tekrar, setTekrar] = useState(0);
  const [tercihAcik, setTercihAcik] = useState(false);
  const sonucRef = useRef<HTMLElement>(null);
  // Son tamamlanan istek ve sonucu; `istek` ile eşleşmiyorsa hesaplama sürüyor demektir (türetilmiş durum).
  const [veri, setVeri] = useState<{ istek: object; sonuc: PlanYaniti | null; hata: string | null } | null>(null);
  const [secili, setSecili] = useState(0);
  const [detayAcik, setDetayAcik] = useState(true);
  const [olcu, setOlcu] = useState<Olcu>({ sol: 416, alt: 0 });
  const [konumHatasi, setKonumHatasi] = useState<string | null>(null);

  const istek = useMemo(() => {
    if (!bas.nokta || !bit.nokta) return null;
    return {
      origin: { lat: bas.nokta.lat, lng: bas.nokta.lng, name: bas.nokta.name },
      dest: { lat: bit.nokta.lat, lng: bit.nokta.lng, name: bit.nokta.name },
      depart_at: zaman.tip === "sec" && zaman.deger ? `${zaman.deger}:00+03:00` : undefined,
      modes: modlar.size === MODLAR.length ? undefined : ([...modlar] as Mod[]),
      preference: tercih,
      max_walk_m: maxYurume,
      max_results: 4,
    };
  }, [bas.nokta, bit.nokta, zaman, modlar, tercih, maxYurume]);

  // Giriş değişince (kısa bir bekleyişle) rotayı yeniden hesapla; eski istek iptal edilir.
  useEffect(() => {
    if (!istek) return;
    const ac = new AbortController();
    const zamanlayici = setTimeout(async () => {
      try {
        const yanit = await planIste(istek, ac.signal);
        setVeri({ istek, sonuc: yanit, hata: null });
        setSecili(0);
        setDetayAcik(true);
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setVeri({ istek, sonuc: null, hata: e instanceof PlanHatasi ? e.message : "Beklenmeyen bir hata oluştu." });
      }
    }, 250);
    return () => {
      clearTimeout(zamanlayici);
      ac.abort();
    };
  }, [istek, tekrar]);   // tekrar: "Tekrar dene" aynı isteği yeniden çalıştırır

  const yukleniyor = istek !== null && veri?.istek !== istek;
  const sonuc = istek ? (veri?.sonuc ?? null) : null;
  const hata = istek && !yukleniyor ? (veri?.hata ?? null) : null;

  const degistir = () => {
    setBas(bit);
    setBit(bas);
  };

  const konumum = useCallback(() => {
    setKonumHatasi(null);
    if (!navigator.geolocation) {
      setKonumHatasi("Bu tarayıcı konum bilgisini vermiyor.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => setBas({ metin: "Konumum", nokta: { lat: p.coords.latitude, lng: p.coords.longitude, name: "Konumum" } }),
      () => setKonumHatasi("Konumunuza erişilemedi. Tarayıcı ayarlarından konum iznini açın."),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }, []);

  // Yeni sonuçlar gelince liste görünür olsun (telefonda çekmecenin altında kalmasın)
  useEffect(() => {
    if (veri?.sonuc?.itineraries.length) sonucRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [veri]);

  const yolculuk = sonuc?.itineraries[secili] ?? null;
  const sonucVar = !!sonuc && sonuc.itineraries.length > 0;

  return (
    <>
      <HaritaHataSiniri>
        <RotaHaritasi durum={durum} yolculuk={yolculuk} baslangic={bas.nokta} varis={bit.nokta} olcu={olcu} />
      </HaritaHataSiniri>
      <Cekmece onOlcu={setOlcu}>
        <div className="kaydir flex-1 overflow-y-auto pb-6" >
          <header className="px-5 pb-1 pt-1 md:pt-14">
            <h1 className="font-display text-[1.7rem] font-extrabold leading-none text-murekkep">smarttransit</h1>
            <p className="mt-1.5 hidden text-[15px] text-murekkep-2 md:block">Metro, tramvay, Marmaray, vapur ve otobüsle İstanbul&apos;da nereye gidiyorsunuz?</p>
          </header>

          <section aria-label="Nereden nereye" className="px-5 pt-4">
            <div className="flex items-stretch gap-1 rounded-2xl bg-yuzey p-2 shadow-[var(--gol)]">
              <div className="relative flex w-7 shrink-0 flex-col items-center justify-center" aria-hidden="true">
                <span className="h-3 w-3 rounded-full border-[3px] border-murekkep bg-yuzey" />
                <span className="my-1 h-7 w-0 border-l-[3px] border-dotted border-murekkep-3" />
                <span className="h-3 w-3 rounded-[3px] bg-iskele ring-[3px] ring-murekkep ring-inset" />
              </div>
              <div className="min-w-0 flex-1 divide-y divide-cizgi">
                <YerAlani
                  id="nereden"
                  etiket="Nereden"
                  yerTutucu="Nereden: adres, yer ya da enlem,boylam"
                  deger={bas.metin}
                  googleHazir={isLoaded}
                  onDeger={(metin) => setBas((y) => ({ ...y, metin }))}
                  onSecim={(nokta) => setBas((y) => ({ ...y, nokta }))}
                  konumumDestegi
                  onKonumum={konumum}
                />
                <YerAlani
                  id="nereye"
                  etiket="Nereye"
                  yerTutucu="Nereye"
                  deger={bit.metin}
                  googleHazir={isLoaded}
                  onDeger={(metin) => setBit((y) => ({ ...y, metin }))}
                  onSecim={(nokta) => setBit((y) => ({ ...y, nokta }))}
                />
              </div>
              <button
                type="button"
                onClick={degistir}
                aria-label="Başlangıç ve varışı değiştir"
                title="Başlangıç ve varışı değiştir"
                className="my-auto grid h-11 w-11 shrink-0 place-items-center rounded-full text-xl text-bogaz transition-colors hover:bg-yuzey-2"
              >
                <Degistir />
              </button>
            </div>
            {konumHatasi && (
              <p role="alert" className="mt-2 text-[13px] text-hata">
                {konumHatasi}
              </p>
            )}
          </section>

          <section aria-label="Zaman ve tercihler" className="space-y-3 px-5 pt-4">
            <ZamanSecici zaman={zaman} onDegis={setZaman} />
            <button
              type="button"
              aria-expanded={tercihAcik}
              onClick={() => setTercihAcik((a) => !a)}
              className="flex items-center gap-1.5 text-sm font-semibold text-bogaz md:hidden"
            >
              Sıralama ve ulaşım türleri
              <Asagi className={`text-lg transition-transform ${tercihAcik ? "rotate-180" : ""}`} />
            </button>
            <div className={`space-y-3 ${tercihAcik ? "block" : "hidden md:block"}`}>
              <TercihSecici tercih={tercih} onDegis={setTercih} />
              <ModSecici secili={modlar} onDegis={setModlar} />
            </div>
          </section>

          <section ref={sonucRef} aria-live="polite" aria-busy={yukleniyor} className="mt-5">
            {!istek && (
              <div className="px-5">
                <p className="text-[15px] font-semibold text-murekkep">Hemen deneyin</p>
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {ORNEKLER.map((o) => (
                    <button
                      key={o.ad}
                      type="button"
                      onClick={() => {
                        setBas({ metin: o.bas.name, nokta: o.bas });
                        setBit({ metin: o.bit.name, nokta: o.bit });
                      }}
                      className="rounded-full border border-cizgi bg-yuzey px-3.5 py-2 text-sm font-medium text-murekkep transition-colors hover:border-bogaz hover:text-bogaz"
                    >
                      {o.ad}
                    </button>
                  ))}
                </div>
                <p className="mt-4 text-[13px] leading-relaxed text-murekkep-2">
                  Başlangıç ve varışı yazıp listeden seçin ya da <span className="tnum">41.037, 28.985</span> gibi bir koordinat girin.
                </p>
              </div>
            )}

            {istek && yukleniyor && !sonuc && <YuklemeIskeleti />}

            {hata && (
              <div role="alert" className="mx-5 flex gap-3 rounded-2xl bg-hata-zemin p-4 text-hata">
                <Uyari className="mt-0.5 shrink-0 text-xl" />
                <div className="min-w-0">
                  <p className="text-[15px] font-semibold">Rota hesaplanamadı</p>
                  <p className="mt-1 text-sm leading-relaxed">{hata}</p>
                  <button
                    type="button"
                    onClick={() => {
                      setVeri(null);
                      setTekrar((t) => t + 1);
                    }}
                    className="mt-3 rounded-full border border-current px-3.5 py-1.5 text-sm font-semibold"
                  >
                    Tekrar dene
                  </button>
                </div>
              </div>
            )}

            {sonuc && !sonucVar && (
              <div className="mx-5 rounded-2xl bg-yuzey p-4">
                <p className="text-[15px] font-semibold text-murekkep">Bu iki nokta arasında rota yok</p>
                <p className="mt-1 text-sm leading-relaxed text-murekkep-2">{sonuc.mesaj}</p>
                {(sonuc.neden === "baslangicta_durak_yok" || sonuc.neden === "varista_durak_yok") && maxYurume < 1500 && (
                  <button
                    type="button"
                    onClick={() => setMaxYurume(1500)}
                    className="mt-3 rounded-full bg-murekkep px-3.5 py-2 text-sm font-semibold text-yuzey"
                  >
                    1,5 km yürümeyi de dene
                  </button>
                )}
                {sonuc.neden === "baglanti_yok" && modlar.size < MODLAR.length && (
                  <button
                    type="button"
                    onClick={() => setModlar(new Set(MODLAR.map((m) => m.id)))}
                    className="mt-3 rounded-full bg-murekkep px-3.5 py-2 text-sm font-semibold text-yuzey"
                  >
                    Tüm ulaşım türlerini aç
                  </button>
                )}
              </div>
            )}

            {sonucVar && sonuc && (
              <div className={`mt-1 transition-opacity ${yukleniyor ? "opacity-60" : ""}`}>
                <h2 className="px-5 pb-2 text-sm font-semibold text-murekkep-2">
                  {sonuc.itineraries.length} seçenek
                </h2>
                <div className="border-y border-cizgi bg-yuzey">
                  <SecenekListesi
                    secenekler={sonuc.itineraries}
                    secili={secili}
                    detayAcik={detayAcik}
                    onSec={(i) => {
                      if (i === secili) setDetayAcik((a) => !a); // seçili karta tekrar basınca aç/kapa
                      else {
                        setSecili(i);
                        setDetayAcik(true);
                      }
                    }}
                  />
                </div>
              </div>
            )}
          </section>
        </div>
      </Cekmece>
    </>
  );
}

function YuklemeIskeleti() {
  return (
    <div className="px-5" role="status" aria-label="Rotalar hesaplanıyor">
      {[0, 1].map((i) => (
        <div key={i} className="mb-3 animate-pulse rounded-2xl bg-yuzey p-4">
          <div className="h-8 w-24 rounded-lg bg-cizgi" />
          <div className="mt-4 flex gap-1">
            <div className="h-7 w-10 rounded-md bg-cizgi" />
            <div className="h-7 flex-1 rounded-md bg-cizgi" />
            <div className="h-7 w-14 rounded-md bg-cizgi" />
          </div>
        </div>
      ))}
    </div>
  );
}


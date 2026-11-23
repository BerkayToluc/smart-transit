"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useGoogleHarita } from "@/lib/google";
import { MODLAR } from "@/lib/modes";
import {
  PlanHatasi, planIste, yaklasanIste, type Etap, type Mod, type Nokta, type PlanYaniti, type Tercih, type YaklasanYaniti,
} from "@/lib/plan";
import HaritaHataSiniri from "@/components/rota/HaritaHataSiniri";
import Cekmece, { type Olcu } from "@/components/rota/Cekmece";
import { ModSecici, TercihSecici, ZamanSecici, type ZamanDurumu } from "@/components/rota/Kontroller";
import { Degistir, Ev, Is, Uyari } from "@/components/rota/Ikonlar";
import RotaHaritasi from "@/components/rota/RotaHaritasi";
import SecenekListesi from "@/components/rota/SecenekListesi";
import CanliSerit from "@/components/rota/CanliSerit";
import YaklasanPanel from "@/components/rota/Yaklasan";
import PaylasDugmesi from "@/components/rota/PaylasDugmesi";
import TemaSecici from "@/components/rota/TemaSecici";
import { baglantiCoz, baglantiOlustur, type UrlDurum, type UrlYer } from "@/lib/baglanti";
import { useYerler, yerOlustur } from "@/lib/yerler";
import YerAlani from "@/components/rota/YerAlani";

interface Yer {
  metin: string;
  nokta: Nokta | null;
}
const BOS: Yer = { metin: "", nokta: null };

export default function RotaPlanla() {
  const { isLoaded, durum } = useGoogleHarita();
  const [bas, setBas] = useState<Yer>(BOS);
  const [bit, setBit] = useState<Yer>(BOS);
  const [zaman, setZaman] = useState<ZamanDurumu>({ tip: "simdi", deger: "" });
  const [tercih, setTercih] = useState<Tercih>("fastest");
  const [modlar, setModlar] = useState<Set<Mod>>(() => new Set(MODLAR.map((m) => m.id)));
  const [maxYurume, setMaxYurume] = useState(800);
  const [tekrar, setTekrar] = useState(0);
  const sonucRef = useRef<HTMLElement>(null);
  const canliSeritRef = useRef<HTMLDivElement>(null);
  // Son tamamlanan istek ve sonucu; `istek` ile eşleşmiyorsa hesaplama sürüyor demektir (türetilmiş durum).
  const [veri, setVeri] = useState<{ istek: object; sonuc: PlanYaniti | null; hata: string | null } | null>(null);
  const [secili, setSecili] = useState(0);
  const [detayAcik, setDetayAcik] = useState(true);
  const [olcu, setOlcu] = useState<Olcu>({ sol: 416, alt: 0 });
  const [konumHatasi, setKonumHatasi] = useState<string | null>(null);
  const yerler = useYerler();
  const [urlHazir, setUrlHazir] = useState(false);

  // "Otobüsleri gör": açık bacak (indeks), seçili hatlar ve son canlı yanıt
  const [canli, setCanli] = useState<{ anahtar: string; bas: string; bit: string; hat: string } | null>(null);
  const [canliHatlar, setCanliHatlar] = useState<string[]>([]);
  const [canliHepsi, setCanliHepsi] = useState(false);
  const [canliVeri, setCanliVeri] = useState<{ anahtar: string; yanit: YaklasanYaniti | null; hata: string | null } | null>(null);

  const istek = useMemo(() => {
    if (!bas.nokta || !bit.nokta) return null;
    return {
      origin: { lat: bas.nokta.lat, lng: bas.nokta.lng, name: bas.nokta.name },
      dest: { lat: bit.nokta.lat, lng: bit.nokta.lng, name: bit.nokta.name },
      depart_at: zaman.tip === "kalkis" && zaman.deger ? `${zaman.deger}:00+03:00` : undefined,
      arrive_by: zaman.tip === "varis" && zaman.deger ? `${zaman.deger}:00+03:00` : undefined,
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
        setCanli(null);
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

  // Canlı yaklaşan otobüsler: açık bacak için 10 saniyede bir yenilenir (görünür sekmede)
  const canliSecimAnahtari = canli ? `${canli.anahtar}|${canliHepsi ? "*" : canliHatlar.join(",")}` : "";
  useEffect(() => {
    if (!canli) return;
    const ac = new AbortController();
    const getir = async () => {
      try {
        const yanit = await yaklasanIste(canli.bas, canli.bit, canliHepsi ? null : canliHatlar, canli.hat, ac.signal);
        setCanliVeri({ anahtar: canliSecimAnahtari, yanit, hata: null });
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setCanliVeri({ anahtar: canliSecimAnahtari, yanit: null, hata: e instanceof PlanHatasi ? e.message : "Canlı veri alınamadı." });
      }
    };
    void getir();
    const aralik = setInterval(() => {
      if (document.visibilityState === "visible") void getir();
    }, 10000);
    return () => {
      ac.abort();
      clearInterval(aralik);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canliSecimAnahtari]);

  const canliAc = (anahtar: string, etap: Etap) => {
    if (canli?.anahtar === anahtar) {
      setCanli(null);
      return;
    }
    canliSeritRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); // adım listesinden açıldıysa panel görünür olsun
    setCanliHatlar(etap.route_short_name ? [etap.route_short_name] : []);
    setCanliHepsi(false);
    setCanliVeri(null);
    setCanli({ anahtar, bas: etap.from.stop_id as string, bit: etap.to.stop_id as string, hat: etap.route_short_name ?? "" });
  };
  const canliHatDegistir = (hat: string) =>
    setCanliHatlar((l) => (l.includes(hat) ? (l.length > 1 ? l.filter((x) => x !== hat) : l) : [...l, hat]));
  const canliGecerli = canliVeri && canliVeri.anahtar === canliSecimAnahtari;
  const canliYanit = canliGecerli ? canliVeri.yanit : null;

  // Haritadaki araç işaretçileri: seçili hatların tüm canlı araçları; biniş durağına yaklaşanlar vurgulu
  const araclar = (canliYanit?.hatlar ?? [])
    .filter((h) => canliHepsi || canliHatlar.includes(h.hat))
    .flatMap((h) =>
      h.tum_araclar.map((a) => ({
        hat: h.hat,
        kapi: a.kapi_no,
        lat: a.enlem,
        lng: a.boylam,
        dakika: h.araclar.find((x) => x.kapi_no === a.kapi_no)?.dakika ?? null,
      })),
    );
  const odak = canliYanit
    ? {
        anahtar: canli?.anahtar ?? "",
        noktalar: [
          { lat: canliYanit.binis.lat, lng: canliYanit.binis.lng },
          ...canliYanit.hatlar.flatMap((h) => h.araclar.slice(0, 2).map((a) => ({ lat: a.enlem, lng: a.boylam }))),
        ],
      }
    : null;

  const canliPanel = (
    <YaklasanPanel
      veri={canliYanit}
      yukleniyor={!canliGecerli}
      hata={canliGecerli ? canliVeri.hata : null}
      secilenHatlar={canliHatlar}
      hepsi={canliHepsi}
      onHat={(h) => {
        if (canliHepsi) {
          setCanliHepsi(false); // "Hepsi" açıkken bir hat seçmek, yalnızca o hatta geçmektir
          setCanliHatlar([h]);
        } else canliHatDegistir(h);
      }}
      onHepsi={() => setCanliHepsi((v) => !v)}
    />
  );

  const degistir = () => {
    setBas(bit);
    setBit(bas);
  };

  // Plan formu <-> adres çubuğu (paylaşılabilir bağlantı, lib/baglanti.ts). Açılışta URL okunur; sonra durum URL'ye yazılır.
  const durumUygula = useCallback((d: UrlDurum) => {
    const yerOf = (y: UrlYer | null): Yer =>
      y ? { metin: y.ad || `${y.lat.toFixed(5)}, ${y.lng.toFixed(5)}`, nokta: { lat: y.lat, lng: y.lng, name: y.ad || "Seçilen nokta" } } : BOS;
    setBas(yerOf(d.bas));
    setBit(yerOf(d.bit));
    setZaman(d.zaman);
    setTercih(d.tercih);
    setModlar(d.modlar ? new Set(d.modlar as Mod[]) : new Set(MODLAR.map((m) => m.id)));
    setMaxYurume(d.maxYurume);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- URL yalnızca tarayıcıda okunabilir; sunucu çıktısıyla uyuşmazlık olmasın diye açılışta bir kez uygulanır
    durumUygula(baglantiCoz(window.location.search));
    setUrlHazir(true);
    const geri = () => durumUygula(baglantiCoz(window.location.search));
    window.addEventListener("popstate", geri); // geri/ileri tuşları
    return () => window.removeEventListener("popstate", geri);
  }, [durumUygula]);

  useEffect(() => {
    if (!urlHazir || !bas.nokta || !bit.nokta) return; // yalnızca tamamlanmış aramalar URL'ye yazılır (yazarken geçmişte ara kayıt oluşmasın)
    const yerOf = (y: Yer): UrlYer | null => (y.nokta ? { lat: y.nokta.lat, lng: y.nokta.lng, ad: y.metin.trim() } : null);
    const q = baglantiOlustur({
      bas: yerOf(bas), bit: yerOf(bit), zaman, tercih,
      modlar: modlar.size === MODLAR.length ? null : [...modlar], maxYurume,
    });
    if (q === window.location.search) return;
    const yerAnahtari = (a: string) => { const p = new URLSearchParams(a); return `${p.get("from")}|${p.get("to")}`; };
    const url = `${window.location.pathname}${q}`;
    // Yeni bir nereden/nereye: geçmişe yeni kayıt (geri tuşu önceki aramaya döner); seçenek değişiklikleri aynı kaydı günceller
    if (yerAnahtari(q) !== yerAnahtari(window.location.search)) window.history.pushState(null, "", url);
    else window.history.replaceState(null, "", url);
  }, [bas, bit, zaman, tercih, modlar, maxYurume, urlHazir]);

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

  // Rota bulununca iki uç nokta "son aramalar"a eklenir (Konumum hariç: her seferinde değişir)
  const sonEkle = yerler.sonEkle;
  useEffect(() => {
    if (!veri?.sonuc?.itineraries.length) return;
    for (const y of [bas, bit]) {
      if (y.nokta && y.metin.trim() && y.metin.trim() !== "Konumum") sonEkle(yerOlustur(y.metin.trim(), y.nokta.lat, y.nokta.lng));
    }
    // yalnızca yeni bir sonuç geldiğinde çalışır
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [veri]);

  // "Eve git" / "İşe git": varış kayıtlı yer olur; başlangıç boşsa konumunuz alınır
  const hizliGit = (y: { ad: string; lat: number; lng: number }) => {
    setBit({ metin: y.ad, nokta: { lat: y.lat, lng: y.lng, name: y.ad } });
    if (!bas.nokta) konumum();
  };

  // Yeni sonuçlar gelince liste görünür olsun (telefonda çekmecenin altında kalmasın)
  useEffect(() => {
    if (veri?.sonuc?.itineraries.length) sonucRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [veri]);

  const yolculuk = sonuc?.itineraries[secili] ?? null;
  const sonucVar = !!sonuc && sonuc.itineraries.length > 0;

  return (
    <>
      <HaritaHataSiniri>
        <RotaHaritasi durum={durum} yolculuk={yolculuk} baslangic={bas.nokta} varis={bit.nokta} olcu={olcu} araclar={araclar} odak={odak} />
      </HaritaHataSiniri>
      <Cekmece onOlcu={setOlcu}>
        <div className="kaydir flex-1 overflow-y-auto pb-6" >
          <header className="flex items-start justify-between gap-3 px-5 pb-1 pt-1 md:pt-8">
            <div className="min-w-0">
            <h1 className="font-display text-[1.7rem] font-extrabold leading-none text-murekkep">smarttransit</h1>
            <p className="mt-1.5 hidden text-[15px] text-murekkep-2 md:block">Metro, tramvay, Marmaray, vapur ve otobüsle İstanbul&apos;da nereye gidiyorsunuz?</p>
            </div>
            <TemaSecici />
          </header>

          <section aria-label="Nereden nereye" className="px-5 pt-4">
            <div className="relative flex items-stretch gap-1 rounded-2xl bg-yuzey p-2 shadow-[var(--gol)]">
              <div className="relative flex w-7 shrink-0 flex-col items-center justify-center" aria-hidden="true">
                <span className="h-3 w-3 rounded-full border-[3px] border-murekkep bg-yuzey" />
                <span className="my-1 h-7 w-0 border-l-[3px] border-dotted border-murekkep-3" />
                <span className="h-3 w-3 rounded-[3px] bg-iskele ring-[3px] ring-murekkep ring-inset" />
              </div>
              <div className="min-w-0 flex-1 divide-y divide-cizgi">
                <YerAlani
                  secili={!!bas.nokta}
                  nokta={bas.nokta}
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
                  secili={!!bit.nokta}
                  nokta={bit.nokta}
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
            {(yerler.depo.ev || yerler.depo.is) && (
              <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Kayıtlı yerlere git">
                {yerler.depo.ev && (
                  <button
                    type="button"
                    onClick={() => hizliGit(yerler.depo.ev!)}
                    className="inline-flex items-center gap-1.5 rounded-full bg-yuzey px-3.5 py-1.5 text-[13px] font-semibold text-murekkep shadow-[var(--gol)] transition-colors hover:bg-yuzey-2"
                  >
                    <Ev className="text-base text-bogaz" /> Eve git
                  </button>
                )}
                {yerler.depo.is && (
                  <button
                    type="button"
                    onClick={() => hizliGit(yerler.depo.is!)}
                    className="inline-flex items-center gap-1.5 rounded-full bg-yuzey px-3.5 py-1.5 text-[13px] font-semibold text-murekkep shadow-[var(--gol)] transition-colors hover:bg-yuzey-2"
                  >
                    <Is className="text-base text-bogaz" /> İşe git
                  </button>
                )}
              </div>
            )}
            {((bas.metin.trim() && !bas.nokta) || (bit.metin.trim() && !bit.nokta)) && (
              <p className="mt-2 text-[13px] text-murekkep-2">Yazdığınız yeri listeden seçin ya da Enter&apos;a basın; ilk öneri seçilir.</p>
            )}
            {konumHatasi && (
              <p role="alert" className="mt-2 text-[13px] text-hata">
                {konumHatasi}
              </p>
            )}
          </section>

          <section aria-label="Zaman ve tercihler" className="space-y-3 px-5 pt-4">
            <ZamanSecici zaman={zaman} onDegis={setZaman} />
            <TercihSecici tercih={tercih} onDegis={setTercih} />
            <ModSecici secili={modlar} onDegis={setModlar} />
          </section>

          <section ref={sonucRef} aria-live="polite" aria-busy={yukleniyor} className="mt-5">
            {!istek && (
              <p className="px-5 text-[13px] leading-relaxed text-murekkep-2">
                Başlangıç ve varışı yazıp listeden seçin ya da <span className="tnum">41.037, 28.985</span> gibi bir koordinat girin.
                Rota çıkınca binmeniz gereken otobüslerin canlı konumlarını burada görebilirsiniz.
              </p>
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

            {sonucVar && sonuc && yolculuk && (
              <div ref={canliSeritRef}>
                <CanliSerit
                  yolculuk={yolculuk}
                  acikAnahtar={canli?.anahtar ?? null}
                  onToggle={(anahtar, i) => canliAc(anahtar, yolculuk.legs[i])}
                  panel={canliPanel}
                />
              </div>
            )}

            {sonucVar && sonuc && (
              <div className={`mt-5 transition-opacity ${yukleniyor ? "opacity-60" : ""}`}>
                <div className="flex items-center justify-between gap-3 px-5 pb-2">
                  <h2 className="text-sm font-semibold text-murekkep-2">{sonuc.itineraries.length} seçenek</h2>
                  <PaylasDugmesi baslik={`Rota: ${bas.metin.trim()} → ${bit.metin.trim()}`} konumumGizli={bas.metin.trim() === "Konumum"} />
                </div>
                <div className="border-y border-cizgi bg-yuzey">
                  <SecenekListesi
                    secenekler={sonuc.itineraries}
                    secili={secili}
                    detayAcik={detayAcik}
                    canli={{ acikAnahtar: canli?.anahtar ?? null, onToggle: canliAc }}
                    onSec={(i) => {
                      if (i === secili) setDetayAcik((a) => !a); // seçili karta tekrar basınca aç/kapa
                      else {
                        setSecili(i);
                        setDetayAcik(true);
                        setCanli(null);
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


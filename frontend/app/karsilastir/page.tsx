"use client";
// Geliştirici aracı: bizim /api/plan sonucunu Google Directions (toplu taşıma) ile yan yana karşılaştırır.
// Yalnızca geliştirme sürümünde açılır; her çift 1 Google Directions isteği harcar (aylık ücretsiz sınır 10.000).
import { useState } from "react";
import { useGoogleHarita } from "@/lib/google";
import { planIste, type Nokta } from "@/lib/plan";

const CIFTLER: { ad: string; bas: Nokta; bit: Nokta }[] = [
  ["Kadıköy", 40.9905, 29.023, "Taksim", 41.037, 28.985],
  ["Üsküdar", 41.026, 29.015, "Sirkeci", 41.0146, 28.977],
  ["Bostancı", 40.952, 29.095, "Beşiktaş", 41.0415, 29.0075],
  ["Kadıköy", 40.9905, 29.023, "Mecidiyeköy", 41.0675, 28.996],
  ["Pendik", 40.877, 29.233, "Kadıköy", 40.9905, 29.023],
  ["Kartal", 40.908, 29.185, "Taksim", 41.037, 28.985],
  ["Ümraniye", 41.02, 29.125, "Levent", 41.081, 29.012],
  ["Avcılar", 40.9795, 28.724, "Zincirlikuyu", 41.0669, 29.017],
  ["Beylikdüzü", 41.002, 28.642, "Zincirlikuyu", 41.0669, 29.017],
  ["Bakırköy", 40.9795, 28.8727, "Taksim", 41.037, 28.985],
  ["Esenyurt", 41.033, 28.672, "Mecidiyeköy", 41.0675, 28.996],
  ["Halkalı", 41.02, 28.786, "Yenikapı", 41.0045, 28.951],
  ["Sarıyer", 41.167, 29.057, "Beşiktaş", 41.0415, 29.0075],
  ["Maslak", 41.112, 29.02, "Kadıköy", 40.9905, 29.023],
  ["Fatih", 41.019, 28.949, "Üsküdar", 41.026, 29.015],
  ["Çatalca", 41.143, 28.462, "Küçükçekmece", 41.0, 28.77],
  ["Silivri", 41.074, 28.246, "Avcılar", 40.9795, 28.724],
  ["Şişli", 41.06, 28.987, "Bakırköy", 40.9795, 28.8727],
  ["Sabiha Gökçen", 40.9086, 29.3146, "Kadıköy", 40.9905, 29.023],
  ["İstanbul Havalimanı", 41.275, 28.752, "Taksim", 41.037, 28.985],
  ["Küçükçekmece", 41.0, 28.77, "Sirkeci", 41.0146, 28.977],
  ["Kartal", 40.908, 29.185, "Üsküdar", 41.026, 29.015],
  ["Mecidiyeköy", 41.0675, 28.996, "Bostancı", 40.952, 29.095],
  ["Beşiktaş", 41.0415, 29.0075, "Ataşehir", 40.9923, 29.1244],
].map(([a, la, lo, b, la2, lo2]) => ({
  ad: `${a} - ${b}`,
  bas: { lat: la as number, lng: lo as number, name: a as string },
  bit: { lat: la2 as number, lng: lo2 as number, name: b as string },
}));

interface Satir {
  ad: string;
  bizim: { dk: number; aktarma: number; hatlar: string[]; secenek: number } | null;
  google: { dk: number; aktarma: number; hatlar: string[]; secenek: number } | null;
  hata?: string;
}

const bekle = (ms: number) => new Promise((r) => setTimeout(r, ms));
// Graf yüklenirken (503 "hazırlanıyor") en çok ~3 dk bekleyip yeniden dener.
async function planBekle(govde: Parameters<typeof planIste>[0]) {
  for (let i = 0; ; i++) {
    try {
      return await planIste(govde);
    } catch (e) {
      if (i >= 18 || !/hazırlan/i.test((e as Error).message)) throw e;
      await bekle(10000);
    }
  }
}
const ortak = (a: string[], b: string[]) => a.filter((x) => b.includes(x)).length;

export default function Karsilastir() {
  const { isLoaded, durum } = useGoogleHarita();
  const [onay, setOnay] = useState(false);
  const [calisiyor, setCalisiyor] = useState(false);
  const [satirlar, setSatirlar] = useState<Satir[]>([]);
  const gelistirme = process.env.NODE_ENV !== "production";

  if (!gelistirme) {
    return <main className="p-8 text-murekkep">Bu sayfa yalnızca geliştirme sürümünde (npm run dev) açılır.</main>;
  }

  const calistir = async () => {
    setCalisiyor(true);
    setSatirlar([]);
    const simdi = new Date();
    const hizmet = new google.maps.DirectionsService();
    for (const c of CIFTLER) {
      const s: Satir = { ad: c.ad, bizim: null, google: null };
      try {
        const y = await planBekle({ origin: c.bas, dest: c.bit, max_results: 5 });
        if (y.itineraries.length) {
          const en = y.itineraries[0];
          s.bizim = {
            dk: Math.round((new Date(en.arrival_time).getTime() - simdi.getTime()) / 60000),
            aktarma: en.transfers,
            hatlar: en.legs.filter((e) => e.type === "transit").map((e) => e.route_short_name ?? e.mode),
            secenek: y.itineraries.length,
          };
        }
      } catch (e) {
        s.hata = `bizim: ${(e as Error).message}`;
      }
      try {
        const r = await hizmet.route({
          origin: { lat: c.bas.lat, lng: c.bas.lng },
          destination: { lat: c.bit.lat, lng: c.bit.lng },
          travelMode: google.maps.TravelMode.TRANSIT,
          transitOptions: { departureTime: simdi },
          provideRouteAlternatives: true,
          region: "tr",
        });
        // Google'ın ilk önerisi en hızlısı olmayabilir (az aktarmayı önceler); adil karşılaştırma için en erken varan alternatif alınır.
        const bacaklar = r.routes.map((x) => x.legs[0]).filter((b) => b?.arrival_time);
        const rota = bacaklar.reduce((a, b) => (b.arrival_time!.value < a.arrival_time!.value ? b : a), bacaklar[0]);
        if (rota?.arrival_time) {
          const adimlar = rota.steps.filter((a) => a.travel_mode === google.maps.TravelMode.TRANSIT);
          s.google = {
            dk: Math.round((rota.arrival_time.value.getTime() - simdi.getTime()) / 60000),
            aktarma: Math.max(adimlar.length - 1, 0),
            hatlar: adimlar.map((a) => a.transit?.line?.short_name || a.transit?.line?.name || "?"),
            secenek: r.routes.length,
          };
        }
      } catch (e) {
        s.hata = `${s.hata ?? ""} google: ${String(e)}`.trim();
      }
      setSatirlar((onceki) => [...onceki, s]);
      await bekle(500);
    }
    setCalisiyor(false);
  };

  const tam = satirlar.filter((s) => s.bizim && s.google);
  const farklar = tam.map((s) => (s.bizim as NonNullable<Satir["bizim"]>).dk - (s.google as NonNullable<Satir["google"]>).dk).sort((a, b) => a - b);
  const ortanca = farklar.length ? farklar[Math.floor(farklar.length / 2)] : null;
  const yakin = farklar.filter((f) => Math.abs(f) <= 10).length;
  const azAktarma = tam.filter((s) => (s.bizim as NonNullable<Satir["bizim"]>).aktarma < (s.google as NonNullable<Satir["google"]>).aktarma).length;
  const fazlaAktarma = tam.filter((s) => (s.bizim as NonNullable<Satir["bizim"]>).aktarma > (s.google as NonNullable<Satir["google"]>).aktarma).length;

  return (
    <main className="mx-auto max-w-5xl p-6 text-murekkep">
      <h1 className="font-display text-2xl font-bold">Rota karşılaştırma (geliştirici aracı)</h1>
      <p className="mt-2 max-w-2xl text-sm text-murekkep-2">
        {CIFTLER.length} çift için bizim rota sonucunu Google Directions toplu taşıma sonucuyla karşılaştırır. Google tarafında en erken varan alternatif alınır (ilk öneri en hızlısı olmayabilir). Süre, sorgu anından
        varışa kadardır (bekleme dahil). Her çift 1 Google Directions isteği harcar; aylık ücretsiz sınır 10.000 olduğundan bu araç
        sınırın binde birkaçını kullanır. Bu sayfa yalnızca geliştirme sürümünde açılır.
      </p>
      <label className="mt-4 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={onay} onChange={(e) => setOnay(e.target.checked)} />
        {CIFTLER.length} Google Directions isteği yapılmasını onaylıyorum
      </label>
      <button
        type="button"
        disabled={!onay || calisiyor || !isLoaded}
        onClick={() => void calistir()}
        className="mt-3 rounded-full bg-murekkep px-5 py-2.5 text-sm font-semibold text-yuzey disabled:opacity-40"
      >
        {calisiyor ? `Çalışıyor… ${satirlar.length}/${CIFTLER.length}` : "Karşılaştırmayı başlat"}
      </button>
      {durum === "kullanilamiyor" && <p className="mt-2 text-sm text-hata">Google Haritalar yüklenemedi (anahtarı kontrol edin).</p>}

      {tam.length > 0 && (
        <p className="mt-5 rounded-xl bg-yuzey p-3 text-sm">
          Ortanca fark (bizim - Google): <b>{ortanca} dk</b>. ±10 dk içinde: <b>{yakin}/{tam.length}</b>. Bizde daha az aktarma:{" "}
          <b>{azAktarma}</b>, daha çok aktarma: <b>{fazlaAktarma}</b>.
        </p>
      )}

      {satirlar.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-murekkep-2">
              <tr>
                <th className="py-2 pr-3">Çift</th>
                <th className="pr-3">Bizim</th>
                <th className="pr-3">Google</th>
                <th className="pr-3">Fark</th>
                <th>Ortak hat</th>
              </tr>
            </thead>
            <tbody>
              {satirlar.map((s) => (
                <tr key={s.ad} className="border-t border-cizgi align-top">
                  <td className="py-2 pr-3 font-semibold">{s.ad}</td>
                  <td className="pr-3">
                    {s.bizim ? (
                      <>
                        <span className="tnum font-semibold">{s.bizim.dk} dk</span>, {s.bizim.aktarma} akt. ({s.bizim.secenek} seçenek)
                        <br />
                        <span className="text-murekkep-2">{s.bizim.hatlar.join(" > ")}</span>
                      </>
                    ) : (
                      <span className="text-hata">yok</span>
                    )}
                  </td>
                  <td className="pr-3">
                    {s.google ? (
                      <>
                        <span className="tnum font-semibold">{s.google.dk} dk</span>, {s.google.aktarma} akt. ({s.google.secenek} seçenek)
                        <br />
                        <span className="text-murekkep-2">{s.google.hatlar.join(" > ")}</span>
                      </>
                    ) : (
                      <span className="text-hata">yok</span>
                    )}
                  </td>
                  <td className="pr-3 tnum font-semibold">{s.bizim && s.google ? `${s.bizim.dk - s.google.dk} dk` : "-"}</td>
                  <td className="tnum">{s.bizim && s.google ? ortak(s.bizim.hatlar, s.google.hatlar) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {satirlar.some((s) => s.hata) && <pre className="mt-3 whitespace-pre-wrap text-xs text-hata">{satirlar.filter((s) => s.hata).map((s) => `${s.ad}: ${s.hata}`).join("\n")}</pre>}
        </div>
      )}
    </main>
  );
}

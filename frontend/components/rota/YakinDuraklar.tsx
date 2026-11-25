"use client";
import Link from "next/link";
import { useState } from "react";
import { Konum, ModIkonu } from "@/components/rota/Ikonlar";
import { baglantiOlustur } from "@/lib/baglanti";
import { mesafeMetni, sureMetni } from "@/lib/format";
import { modAdi } from "@/lib/modes";
import { PlanHatasi, yakinDuraklarIste, type YakinDurak, type YakinKatmanVeri } from "@/lib/plan";

const YARICAPLAR = [300, 600, 1000];
const VARSAYILAN_YARICAP = 600;
const yaricapMetni = (m: number) => (m >= 1000 ? `${m / 1000} km` : `${m} m`);
/** Yürüme süresi (dk): kuş uçuşu × 1,3 / 4,8 km/s: rota planlayıcıyla aynı varsayım. */
const yurumeDk = (m: number) => Math.max(1, Math.ceil((m * 1.3) / 80));

interface Props {
  /** Harita katmanı verisi (null: kaldır) */
  onVeri: (v: YakinKatmanVeri | null) => void;
  secili: string | null;
  onSec: (id: string | null) => void;
  /** Seçili durağa sokaklardan gerçek yürüyüş mesafesi/süresi (durak kimliği -> bilgi) */
  yurume?: Record<string, { metre: number; saniye: number }>;
}

/** "Yakınımdaki duraklar": konum yalnızca düğmeye basınca istenir. Duraklar haritada adlı noktalar olarak, konumunuz ve arama yarıçapıyla görünür;
 * bir durağı seçince haritada konumunuzdan o durağa noktalı yürüyüş yolu çizilir. */
export default function YakinDuraklar({ onVeri, secili, onSec, yurume = {} }: Props) {
  const [durum, setDurum] = useState<"bos" | "araniyor" | "tamam" | "hata">("bos");
  const [duraklar, setDuraklar] = useState<YakinDurak[]>([]);
  const [konum, setKonum] = useState<YakinKatmanVeri["konum"] | null>(null);
  const [yaricap, setYaricap] = useState(VARSAYILAN_YARICAP);
  const [hata, setHata] = useState("");

  const getir = async (k: YakinKatmanVeri["konum"], r: number) => {
    setDurum("araniyor");
    onSec(null);
    try {
      const y = await yakinDuraklarIste(k.lat, k.lng, r);
      setDuraklar(y.stops);
      onVeri({ konum: k, yaricap: r, duraklar: y.stops });
      setDurum("tamam");
    } catch (e) {
      setHata(e instanceof PlanHatasi ? (e.durum === 422 ? "Konumunuz İstanbul sınırlarının dışında görünüyor." : e.message) : "Yakındaki duraklar alınamadı.");
      setDurum("hata");
    }
  };

  const ara = () => {
    if (!navigator.geolocation) {
      setHata("Bu tarayıcı konum bilgisini vermiyor.");
      setDurum("hata");
      return;
    }
    setDurum("araniyor");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        const k = { lat: p.coords.latitude, lng: p.coords.longitude, dogruluk: Number.isFinite(p.coords.accuracy) ? p.coords.accuracy : null };
        setKonum(k);
        void getir(k, yaricap);
      },
      () => {
        setHata("Konumunuza erişilemedi. Tarayıcı ayarlarından konum iznini açın.");
        setDurum("hata");
      },
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const kapat = () => {
    onVeri(null);
    onSec(null);
    setDurum("bos");
    setDuraklar([]);
  };

  return (
    <section aria-label="Yakınımdaki duraklar" className="mx-5 mt-5">
      {(durum === "bos" || durum === "hata" || (durum === "araniyor" && !konum)) && (
        <button
          type="button"
          onClick={ara}
          disabled={durum === "araniyor"}
          className="inline-flex items-center gap-2 rounded-full border border-cizgi bg-yuzey px-4 py-2.5 text-[14px] font-semibold text-murekkep transition-colors hover:bg-yuzey-2 disabled:opacity-60"
        >
          <Konum className="text-lg text-bogaz" /> {durum === "araniyor" ? "Konum alınıyor…" : "Yakınımdaki duraklar"}
        </button>
      )}
      {durum === "hata" && <p role="alert" className="mt-2 text-[13px] text-hata">{hata}</p>}

      {konum && (durum === "tamam" || durum === "araniyor") && (
        <>
          <div className="flex items-center justify-between gap-2 pb-2">
            <h2 className="text-sm font-semibold text-murekkep-2">Yakınımdaki duraklar</h2>
            <button type="button" onClick={kapat} className="rounded-md px-1.5 py-0.5 text-[12px] font-semibold text-bogaz hover:underline">
              Haritadan kaldır
            </button>
          </div>
          <div role="radiogroup" aria-label="Arama yarıçapı" className="mb-2 flex items-center gap-1.5">
            {YARICAPLAR.map((r) => (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={yaricap === r}
                onClick={() => {
                  setYaricap(r);
                  void getir(konum, r);
                }}
                className={`rounded-full px-3 py-1 text-[12px] font-semibold transition-colors ${yaricap === r ? "bg-murekkep text-yuzey" : "bg-yuzey-2 text-murekkep-2 hover:text-murekkep"}`}
              >
                {yaricapMetni(r)}
              </button>
            ))}
            <span role="status" aria-live="polite" className="ml-1 text-[12px] text-murekkep-3">
              {durum === "araniyor" ? "Aranıyor…" : `${yaricapMetni(yaricap)} çevresinde ${duraklar.length} durak`}
            </span>
          </div>
          {durum === "tamam" && duraklar.length === 0 ? (
            <p className="text-[13px] text-murekkep-2">{yaricapMetni(yaricap)} çevresinde durak bulunamadı. Yarıçapı büyütmeyi deneyin.</p>
          ) : (
            <ul className="m-0 list-none divide-y divide-cizgi rounded-2xl bg-yuzey p-0 shadow-[var(--gol)]">
              {duraklar.map((d) => {
                const acik = secili === d.stop_id;
                return (
                  <li key={d.stop_id}>
                    <button
                      type="button"
                      aria-pressed={acik}
                      onClick={() => onSec(acik ? null : d.stop_id)}
                      className={`flex w-full items-center gap-3 px-3.5 py-3 text-left transition-colors hover:bg-yuzey-2 ${acik ? "bg-yuzey-2" : ""}`}
                    >
                      <span className="flex shrink-0 gap-1 text-lg text-bogaz" aria-hidden="true">
                        {d.modes.slice(0, 3).map((m) => <ModIkonu key={m} mod={m} />)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[14px] font-semibold text-murekkep">{d.name}</span>
                        <span className="block truncate text-[12px] text-murekkep-3">
                          {d.modes.map(modAdi).join(", ")}: {d.routes.slice(0, 5).join(", ")}
                        </span>
                      </span>
                      <span className="shrink-0 text-right leading-tight">
                        <span className="tnum block text-[13px] font-semibold text-murekkep">{mesafeMetni(d.distance_m)}</span>
                        <span className="tnum block text-[11px] text-murekkep-3">~{yurumeDk(d.distance_m)} dk yürüyüş</span>
                      </span>
                    </button>
                    {acik && (
                      <div className="flex flex-wrap gap-2 bg-yuzey-2 px-3.5 pb-3">
                        {yurume[d.stop_id] && (
                          <p className="w-full text-[12px] text-murekkep-2">
                            Sokaklardan yaklaşık {mesafeMetni(yurume[d.stop_id].metre)}, {sureMetni(yurume[d.stop_id].saniye)} yürüyüş
                          </p>
                        )}
                        <Link
                          href={`/durak/${encodeURIComponent(d.stop_id)}`}
                          className="rounded-full bg-iskele px-3.5 py-1.5 text-[13px] font-semibold text-[#2a1a00]"
                        >
                          Kalkışlar ve canlı otobüsler
                        </Link>
                        <Link
                          href={`/${baglantiOlustur({ bas: null, bit: { lat: d.lat, lng: d.lng, ad: d.name }, zaman: { tip: "simdi", deger: "" }, tercih: "fastest", modlar: null, maxYurume: 800 })}`}
                          className="rounded-full border border-cizgi bg-yuzey px-3.5 py-1.5 text-[13px] font-semibold text-murekkep"
                        >
                          Buraya git
                        </Link>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="mt-2 text-[12px] leading-relaxed text-murekkep-3">
            Haritada mavi nokta konumunuz, kesikli daire arama yarıçapıdır. Bir durağa dokununca konumunuzdan o durağa yürüyüş yolu çizilir.
          </p>
        </>
      )}
    </section>
  );
}

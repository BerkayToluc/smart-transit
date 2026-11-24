"use client";
import Link from "next/link";
import { useState } from "react";
import { Konum, ModIkonu } from "@/components/rota/Ikonlar";
import { mesafeMetni } from "@/lib/format";
import { modAdi } from "@/lib/modes";
import { PlanHatasi, yakinDuraklarIste, type YakinDurak } from "@/lib/plan";

/** "Yakınımdaki duraklar": konum yalnızca düğmeye basınca istenir; liste durak sayfalarına bağlanır. */
export default function YakinDuraklar() {
  const [durum, setDurum] = useState<"bos" | "araniyor" | "tamam" | "hata">("bos");
  const [duraklar, setDuraklar] = useState<YakinDurak[]>([]);
  const [hata, setHata] = useState("");

  const ara = () => {
    if (!navigator.geolocation) {
      setHata("Bu tarayıcı konum bilgisini vermiyor.");
      setDurum("hata");
      return;
    }
    setDurum("araniyor");
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        try {
          const y = await yakinDuraklarIste(p.coords.latitude, p.coords.longitude);
          setDuraklar(y.stops);
          setDurum("tamam");
        } catch (e) {
          setHata(e instanceof PlanHatasi ? (e.durum === 422 ? "Konumunuz İstanbul sınırlarının dışında görünüyor." : e.message) : "Yakındaki duraklar alınamadı.");
          setDurum("hata");
        }
      },
      () => {
        setHata("Konumunuza erişilemedi. Tarayıcı ayarlarından konum iznini açın.");
        setDurum("hata");
      },
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  return (
    <section aria-label="Yakınımdaki duraklar" className="mx-5 mt-5">
      {durum !== "tamam" && (
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
      {durum === "tamam" && (
        <>
          <h2 className="pb-2 text-sm font-semibold text-murekkep-2">Yakınımdaki duraklar</h2>
          {duraklar.length === 0 ? (
            <p className="text-[13px] text-murekkep-2">Yakınınızda (600 m) durak bulunamadı.</p>
          ) : (
            <ul className="m-0 list-none divide-y divide-cizgi rounded-2xl bg-yuzey p-0 shadow-[var(--gol)]">
              {duraklar.map((d) => (
                <li key={d.stop_id}>
                  <Link href={`/durak/${encodeURIComponent(d.stop_id)}`} className="flex items-center gap-3 px-3.5 py-3 transition-colors hover:bg-yuzey-2">
                    <span className="flex shrink-0 gap-1 text-lg text-bogaz" aria-hidden="true">
                      {d.modes.slice(0, 3).map((m) => <ModIkonu key={m} mod={m} />)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-semibold text-murekkep">{d.name}</span>
                      <span className="block truncate text-[12px] text-murekkep-3">
                        {d.modes.map(modAdi).join(", ")}: {d.routes.slice(0, 5).join(", ")}
                      </span>
                    </span>
                    <span className="tnum shrink-0 text-[12px] font-semibold text-murekkep-2">{mesafeMetni(d.distance_m)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

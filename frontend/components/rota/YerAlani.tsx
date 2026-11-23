"use client";
import { useEffect, useRef, useState } from "react";
import { Autocomplete } from "@react-google-maps/api";
import { ISTANBUL_SINIRLARI } from "@/lib/google";
import type { Nokta } from "@/lib/plan";
import { Konum } from "@/components/rota/Ikonlar";
import YerKaydet from "@/components/rota/YerKaydet";
import YerOnerileri from "@/components/rota/YerOnerileri";
import { useYerler, yerOlustur, type KayitliYer } from "@/lib/yerler";
import { bos } from "@/lib/yerlerMantik";

const KOORDINAT = /^\s*(-?\d{1,2}[.,]\d+)\s*[,;\s]\s*(-?\d{1,3}[.,]\d+)\s*$/;

/** "41.03, 28.98" biçimindeki metni koordinata çevirir (Google yüklenmediyse de yer girilebilsin). */
export function koordinatCoz(metin: string): Nokta | null {
  const m = KOORDINAT.exec(metin);
  if (!m) return null;
  const lat = parseFloat(m[1].replace(",", "."));
  const lng = parseFloat(m[2].replace(",", "."));
  return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
}

/** Yazılan metni Google önerilerinin ilkiyle çözer ("okan üniversitesi" + Enter). Bulunamazsa null. */
async function ilkOneriyiCoz(metin: string): Promise<(Nokta & { name: string }) | null> {
  if (typeof google === "undefined" || !google.maps?.places) return null;
  const oneriler = await new Promise<google.maps.places.AutocompletePrediction[]>((coz) => {
    new google.maps.places.AutocompleteService().getPlacePredictions(
      { input: metin, componentRestrictions: { country: "tr" }, locationBias: ISTANBUL_SINIRLARI, language: "tr" },
      (r) => coz(r ?? []),
    );
  });
  if (oneriler.length === 0) return null;
  return new Promise((coz) => {
    new google.maps.places.PlacesService(document.createElement("div")).getDetails(
      { placeId: oneriler[0].place_id, fields: ["geometry", "name"] },
      (yer, durum) => {
        const konum = yer?.geometry?.location;
        coz(durum === google.maps.places.PlacesServiceStatus.OK && konum ? { lat: konum.lat(), lng: konum.lng(), name: yer?.name || oneriler[0].description } : null);
      },
    );
  });
}

interface Props {
  /** Bu alanda bir nokta seçili mi (üst bileşen bilir) */
  secili: boolean;
  /** Seçili nokta (kaydetme menüsü için) */
  nokta?: Nokta | null;
  id: string;
  etiket: string;
  yerTutucu: string;
  deger: string;
  googleHazir: boolean;
  onDeger: (metin: string) => void;
  onSecim: (nokta: Nokta | null) => void;
  konumumDestegi?: boolean;
  onKonumum?: () => void;
}

export default function YerAlani({ secili, nokta, id, etiket, yerTutucu, deger, googleHazir, onDeger, onSecim, konumumDestegi, onKonumum }: Props) {
  const ac = useRef<google.maps.places.Autocomplete | null>(null);
  const yerler = useYerler();
  const [oneriAcik, setOneriAcik] = useState(false);
  const oneriGoster = oneriAcik && deger.trim() === "" && !bos(yerler.depo);
  const kayitli = (y: KayitliYer) => {
    onDeger(y.ad);
    onSecim({ lat: y.lat, lng: y.lng, name: y.ad });
    setOneriAcik(false);
    (document.activeElement as HTMLElement | null)?.blur();
  };
  const kaydedilecek: KayitliYer | null =
    yerler.kullanilabilir && nokta && deger.trim() ? yerOlustur(deger.trim() || nokta.name || "Seçilen nokta", nokta.lat, nokta.lng) : null;

  const bekleyen = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seciliRef = useRef(secili);
  const metinRef = useRef(deger);
  useEffect(() => {
    seciliRef.current = secili;
    metinRef.current = deger;
  });
  useEffect(() => () => {
    if (bekleyen.current) clearTimeout(bekleyen.current);
  }, []);

  /** Listeden seçilmediyse: koordinat mı? değilse ilk Google önerisi. */
  const metniCoz = async () => {
    const metin = metinRef.current.trim();
    if (!metin || seciliRef.current) return;
    const k = koordinatCoz(metin);
    if (k) {
      onSecim({ ...k, name: "Seçilen nokta" });
      return;
    }
    if (!googleHazir) return;
    const yer = await ilkOneriyiCoz(metin);
    if (!yer || seciliRef.current || metinRef.current.trim() !== metin) return; // bu arada başka bir şey seçildi/yazıldı
    onDeger(yer.name);
    onSecim(yer);
  };

  const yerSecildi = () => {
    if (bekleyen.current) clearTimeout(bekleyen.current); // liste tıklaması: gecikmeli çözümlemeyi iptal et
    const yer = ac.current?.getPlace();
    const konum = yer?.geometry?.location;
    if (!konum) return;
    const ad = yer?.name || yer?.formatted_address || "";
    onDeger(ad);
    onSecim({ lat: konum.lat(), lng: konum.lng(), name: ad });
  };

  const girdi = (
    <input
      id={id}
      type="text"
      value={deger}
      autoComplete="off"
      placeholder={yerTutucu}
      aria-label={etiket}
      onFocus={() => setOneriAcik(true)}
      onChange={(e) => {
        onDeger(e.target.value);
        onSecim(null); // metin değişti: önceki seçim geçersiz
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOneriAcik(false);
        if (e.key !== "Enter") return;
        e.preventDefault();
        void metniCoz();
      }}
      onBlur={() => {
        // Öneri listesine tıklanırsa önce blur gelir; kısa bekleyip seçim olmadıysa metni çöz
        bekleyen.current = setTimeout(() => void metniCoz(), 350);
      }}
      className="h-12 w-full min-w-0 rounded-xl bg-transparent pl-1 pr-2 text-[15px] font-medium text-murekkep outline-none placeholder:text-murekkep-3"
    />
  );

  return (
    <div
      className="flex min-w-0 flex-1 items-center"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOneriAcik(false); // odak bu alanın dışına çıktı
      }}
    >
      {googleHazir ? (
        <div className="min-w-0 flex-1">
          <Autocomplete
            onLoad={(a) => {
              ac.current = a;
            }}
            onPlaceChanged={yerSecildi}
            options={{
              componentRestrictions: { country: "tr" },
              bounds: ISTANBUL_SINIRLARI,
              strictBounds: false,
              fields: ["geometry", "name", "formatted_address"],
            }}
          >
            {girdi}
          </Autocomplete>
        </div>
      ) : (
        <div className="min-w-0 flex-1">{girdi}</div>
      )}
      {kaydedilecek && (
        <YerKaydet
          yer={kaydedilecek}
          depo={yerler.depo}
          onEv={() => yerler.evKaydet(kaydedilecek)}
          onIs={() => yerler.isKaydet(kaydedilecek)}
          onFavori={() => yerler.favoriEkle(kaydedilecek)}
          onFavoriKaldir={() => yerler.favoriSil(kaydedilecek)}
        />
      )}
      {oneriGoster && (
        <YerOnerileri
          depo={yerler.depo}
          onSec={kayitli}
          onEvSil={() => yerler.evKaydet(null)}
          onIsSil={() => yerler.isKaydet(null)}
          onFavoriSil={yerler.favoriSil}
          onSonlariSil={yerler.sonlariSil}
          onHepsiniSil={yerler.hepsiniSil}
        />
      )}
      {konumumDestegi && (
        <button
          type="button"
          onClick={onKonumum}
          aria-label="Konumumu kullan"
          title="Konumumu kullan"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-xl text-bogaz transition-colors hover:bg-yuzey-2"
        >
          <Konum />
        </button>
      )}
    </div>
  );
}

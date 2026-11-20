"use client";
import { useRef } from "react";
import { Autocomplete } from "@react-google-maps/api";
import { ISTANBUL_SINIRLARI } from "@/lib/google";
import type { Nokta } from "@/lib/plan";
import { Konum } from "@/components/rota/Ikonlar";

const KOORDINAT = /^\s*(-?\d{1,2}[.,]\d+)\s*[,;\s]\s*(-?\d{1,3}[.,]\d+)\s*$/;

/** "41.03, 28.98" biçimindeki metni koordinata çevirir (Google yüklenmediyse de yer girilebilsin). */
export function koordinatCoz(metin: string): Nokta | null {
  const m = KOORDINAT.exec(metin);
  if (!m) return null;
  const lat = parseFloat(m[1].replace(",", "."));
  const lng = parseFloat(m[2].replace(",", "."));
  return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
}

interface Props {
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

export default function YerAlani({ id, etiket, yerTutucu, deger, googleHazir, onDeger, onSecim, konumumDestegi, onKonumum }: Props) {
  const ac = useRef<google.maps.places.Autocomplete | null>(null);

  const yerSecildi = () => {
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
      onChange={(e) => {
        onDeger(e.target.value);
        onSecim(null); // metin değişti: önceki seçim geçersiz
      }}
      onKeyDown={(e) => {
        if (e.key !== "Enter") return;
        const k = koordinatCoz(deger);
        if (k) onSecim({ ...k, name: "Seçilen nokta" });
      }}
      onBlur={() => {
        const k = koordinatCoz(deger);
        if (k) onSecim({ ...k, name: "Seçilen nokta" });
      }}
      className="h-12 w-full min-w-0 rounded-xl bg-transparent pl-1 pr-2 text-[15px] font-medium text-murekkep outline-none placeholder:text-murekkep-3"
    />
  );

  return (
    <div className="flex min-w-0 flex-1 items-center">
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

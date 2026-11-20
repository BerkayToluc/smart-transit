"use client";
import { useEffect, useState } from "react";
import { useMedya } from "@/lib/hooks";
import { GoogleMap, Marker, Polyline } from "@react-google-maps/api";
import { hatRengi, renkCoz } from "@/lib/modes";
import { ISTANBUL_MERKEZ, type HaritaDurumu } from "@/lib/google";
import type { Nokta, Yolculuk } from "@/lib/plan";
import type { Olcu } from "@/components/rota/Cekmece";

const GECE_STILI: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#0f2430" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#9db4be" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0f2430" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#08141b" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#1d3a4a" }] },
  { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#7691a0" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
];
const GUNDUZ_STILI: google.maps.MapTypeStyle[] = [
  { featureType: "poi.business", stylers: [{ visibility: "off" }] },
  { featureType: "transit.station.bus", stylers: [{ visibility: "off" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#bfd9e3" }] },
];

interface Props {
  durum: HaritaDurumu;
  yolculuk: Yolculuk | null;
  baslangic: Nokta | null;
  varis: Nokta | null;
  olcu: Olcu;
}

export default function RotaHaritasi({ durum, yolculuk, baslangic, varis, olcu }: Props) {
  const [harita, setHarita] = useState<google.maps.Map | null>(null);
  const karanlik = useMedya("(prefers-color-scheme: dark)");

  // Seçili yolculuk (ya da yalnızca iki uç nokta) ekrana sığdırılır; çekmece/panel kadar boşluk bırakılır.
  useEffect(() => {
    if (!harita) return;
    const sinir = new google.maps.LatLngBounds();
    let n = 0;
    const ekle = (lat: number, lng: number) => {
      sinir.extend({ lat, lng });
      n++;
    };
    if (yolculuk) yolculuk.legs.forEach((e) => e.polyline.forEach(([la, lo]) => ekle(la, lo)));
    else {
      if (baslangic) ekle(baslangic.lat, baslangic.lng);
      if (varis) ekle(varis.lat, varis.lng);
    }
    if (n === 0) return;
    if (n === 1) {
      harita.panTo(sinir.getCenter());
      harita.setZoom(15);
      return;
    }
    harita.fitBounds(sinir, { top: 72, right: 32, left: olcu.sol + 32, bottom: olcu.alt + 24 });
  }, [harita, yolculuk, baslangic, varis, olcu.sol, olcu.alt]);

  if (durum !== "hazir") {
    return (
      <div className="absolute inset-0 grid place-items-center bg-sis p-8 text-center" role="status">
        <div className="max-w-sm md:ml-[26rem]">
          {durum === "yukleniyor" ? (
            <p className="text-sm text-murekkep-2">Harita yükleniyor…</p>
          ) : (
            <>
              <p className="text-[15px] font-semibold text-murekkep">Harita kullanılamıyor</p>
              <p className="mt-1 text-sm leading-relaxed text-murekkep-2">
                Google Haritalar yüklenemedi ya da anahtar kabul edilmedi. Rota adımları soldaki listede görünür; yer araması için
                enlem ve boylam girebilirsiniz.
              </p>
            </>
          )}
        </div>
      </div>
    );
  }

  const daire = (dolgu: string, kenar: string, olcek: number, kalinlik: number): google.maps.Symbol => ({
    path: google.maps.SymbolPath.CIRCLE,
    scale: olcek,
    fillColor: dolgu,
    fillOpacity: 1,
    strokeColor: kenar,
    strokeWeight: kalinlik,
  });

  return (
    <GoogleMap
      mapContainerClassName="absolute inset-0"
      center={ISTANBUL_MERKEZ}
      zoom={11}
      onLoad={setHarita}
      onUnmount={() => setHarita(null)}
      options={{
        disableDefaultUI: true,
        zoomControl: true,
        clickableIcons: false,
        gestureHandling: "greedy",
        styles: karanlik ? GECE_STILI : GUNDUZ_STILI,
      }}
    >
      {yolculuk?.legs.map((e, i) => {
        const yol = e.polyline.map(([lat, lng]) => ({ lat, lng }));
        if (e.type === "walk") {
          return (
            <Polyline
              key={`y${i}`}
              path={yol}
              options={{
                strokeOpacity: 0,
                zIndex: 1,
                icons: [{ icon: { path: "M 0,-1 0,1", strokeOpacity: 0.95, strokeColor: karanlik ? "#a8bbc4" : "#4a6572", scale: 3 }, offset: "0", repeat: "11px" }],
              }}
            />
          );
        }
        const renk = renkCoz(hatRengi(e.mode, e.route_short_name));
        return (
          <Polyline key={`a${i}`} path={yol} options={{ strokeColor: renk, strokeOpacity: 0.95, strokeWeight: 6, zIndex: 2 }} />
        );
      })}
      {yolculuk?.legs.map((e, i) =>
        e.type === "transit" ? (
          <span key={`d${i}`}>
            <Marker position={e.from} icon={daire("#ffffff", renkCoz(hatRengi(e.mode, e.route_short_name)), 5.5, 3.5)} title={e.from.name} zIndex={5} />
            <Marker position={e.to} icon={daire("#ffffff", renkCoz(hatRengi(e.mode, e.route_short_name)), 5.5, 3.5)} title={e.to.name} zIndex={5} />
          </span>
        ) : null,
      )}
      {baslangic && <Marker position={baslangic} icon={daire("#0c2a38", "#ffffff", 8, 3)} title="Başlangıç" zIndex={10} />}
      {varis && <Marker position={varis} icon={daire("#f59f0f", "#0c2a38", 9, 3)} title="Varış" zIndex={10} />}
    </GoogleMap>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useMedya } from "@/lib/hooks";
import { GoogleMap } from "@react-google-maps/api";
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

/** Otobüs/metrobüs bacağını gerçek yollara oturtur: durak sırası boyunca Google Directions (araç yolu). Başarısızsa null. */
const yolOnbellek = new Map<string, google.maps.LatLngLiteral[]>();

function uzunluk(yol: { lat: number; lng: number }[]): number {
  let t = 0;
  for (let i = 1; i < yol.length; i++) {
    const dLat = (yol[i].lat - yol[i - 1].lat) * 111_000;
    const dLng = (yol[i].lng - yol[i - 1].lng) * 83_800;
    t += Math.hypot(dLat, dLng);
  }
  return t;
}

async function yolaOturt(noktalar: [number, number][]): Promise<google.maps.LatLngLiteral[] | null> {
  if (noktalar.length < 2) return null;
  const anahtar = noktalar.map(([a, b]) => `${a.toFixed(5)},${b.toFixed(5)}`).join("|");
  const onbellekte = yolOnbellek.get(anahtar);
  if (onbellekte) return onbellekte;
  const lit = noktalar.map(([lat, lng]) => ({ lat, lng }));
  const ic = lit.slice(1, -1);
  // Directions en çok 25 ara nokta kabul eder: uzun hatlarda eşit aralıklı örnek
  const ornek = ic.length > 23 ? Array.from({ length: 23 }, (_, i) => ic[Math.floor(((i + 0.5) * ic.length) / 23)]) : ic;
  try {
    const sonuc = await new google.maps.DirectionsService().route({
      origin: lit[0],
      destination: lit[lit.length - 1],
      waypoints: ornek.map((location) => ({ location, stopover: false })),
      travelMode: google.maps.TravelMode.DRIVING,
      optimizeWaypoints: false,
      region: "tr",
    });
    const yol = sonuc.routes[0]?.overview_path.map((p) => ({ lat: p.lat(), lng: p.lng() }));
    if (!yol || yol.length < 2) return null;
    if (uzunluk(yol) > uzunluk(lit) * 2.5) return null; // büyük sapma: durak sırasını bozan yol; düz çizgi kalsın
    yolOnbellek.set(anahtar, yol);
    return yol;
  } catch {
    return null;
  }
}

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

  // Çizgi ve işaretçiler React sarmalayıcısı yerine doğrudan Google API'siyle yönetilir: seçim/giriş değişince
  // eskiler kesinlikle kaldırılır (eski rotanın haritada kalması hatası).
  useEffect(() => {
    if (!harita) return;
    const nesneler: { setMap: (m: google.maps.Map | null) => void }[] = [];
    let iptal = false;
    const ekle = <T extends { setMap: (m: google.maps.Map | null) => void }>(n: T): T => {
      nesneler.push(n);
      return n;
    };
    const daire = (dolgu: string, kenar: string, olcek: number, kalinlik: number): google.maps.Symbol => ({
      path: google.maps.SymbolPath.CIRCLE,
      scale: olcek,
      fillColor: dolgu,
      fillOpacity: 1,
      strokeColor: kenar,
      strokeWeight: kalinlik,
    });
    const isaret = (konum: google.maps.LatLngLiteral, ikon: google.maps.Symbol, baslik: string, z: number) =>
      ekle(new google.maps.Marker({ map: harita, position: konum, icon: ikon, title: baslik, zIndex: z, clickable: false }));

    yolculuk?.legs.forEach((e) => {
      const yol = e.polyline.map(([lat, lng]) => ({ lat, lng }));
      if (e.type === "walk") {
        ekle(
          new google.maps.Polyline({
            map: harita,
            path: yol,
            strokeOpacity: 0,
            zIndex: 1,
            icons: [{ icon: { path: "M 0,-1 0,1", strokeOpacity: 0.95, strokeColor: karanlik ? "#a8bbc4" : "#4a6572", scale: 3 }, offset: "0", repeat: "11px" }],
          }),
        );
        return;
      }
      const renk = renkCoz(hatRengi(e.mode, e.route_short_name));
      const yolBacagi = e.mode === "bus" || e.mode === "metrobus";
      const cizgi = ekle(
        new google.maps.Polyline({ map: harita, path: yol, strokeColor: renk, strokeOpacity: yolBacagi ? 0.4 : 0.95, strokeWeight: 6, zIndex: 2 }),
      );
      if (yolBacagi) {
        yolaOturt(e.polyline).then((oturan) => {
          if (iptal) return;
          if (oturan) cizgi.setOptions({ path: oturan, strokeOpacity: 0.95 });
          else cizgi.setOptions({ strokeOpacity: 0.95 }); // yola oturtulamadı: durak sırası çizgisi
        });
      }
      const nokta = daire("#ffffff", renk, 5.5, 3.5);
      isaret(e.from, nokta, e.from.name, 5);
      isaret(e.to, nokta, e.to.name, 5);
    });
    if (baslangic) isaret(baslangic, daire("#0c2a38", "#ffffff", 8, 3), "Başlangıç", 10);
    if (varis) isaret(varis, daire("#f59f0f", "#0c2a38", 9, 3), "Varış", 10);

    return () => {
      iptal = true;
      nesneler.forEach((n) => n.setMap(null));
    };
  }, [harita, yolculuk, baslangic, varis, karanlik]);

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
    />
  );
}

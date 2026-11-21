"use client";
import { useEffect, useRef, useState } from "react";
import { useMedya } from "@/lib/hooks";
import { GoogleMap } from "@react-google-maps/api";
import { hatRengi, renkCoz, yaziRengi } from "@/lib/modes";
import { ISTANBUL_MERKEZ, type HaritaDurumu } from "@/lib/google";
import type { Etap, Nokta, Yolculuk } from "@/lib/plan";
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

/** Tek parça (en çok 9 durak): Google Directions ile araç yolu. Sapma/hata olursa null. */
async function parcaOturt(lit: google.maps.LatLngLiteral[]): Promise<google.maps.LatLngLiteral[] | null> {
  try {
    const sonuc = await new google.maps.DirectionsService().route({
      origin: lit[0],
      destination: lit[lit.length - 1],
      waypoints: lit.slice(1, -1).map((location) => ({ location, stopover: false })),
      travelMode: google.maps.TravelMode.DRIVING,
      optimizeWaypoints: false,
      region: "tr",
    });
    const yol = sonuc.routes[0]?.overview_path.map((p) => ({ lat: p.lat(), lng: p.lng() }));
    if (!yol || yol.length < 2) return null;
    if (uzunluk(yol) > uzunluk(lit) * 3 + 300) return null; // büyük sapma: durak sırasını bozan yol; düz çizgi kalsın
    return yol;
  } catch {
    return null;
  }
}

const PARCA_ARALIK = 8; // bir istekte en çok 8 aralık (9 durak)

/** Otobüs/metrobüs bacağını gerçek yollara oturtur. Uzun bacak (özellikle seyrek duraklı metrobüs) tek istekte
 * başarısız olabildiği için kısa parçalara bölünür; başarısız parça düz çizgi kalır, diğerleri yolu izler. */
async function yolaOturt(noktalar: [number, number][]): Promise<google.maps.LatLngLiteral[] | null> {
  if (noktalar.length < 2) return null;
  const anahtar = "B|" + noktalar.map(([a, b]) => `${a.toFixed(5)},${b.toFixed(5)}`).join("|");
  const onbellekte = yolOnbellek.get(anahtar);
  if (onbellekte) return onbellekte;
  const lit = noktalar.map(([lat, lng]) => ({ lat, lng }));
  const tum: google.maps.LatLngLiteral[] = [];
  let basarili = 0;
  for (let i = 0; i < lit.length - 1; i += PARCA_ARALIK) {
    const parca = lit.slice(i, Math.min(i + PARCA_ARALIK + 1, lit.length));
    const oturan = await parcaOturt(parca);
    if (oturan) basarili++;
    tum.push(...(oturan ?? parca).slice(tum.length ? 1 : 0)); // birleşim noktası iki kez eklenmesin
  }
  if (basarili === 0) return null;
  yolOnbellek.set(anahtar, tum);
  return tum;
}

export interface HaritaArac {
  hat: string;
  kapi: string;
  lat: number;
  lng: number;
  dakika: number | null; // biniş durağına yaklaşıyorsa kalan dk
}

const RAYLI_MODLAR = ["rail", "metro", "tram", "funicular", "cable_car"];

function ayriMetre(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  return Math.hypot((a.lat - b.lat) * 111_000, (a.lng - b.lng) * 83_800);
}

/** Metro/tramvay/Marmaray bacağını ray hattına oturtur: Google toplu taşıma güzergâhının adım çizgileri raya uyar
 * (durakları düz çizgiyle birleştirmek kıyı boyunca kıvrılan Marmaray'da sapıyordu). Başarısızsa null. */
async function raylaOturt(e: Etap): Promise<google.maps.LatLngLiteral[] | null> {
  const bas = { lat: e.from.lat, lng: e.from.lng };
  const bit = { lat: e.to.lat, lng: e.to.lng };
  const anahtar = `T|${e.mode}|${bas.lat.toFixed(5)},${bas.lng.toFixed(5)}|${bit.lat.toFixed(5)},${bit.lng.toFixed(5)}`;
  const onbellekte = yolOnbellek.get(anahtar);
  if (onbellekte) return onbellekte;
  const T = google.maps.TransitMode;
  const modlar = e.mode === "metro" ? [T.SUBWAY, T.RAIL, T.TRAIN] : e.mode === "tram" ? [T.TRAM] : [T.RAIL, T.TRAIN, T.SUBWAY, T.TRAM];
  // Gece seferi yokken sonuç boş dönmesin: yarın öğlen için sor (güzergâh çizgisi saatten bağımsızdır)
  const yarin = new Date();
  yarin.setDate(yarin.getDate() + 1);
  yarin.setHours(12, 0, 0, 0);
  try {
    const sonuc = await new google.maps.DirectionsService().route({
      origin: bas,
      destination: bit,
      travelMode: google.maps.TravelMode.TRANSIT,
      transitOptions: { modes: modlar, departureTime: yarin },
      region: "tr",
    });
    const adimlar = (sonuc.routes[0]?.legs[0]?.steps ?? []).filter((a) => a.travel_mode === google.maps.TravelMode.TRANSIT);
    const yol = adimlar.flatMap((a) => (a.path ?? []).map((p) => ({ lat: p.lat(), lng: p.lng() })));
    if (yol.length < 2) return null;
    // Uçlar istasyonlara yakın olmalı ve çizgi makul uzunlukta kalmalı; yoksa Google başka bir güzergâh seçmiştir
    if (ayriMetre(yol[0], bas) > 500 || ayriMetre(yol[yol.length - 1], bit) > 500) return null;
    if (uzunluk(yol) > ayriMetre(bas, bit) * 3 + 500) return null;
    const tam = [bas, ...yol, bit];
    yolOnbellek.set(anahtar, tam);
    return tam;
  } catch {
    return null;
  }
}

interface Props {
  araclar: HaritaArac[];
  odak: { anahtar: string; noktalar: { lat: number; lng: number }[] } | null;
  durum: HaritaDurumu;
  yolculuk: Yolculuk | null;
  baslangic: Nokta | null;
  varis: Nokta | null;
  olcu: Olcu;
}

export default function RotaHaritasi({ araclar, odak, durum, yolculuk, baslangic, varis, olcu }: Props) {
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
      const rayBacagi = RAYLI_MODLAR.includes(e.mode);
      const cizgi = ekle(
        new google.maps.Polyline({ map: harita, path: yol, strokeColor: renk, strokeOpacity: yolBacagi || rayBacagi ? 0.4 : 0.95, strokeWeight: 6, zIndex: 2 }),
      );
      if (yolBacagi || rayBacagi) {
        (yolBacagi ? yolaOturt(e.polyline) : raylaOturt(e)).then((oturan) => {
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

  // Canlı araç işaretçileri (rota çizgisinden bağımsız; 10 sn'lik yenilemede yalnız bunlar yeniden çizilir)
  useEffect(() => {
    if (!harita || araclar.length === 0) return;
    const isaretler = araclar.map((a) => {
      const renk = renkCoz(hatRengi("bus", a.hat));
      return new google.maps.Marker({
        map: harita,
        position: { lat: a.lat, lng: a.lng },
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 13,
          fillColor: renk,
          fillOpacity: 1,
          strokeColor: a.dakika != null ? "#f59f0f" : "#ffffff",
          strokeWeight: a.dakika != null ? 4 : 2,
        },
        label: { text: a.hat.slice(0, 4), color: yaziRengi(renk), fontSize: "10px", fontWeight: "700" },
        title: `${a.hat}, kapı ${a.kapi}${a.dakika != null ? `, ${a.dakika} dk` : ""}`,
        zIndex: 20,
        clickable: false,
      });
    });
    return () => isaretler.forEach((m) => m.setMap(null));
  }, [harita, araclar]);

  // "Otobüsleri gör" açılınca biniş durağı ve en yakın araçlar ekrana sığdırılır (yalnızca bir kez; 10 sn'lik yenilemede değil)
  const sonOdak = useRef("");
  useEffect(() => {
    if (!odak) sonOdak.current = ""; // panel kapandı: bir sonraki açılışta yeniden sığdır
    if (!harita || !odak || odak.noktalar.length < 2 || sonOdak.current === odak.anahtar) return;
    sonOdak.current = odak.anahtar;
    const sinir = new google.maps.LatLngBounds();
    odak.noktalar.forEach((n) => sinir.extend(n));
    harita.fitBounds(sinir, { top: 72, right: 32, left: olcu.sol + 32, bottom: olcu.alt + 24 });
  }, [harita, odak, olcu.sol, olcu.alt]);

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

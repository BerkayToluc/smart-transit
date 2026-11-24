"use client";
import { useGoogleMap } from "@react-google-maps/api";
import { useEffect } from "react";
import type { Olcu } from "@/components/rota/Cekmece";
import { hatRengi, renkCoz } from "@/lib/modes";
import type { YakinKatmanVeri } from "@/lib/plan";
import { useTema } from "@/lib/tema";

// Durak işaretçisinin rengi: en "ağır" ulaşım türüne göre
const ONCELIK = ["metro", "rail", "tram", "ferry", "metrobus", "funicular", "cable_car", "bus"];
const ana = (modlar: string[]) => ONCELIK.find((m) => modlar.includes(m)) ?? "bus";
const kisalt = (ad: string) => (ad.length > 22 ? `${ad.slice(0, 21)}…` : ad);

interface Props {
  veri: YakinKatmanVeri | null;
  secili: string | null;
  onSec: (id: string) => void;
  olcu: Olcu;
}

/** Haritada konumunuz (mavi nokta), arama yarıçapı (kesikli daire), adlı durak işaretçileri ve seçili durağa noktalı yürüyüş yolu. */
export default function YakinKatman({ veri, secili, onSec, olcu }: Props) {
  const harita = useGoogleMap();
  const { etkin: tema } = useTema();

  // Konum, yarıçap ve duraklar; seçim değişince yalnızca vurgu güncellensin diye `secili` bağımlılıkta DEĞİL (aşağıda ayrı katman)
  useEffect(() => {
    if (!harita || !veri) return;
    const nesneler: { setMap: (m: null) => void }[] = [];
    const bogaz = renkCoz("var(--bogaz)");
    const mur = renkCoz("var(--murekkep)");
    const merkez = { lat: veri.konum.lat, lng: veri.konum.lng };

    const daire = new google.maps.Circle({
      map: harita, center: merkez, radius: veri.yaricap, clickable: false, zIndex: 1,
      strokeColor: bogaz, strokeOpacity: 0.85, strokeWeight: 2, fillColor: bogaz, fillOpacity: 0.07,
    });
    nesneler.push(daire);
    if (veri.konum.dogruluk && veri.konum.dogruluk > 25 && veri.konum.dogruluk < 400) {
      nesneler.push(new google.maps.Circle({
        map: harita, center: merkez, radius: veri.konum.dogruluk, clickable: false, zIndex: 2,
        strokeOpacity: 0, fillColor: "#4285f4", fillOpacity: 0.16,
      }));
    }
    // Konumunuz: Google Haritalar'daki gibi beyaz halkalı mavi nokta
    nesneler.push(new google.maps.Marker({
      map: harita, position: merkez, clickable: false, zIndex: 40, title: "Konumunuz",
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: "#4285f4", fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 3 },
    }));
    veri.duraklar.forEach((d) => {
      const renk = renkCoz(hatRengi(ana(d.modes)));
      const m = new google.maps.Marker({
        map: harita, position: { lat: d.lat, lng: d.lng }, zIndex: 20, title: `${d.name}, ${d.distance_m} m`,
        icon: {
          path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: renk, fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 2.5,
          labelOrigin: new google.maps.Point(0, 2.7),
        },
        label: { text: kisalt(d.name), color: mur, fontSize: "11px", fontWeight: "600", className: "harita-etiket" },
      });
      m.addListener("click", () => onSec(d.stop_id));
      nesneler.push(m);
    });

    const sinir = daire.getBounds();
    if (sinir) harita.fitBounds(sinir, { top: 72, right: 32, left: olcu.sol + 32, bottom: olcu.alt + 24 });
    return () => nesneler.forEach((n) => n.setMap(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [harita, veri, tema, olcu.sol, olcu.alt]);

  // Seçili durak: vurgulu halka ve konumdan durağa noktalı yürüyüş yolu (Google yürüyüş rotası; olmazsa düz noktalı çizgi)
  useEffect(() => {
    if (!harita || !veri || !secili) return;
    const d = veri.duraklar.find((x) => x.stop_id === secili);
    if (!d) return;
    let iptal = false;
    const bogaz = renkCoz("var(--bogaz)");
    const iskele = renkCoz("var(--iskele)");
    const merkez = { lat: veri.konum.lat, lng: veri.konum.lng };
    const hedef = { lat: d.lat, lng: d.lng };
    const halka = new google.maps.Marker({
      map: harita, position: hedef, clickable: false, zIndex: 35,
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 13, fillOpacity: 0, strokeColor: iskele, strokeWeight: 4 },
    });
    const yol = new google.maps.Polyline({
      map: harita, path: [merkez, hedef], strokeOpacity: 0, zIndex: 10,
      icons: [{ icon: { path: google.maps.SymbolPath.CIRCLE, scale: 3, fillColor: bogaz, fillOpacity: 1, strokeColor: "#ffffff", strokeWeight: 1 }, offset: "0", repeat: "11px" }],
    });
    new google.maps.DirectionsService()
      .route({ origin: merkez, destination: hedef, travelMode: google.maps.TravelMode.WALKING, region: "tr" })
      .then((r) => {
        const p = r.routes[0]?.overview_path;
        if (!iptal && p && p.length > 1) yol.setPath(p);
      })
      .catch(() => {
        /* yürüyüş rotası alınamadı: düz noktalı çizgi kalır */
      });
    const sinir = new google.maps.LatLngBounds();
    sinir.extend(merkez);
    sinir.extend(hedef);
    harita.fitBounds(sinir, { top: 96, right: 48, left: olcu.sol + 48, bottom: olcu.alt + 48 });
    return () => {
      iptal = true;
      halka.setMap(null);
      yol.setMap(null);
    };
  }, [harita, veri, secili, tema, olcu.sol, olcu.alt]);

  return null;
}

"use client";
// Google Haritalar yürüyüş rotası: konumdan/bir noktadan diğerine sokak ve kaldırım üzerinden yol. Sonuç önbelleklenir.
import { EN_KISA_YURUME_M, makulYurume } from "@/lib/yurumeMantik";

export interface YurumeSonucu {
  path: google.maps.LatLngLiteral[];
  metre: number;
  saniye: number;
}

const onbellek = new Map<string, YurumeSonucu | null>();
const anahtar = (a: google.maps.LatLngLiteral, b: google.maps.LatLngLiteral) =>
  `${a.lat.toFixed(5)},${a.lng.toFixed(5)}>${b.lat.toFixed(5)},${b.lng.toFixed(5)}`;

function duzMetre(a: google.maps.LatLngLiteral, b: google.maps.LatLngLiteral): number {
  const dLat = (a.lat - b.lat) * 111_000;
  const dLng = (a.lng - b.lng) * 111_000 * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  return Math.hypot(dLat, dLng);
}

/** İki nokta arasındaki yürüyüş yolu; çok kısa, alınamayan ya da makul olmayan yollarda null (çağıran düz çizgi çizer). */
export async function yurumeYolu(a: google.maps.LatLngLiteral, b: google.maps.LatLngLiteral): Promise<YurumeSonucu | null> {
  const duz = duzMetre(a, b);
  if (duz < EN_KISA_YURUME_M) return null;
  const k = anahtar(a, b);
  if (onbellek.has(k)) return onbellek.get(k) ?? null;
  try {
    const sonuc = await new google.maps.DirectionsService().route({
      origin: a,
      destination: b,
      travelMode: google.maps.TravelMode.WALKING,
      region: "tr",
    });
    const bacak = sonuc.routes[0]?.legs[0];
    const adimYolu = (bacak?.steps ?? []).flatMap((s) => (s.path ?? []).map((p) => ({ lat: p.lat(), lng: p.lng() })));
    const yol = adimYolu.length > 1 ? adimYolu : (sonuc.routes[0]?.overview_path ?? []).map((p) => ({ lat: p.lat(), lng: p.lng() }));
    const metre = bacak?.distance?.value ?? 0;
    const saniye = bacak?.duration?.value ?? 0;
    // Uçlar tam noktaya otursun (Google en yakın yola çeker): çizgi başlangıç/varış işaretçisine bağlansın
    const tam = yol.length > 1 && makulYurume(duz, metre) ? { path: [a, ...yol, b], metre, saniye } : null;
    onbellek.set(k, tam);
    return tam;
  } catch {
    onbellek.set(k, null); // anahtar/kota/ağ hatası: aynı çifti tekrar tekrar sorma
    return null;
  }
}

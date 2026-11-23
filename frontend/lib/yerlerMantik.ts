// Kayıtlı yerler (Eve / İşe / favoriler / son aramalar) için saf mantık: depolama ve React'ten bağımsız, node ile test edilir.
// Veriler yalnızca kullanıcının cihazında tutulur; bozuk/eski kayıtlar sessizce atılır.

export interface KayitliYer {
  id: string; // "enlem,boylam" (5 hane): aynı yer tek kayıt
  ad: string;
  lat: number;
  lng: number;
}

export interface Depo {
  ev: KayitliYer | null;
  is: KayitliYer | null;
  favoriler: KayitliYer[];
  son: KayitliYer[];
}

export const EN_COK_SON = 5;
export const EN_COK_FAVORI = 20;
export const AYNI_YER_M = 60; // bu mesafe içindeki aynı adlı kayıtlar aynı yer sayılır
const ENLEM: [number, number] = [40.7, 41.7];
const BOYLAM: [number, number] = [27.8, 30.0];

export const bosDepo = (): Depo => ({ ev: null, is: null, favoriler: [], son: [] });

export function yerOlustur(ad: string, lat: number, lng: number): KayitliYer {
  return { id: `${lat.toFixed(5)},${lng.toFixed(5)}`, ad: ad.trim().slice(0, 80), lat, lng };
}

function gecerliYer(y: unknown): y is KayitliYer {
  if (!y || typeof y !== "object") return false;
  const o = y as Record<string, unknown>;
  return (
    typeof o.ad === "string" && o.ad.trim().length > 0 && o.ad.length <= 80 &&
    typeof o.lat === "number" && Number.isFinite(o.lat) && o.lat >= ENLEM[0] && o.lat <= ENLEM[1] &&
    typeof o.lng === "number" && Number.isFinite(o.lng) && o.lng >= BOYLAM[0] && o.lng <= BOYLAM[1]
  );
}

const temiz = (y: unknown): KayitliYer | null => (gecerliYer(y) ? yerOlustur(y.ad, y.lat, y.lng) : null);

/** localStorage'tan okunan metni depoya çevirir; geçersiz/bozuk içerik boş depo ya da süzülmüş depo olur. */
export function depoCoz(metin: string | null): Depo {
  if (!metin) return bosDepo();
  let ham: unknown;
  try {
    ham = JSON.parse(metin);
  } catch {
    return bosDepo();
  }
  if (!ham || typeof ham !== "object") return bosDepo();
  const o = ham as Record<string, unknown>;
  const liste = (x: unknown, en: number) => (Array.isArray(x) ? x.map(temiz).filter((y): y is KayitliYer => y !== null).slice(0, en) : []);
  return { ev: temiz(o.ev), is: temiz(o.is), favoriler: liste(o.favoriler, EN_COK_FAVORI), son: liste(o.son, EN_COK_SON) };
}

export function mesafeM(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const dLat = (a.lat - b.lat) * 111_000;
  const dLng = (a.lng - b.lng) * 111_000 * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  return Math.hypot(dLat, dLng);
}

/** Aynı yer: koordinat birbirine AYNI_YER_M içinde. */
export const ayniYer = (a: KayitliYer, b: KayitliYer): boolean => mesafeM(a, b) <= AYNI_YER_M;

/** Son aramalara ekler: aynı yer varsa başa taşınır; en çok EN_COK_SON. */
export function sonEkle(d: Depo, yer: KayitliYer): Depo {
  return { ...d, son: [yer, ...d.son.filter((y) => !ayniYer(y, yer))].slice(0, EN_COK_SON) };
}

export const favoriMi = (d: Depo, yer: KayitliYer): boolean => d.favoriler.some((y) => ayniYer(y, yer));

/** Favori ekler (başa); en çok EN_COK_FAVORI, dolunca en eski düşer. */
export function favoriEkle(d: Depo, yer: KayitliYer): Depo {
  return { ...d, favoriler: [yer, ...d.favoriler.filter((y) => !ayniYer(y, yer))].slice(0, EN_COK_FAVORI) };
}

export const favoriSil = (d: Depo, yer: KayitliYer): Depo => ({ ...d, favoriler: d.favoriler.filter((y) => !ayniYer(y, yer)) });
export const evKaydet = (d: Depo, yer: KayitliYer | null): Depo => ({ ...d, ev: yer });
export const isKaydet = (d: Depo, yer: KayitliYer | null): Depo => ({ ...d, is: yer });
export const sonlariSil = (d: Depo): Depo => ({ ...d, son: [] });

export const bos = (d: Depo): boolean => !d.ev && !d.is && d.favoriler.length === 0 && d.son.length === 0;

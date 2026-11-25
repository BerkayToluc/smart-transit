// /api/plan istemcisi ve yanıt tipleri (sözleşme: docs/schema.md "POST /api/plan").
import { API_BASE, apiUrl } from "@/lib/api";

export type Mod = "bus" | "metrobus" | "metro" | "tram" | "funicular" | "cable_car" | "rail" | "ferry";
export type Tercih = "fastest" | "fewest_transfers" | "least_walking";

export interface Nokta {
  lat: number;
  lng: number;
  name?: string;
}

export interface PlanIstegi {
  origin: Nokta;
  dest: Nokta;
  depart_at?: string; // ISO 8601; boşsa şimdi
  arrive_by?: string; // ISO 8601: bu saatte ya da öncesinde varan, en geç kalkışlı rotalar
  modes?: Mod[];
  max_transfers?: number;
  max_walk_m?: number;
  preference?: Tercih;
  max_results?: number;
}

export interface Yer {
  name: string;
  lat: number;
  lng: number;
  stop_id?: string | null;
  time: string;
}

export interface Etap {
  type: "walk" | "transit";
  mode: string;
  route_short_name?: string | null;
  route_long_name?: string | null;
  route_id?: string | null;
  trip_id?: string | null;
  headsign?: string | null;
  from: Yer;
  to: Yer;
  num_stops: number;
  duration: number;
  distance_m?: number | null;
  polyline: [number, number][];
  geometry?: "resmi" | "durak"; // transit: resmî İETT güzergâh çizgisinden mi (resmi), durak sırasından mı (durak)
}

/** İlk otobüs bacağı için canlı bilgi (#22). source=canli: canlı araç bulundu; tarife: planlı tarifeye göre. */
export interface CanliBilgi {
  source: "canli" | "tarife";
  route: string;
  stop: string;
  stop_id: string;
  planned_departure: string;
  service_down?: boolean; // İETT canlı veri servisi yanıt vermedi
  no_vehicle?: boolean; // yaklaşan canlı araç görünmüyor
  missed?: boolean; // yaklaşan araçlar var ama siz durağa varmadan geçecek
  nearest_min?: number; // (missed) en yakın aracın durağa kalan dakikası
  reach_min?: number; // durağa şimdiden kaç dk sonra varırsınız
  gate?: string;
  arrives_in_min?: number; // araç durağa şimdiden kaç dk sonra gelir
  wait_min?: number; // durağa vardığınızda bekleyeceğiniz süre
  delay_min?: number; // tarifeye göre sapma (+: geç)
  better_option?: number; // daha iyi alternatifin indeksi
  better_gain_min?: number;
}

export interface Yolculuk {
  departure_time: string;
  arrival_time: string;
  total_duration: number;
  transfers: number;
  walk_distance: number;
  legs: Etap[];
  live?: CanliBilgi;
  adjusted_arrival_time?: string; // canlı gecikme eklenmiş güncel varış (yalnızca gecikme varsa)
}

export interface PlanYaniti {
  itineraries: Yolculuk[];
  neden?: string | null;
  mesaj?: string | null;
}

export class PlanHatasi extends Error {
  constructor(
    mesaj: string,
    public durum?: number,
  ) {
    super(mesaj);
    this.name = "PlanHatasi";
  }
}

const ALAN_ADLARI: Record<string, string> = {
  origin: "Başlangıç noktası",
  dest: "Varış noktası",
  lat: "enlemi",
  lng: "boylamı",
  max_transfers: "En çok aktarma",
  max_walk_m: "En çok yürüme",
  depart_at: "Kalkış zamanı",
  modes: "Ulaşım türü",
};

/** FastAPI doğrulama (422) hatasını kullanıcıya anlaşılır bir cümleye çevirir. */
function dogrulamaMesaji(detay: unknown): string {
  if (!Array.isArray(detay) || detay.length === 0) return "İstek geçerli değil.";
  const d = detay[0] as { loc?: unknown[]; msg?: string; type?: string };
  const yol = (d.loc ?? []).filter((x) => x !== "body").map(String);
  const nokta = yol[0] === "origin" || yol[0] === "dest";
  if (nokta && (d.type === "greater_than_equal" || d.type === "less_than_equal")) {
    return `${ALAN_ADLARI[yol[0]]} İstanbul sınırlarının dışında. Haritada İstanbul içinden bir yer seçin.`;
  }
  const ad = yol.map((p) => ALAN_ADLARI[p] ?? p).join(" ");
  return ad ? `${ad}: değer geçerli değil.` : "İstek geçerli değil.";
}

export async function planIste(govde: PlanIstegi, signal?: AbortSignal): Promise<PlanYaniti> {
  let yanit: Response;
  try {
    yanit = await fetch(apiUrl("/api/plan"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(govde),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new PlanHatasi(
      `Sunucuya (${API_BASE}) ulaşılamıyor. Backend çalışıyor mu? Kök klasörde "uvicorn main:app --reload" komutuyla başlatın; adres farklıysa frontend/.env.local içindeki NEXT_PUBLIC_API_URL değerini düzeltin.`,
    );
  }
  if (yanit.ok) return (await yanit.json()) as PlanYaniti;
  let detay: unknown = null;
  try {
    detay = (await yanit.json()).detail;
  } catch {
    /* gövde yok */
  }
  if (yanit.status === 422) throw new PlanHatasi(dogrulamaMesaji(detay), 422);
  if (typeof detay === "string") throw new PlanHatasi(detay, yanit.status);
  throw new PlanHatasi(`Rota hesaplanamadı (hata kodu ${yanit.status}). Biraz sonra tekrar deneyin.`, yanit.status);
}

// ---------------------------------------------------------------- yaklaşan otobüsler (GET /api/yaklasan)
export interface YaklasanArac {
  kapi_no: string;
  dakika: number;
  mesafe_km: number;
  hiz_kmh: number;
  yon: string;
  enlem: number;
  boylam: number;
}

export interface HatCanli {
  hat: string;
  mod: string;
  yon: string; // hattın bu yöndeki son durağı
  sure_dk: number | null; // biniş-iniş arası tarifedeki süre
  araclar: YaklasanArac[]; // biniş durağına yaklaşanlar, dakikaya göre sıralı
  tum_araclar: { kapi_no: string; enlem: number; boylam: number; yon: string }[]; // hattın tüm canlı araçları (harita)
  planli: string[]; // sıradaki planlı kalkışlar "14:20"
  canli_erisilemiyor?: boolean; // İETT canlı veri servisi yanıt vermedi ("araç yok"tan ayrı)
}

export interface YaklasanYaniti {
  binis: { stop_id: string; name: string; lat: number; lng: number };
  inis: { stop_id: string; name: string; lat: number; lng: number };
  hat_adlari: string[]; // bu iki durak arasında giden tüm otobüs hatları
  hatlar: HatCanli[];
}

export async function yaklasanIste(
  bas: string,
  bit: string,
  hatlar: string[] | null,
  oncelik: string | null,
  signal?: AbortSignal,
): Promise<YaklasanYaniti> {
  const q = new URLSearchParams({ bas, bit });
  if (hatlar && hatlar.length) q.set("hatlar", hatlar.join(","));
  if (oncelik) q.set("oncelik", oncelik);
  let yanit: Response;
  try {
    yanit = await fetch(apiUrl(`/api/yaklasan?${q}`), { signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new PlanHatasi("Canlı otobüs bilgisine ulaşılamıyor.");
  }
  if (!yanit.ok) {
    let detay = "";
    try {
      detay = (await yanit.json()).detail;
    } catch {
      /* gövde yok */
    }
    throw new PlanHatasi(typeof detay === "string" && detay ? detay : "Canlı otobüs bilgisi alınamadı.", yanit.status);
  }
  return (await yanit.json()) as YaklasanYaniti;
}

// ---------------------------------------------------------------- durak sayfası (GET /api/stops/{id}/departures, /api/stops/nearby)
export interface DurakKalkis {
  hat: string;
  mod: string;
  yon: string; // hattın bu yöndeki son durağı
  planli: { saat: string; dk: number }[]; // sıradaki planlı kalkışlar ("14:20", şimdiden dakika)
  canli: { dakika: number; kapi_no: string; mesafe_km: number }[]; // yalnızca otobüs: durağa yaklaşan canlı araçlar
  canli_denendi: boolean;
  canli_erisilemiyor: boolean;
}

export interface DurakBilgisi {
  stop_id: string;
  name: string;
  lat: number;
  lng: number;
  stop_ids: string[];
  modes: string[];
}

export interface DurakYaniti {
  stop: DurakBilgisi;
  departures: DurakKalkis[];
  toplam_hat: number;
  canli_erisilemiyor: boolean;
}

export interface YakinDurak {
  name: string;
  lat: number;
  lng: number;
  stop_id: string;
  stop_ids: string[];
  modes: string[];
  routes: string[];
  distance_m: number;
}

async function getir<T>(yol: string, hata: string, signal?: AbortSignal): Promise<T> {
  let yanit: Response;
  try {
    yanit = await fetch(apiUrl(yol), { signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new PlanHatasi("Sunucuya ulaşılamıyor. İnternet bağlantınızı kontrol edip tekrar deneyin.");
  }
  if (yanit.ok) return (await yanit.json()) as T;
  let detay: unknown = null;
  try {
    detay = (await yanit.json()).detail;
  } catch {
    /* gövde yok */
  }
  throw new PlanHatasi(typeof detay === "string" && detay ? detay : hata, yanit.status);
}

export const durakKalkislariIste = (stopId: string, limit: number, signal?: AbortSignal) =>
  getir<DurakYaniti>(`/api/stops/${encodeURIComponent(stopId)}/departures?limit=${limit}`, "Durak bilgisi alınamadı.", signal);

export const yakinDuraklarIste = (lat: number, lng: number, yaricap: number, signal?: AbortSignal) =>
  getir<{ stops: YakinDurak[] }>(`/api/stops/nearby?lat=${lat}&lng=${lng}&radius_m=${yaricap}&limit=12`, "Yakındaki duraklar alınamadı.", signal);

/** Haritada "Yakınımdaki duraklar" katmanı: arama merkezi (konumunuz), yarıçap ve duraklar. */
export interface YakinKatmanVeri {
  konum: { lat: number; lng: number; dogruluk: number | null };
  yaricap: number;
  duraklar: YakinDurak[];
}

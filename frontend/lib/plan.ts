// /api/plan istemcisi ve yanıt tipleri (sözleşme: docs/schema.md "POST /api/plan").
import { apiUrl } from "@/lib/api";

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
}

export interface Yolculuk {
  departure_time: string;
  arrival_time: string;
  total_duration: number;
  transfers: number;
  walk_distance: number;
  legs: Etap[];
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
    throw new PlanHatasi("Sunucuya ulaşılamıyor. İnternet bağlantınızı ve sunucunun çalıştığını kontrol edin.");
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

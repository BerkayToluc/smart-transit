// Plan formunun URL'ye yazılması / URL'den okunması (paylaşılabilir rota bağlantısı). Saf mantık: React ve tarayıcıdan bağımsız.
// Biçim: ?from=41.03700,28.98500&fn=Taksim&to=...&tn=...&t=k&d=2026-11-24T10:00&tercih=az_aktarma&modlar=metro,bus&yurume=1200
// Geçersiz ya da eksik parametreler sessizce yok sayılır. "Konumum" başlangıcı konum gizliliği için bağlantıya yazılmaz.

export interface UrlYer {
  lat: number;
  lng: number;
  ad: string;
}

export interface UrlDurum {
  bas: UrlYer | null;
  bit: UrlYer | null;
  zaman: { tip: "simdi" | "kalkis" | "varis"; deger: string };
  tercih: "fastest" | "fewest_transfers" | "least_walking";
  modlar: string[] | null; // null: hepsi
  maxYurume: number;
}

export const GECERLI_MODLAR = ["metro", "tram", "rail", "ferry", "metrobus", "bus", "funicular", "cable_car"];
const TERCIHLER = ["fastest", "fewest_transfers", "least_walking"] as const;
export const VARSAYILAN_YURUME = 800;
const ENLEM: [number, number] = [40.7, 41.7];
const BOYLAM: [number, number] = [27.8, 30.0];
const ZAMAN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const KONUMUM = "Konumum";

const nokta = (y: UrlYer) => `${y.lat.toFixed(5)},${y.lng.toFixed(5)}`;

/** Durumu sorgu dizgisine çevirir ("?..."); varsayılanlar yazılmaz, hiçbir şey yoksa boş metin. */
export function baglantiOlustur(d: UrlDurum): string {
  const q = new URLSearchParams();
  if (d.bas && d.bas.ad.trim() !== KONUMUM) {
    q.set("from", nokta(d.bas));
    if (d.bas.ad.trim()) q.set("fn", d.bas.ad.trim().slice(0, 80));
  }
  if (d.bit) {
    q.set("to", nokta(d.bit));
    if (d.bit.ad.trim()) q.set("tn", d.bit.ad.trim().slice(0, 80));
  }
  if ((d.zaman.tip === "kalkis" || d.zaman.tip === "varis") && ZAMAN.test(d.zaman.deger)) {
    q.set("t", d.zaman.tip === "kalkis" ? "k" : "v");
    q.set("d", d.zaman.deger);
  }
  if (d.tercih !== "fastest") q.set("tercih", d.tercih);
  if (d.modlar && d.modlar.length > 0 && d.modlar.length < GECERLI_MODLAR.length) q.set("modlar", d.modlar.join(","));
  if (d.maxYurume !== VARSAYILAN_YURUME) q.set("yurume", String(d.maxYurume));
  const s = q.toString();
  return s ? `?${s}` : "";
}

function noktaCoz(deger: string | null, ad: string | null): UrlYer | null {
  if (!deger) return null;
  const m = /^(-?\d{1,2}(?:\.\d+)?),(-?\d{1,3}(?:\.\d+)?)$/.exec(deger.trim());
  if (!m) return null;
  const lat = parseFloat(m[1]);
  const lng = parseFloat(m[2]);
  if (!(lat >= ENLEM[0] && lat <= ENLEM[1] && lng >= BOYLAM[0] && lng <= BOYLAM[1])) return null;
  const temiz = (ad ?? "").replace(/[\u0000-\u001f]/g, "").trim().slice(0, 80);
  return { lat, lng, ad: temiz };
}

/** Sorgu dizgisinden (başında "?" olsun olmasın) geçerli alanları okur; olmayanlar varsayılan değerinde kalır. */
export function baglantiCoz(arama: string): UrlDurum {
  const q = new URLSearchParams(arama);
  const durum: UrlDurum = {
    bas: noktaCoz(q.get("from"), q.get("fn")),
    bit: noktaCoz(q.get("to"), q.get("tn")),
    zaman: { tip: "simdi", deger: "" },
    tercih: "fastest",
    modlar: null,
    maxYurume: VARSAYILAN_YURUME,
  };
  const t = q.get("t");
  const d = q.get("d");
  if ((t === "k" || t === "v") && d && ZAMAN.test(d) && !Number.isNaN(Date.parse(`${d}:00+03:00`))) {
    durum.zaman = { tip: t === "k" ? "kalkis" : "varis", deger: d };
  }
  const tercih = q.get("tercih");
  if (TERCIHLER.includes(tercih as (typeof TERCIHLER)[number])) durum.tercih = tercih as UrlDurum["tercih"];
  const modlar = (q.get("modlar") ?? "").split(",").filter((m) => GECERLI_MODLAR.includes(m));
  if (modlar.length > 0 && modlar.length < GECERLI_MODLAR.length) durum.modlar = [...new Set(modlar)];
  const y = Number(q.get("yurume"));
  if (Number.isInteger(y) && y >= 100 && y <= 2000) durum.maxYurume = y;
  return durum;
}

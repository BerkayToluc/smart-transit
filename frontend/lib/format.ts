// Süre, saat ve mesafe biçimleri (Türkçe, kısa).

/** 3654 sn -> "1 sa 1 dk", 2520 sn -> "42 dk" */
export function sureMetni(sn: number): string {
  const dk = Math.max(1, Math.round(sn / 60));
  if (dk < 60) return `${dk} dk`;
  const sa = Math.floor(dk / 60);
  const kalan = dk % 60;
  return kalan ? `${sa} sa ${kalan} dk` : `${sa} sa`;
}

/** ISO zamanını "08:30" yapar (saat dilimi ISO'daki +03:00'dır; tarayıcı saat dilimine bağlı değildir). */
export function saatMetni(iso: string): string {
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : "";
}

/** ISO zamanından gece yarısından beri dakika (aynı gün içi farklar için). */
export function dakika(iso: string): number {
  return Math.round(new Date(iso).getTime() / 60000);
}

export function mesafeMetni(m: number): string {
  if (m < 950) return `${Math.round(m / 10) * 10} m`;
  return `${(m / 1000).toFixed(1).replace(".", ",")} km`;
}

/** İstanbul'daki şimdiki an, datetime-local biçiminde ("2026-11-23T08:30"); tarayıcı saat diliminden bağımsız. */
export function istanbulSimdi(): string {
  return new Date(Date.now() + 3 * 3600 * 1000).toISOString().slice(0, 16);
}

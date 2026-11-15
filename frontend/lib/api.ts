// Backend (FastAPI) adresi tek yerden okunur.
//
// NEXT_PUBLIC_API_URL tanımlı değilse yerel geliştirme adresi kullanılır.
// Not: Next.js NEXT_PUBLIC_ değişkenlerini build sırasında koda gömer; değeri
// değiştirince `npm run dev` / `npm run build` yeniden başlatılmalıdır. Gömme
// işlemi `process.env.NEXT_PUBLIC_API_URL` ifadesini birebir aradığı için bu
// satırı dinamik (örn. process.env[ad]) hale getirmeyin.
const VARSAYILAN_API_ADRESI = "http://localhost:8000";

export const API_BASE: string = (
  process.env.NEXT_PUBLIC_API_URL || VARSAYILAN_API_ADRESI
).replace(/\/+$/, "");

/** "/api/hatlar" gibi bir yolu tam backend adresine çevirir. */
export function apiUrl(yol: string): string {
  return `${API_BASE}${yol.startsWith("/") ? yol : `/${yol}`}`;
}

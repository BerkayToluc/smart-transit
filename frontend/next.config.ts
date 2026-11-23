import type { NextConfig } from "next";

// Backend adresi ön yüzde `lib/api.ts` üzerinden (NEXT_PUBLIC_API_URL) okunur;
// eskiden burada bulunan ve hiçbir yerde kullanılmayan "/api/python/*"
// yönlendirmesi kaldırıldı.
const nextConfig: NextConfig = {
  // Servis çalışanı her açılışta güncellik denetimi yapsın (önbelleğe takılıp eski sürümde kalmasın)
  async headers() {
    return [
      { source: "/sw.js", headers: [{ key: "Content-Type", value: "application/javascript; charset=utf-8" }, { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }] },
    ];
  },
};

export default nextConfig;

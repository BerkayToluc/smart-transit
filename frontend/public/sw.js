// SmartTransit servis çalışanı: uygulama kabuğu önbelleği ve çevrimdışı sayfası.
// Rota hesabı sunucuda yapılır; bu yüzden API istekleri ASLA önbelleğe alınmaz (canlı veri bayatlamasın).
const SURUM = "smarttransit-v1";
const KABUK = ["/", "/cevrimdisi.html", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (olay) => {
  olay.waitUntil(caches.open(SURUM).then((c) => c.addAll(KABUK)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (olay) => {
  olay.waitUntil(
    caches.keys().then((adlar) => Promise.all(adlar.filter((a) => a !== SURUM).map((a) => caches.delete(a)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (olay) => {
  const istek = olay.request;
  if (istek.method !== "GET") return;
  const url = new URL(istek.url);
  if (url.origin !== self.location.origin) return; // backend API, Google Haritalar ve yazı tipleri: tarayıcıya bırak
  if (url.pathname.startsWith("/api/")) return;

  // Sayfa gezintisi: önce ağ; ağ yoksa önbellekteki kabuk, o da yoksa çevrimdışı sayfası
  if (istek.mode === "navigate") {
    olay.respondWith(
      fetch(istek)
        .then((yanit) => {
          const kopya = yanit.clone();
          if (yanit.ok && url.pathname === "/") caches.open(SURUM).then((c) => c.put("/", kopya));
          return yanit;
        })
        .catch(async () => (await caches.match(istek, { ignoreSearch: true })) || (await caches.match("/")) || (await caches.match("/cevrimdisi.html"))),
    );
    return;
  }

  // Sürümlü, değişmez dosyalar (_next/static) ve simgeler: önce önbellek
  if (url.pathname.startsWith("/_next/static/") || /^\/icon-.*\.png$/.test(url.pathname)) {
    olay.respondWith(
      caches.match(istek).then(
        (bulunan) =>
          bulunan ||
          fetch(istek).then((yanit) => {
            if (yanit.ok) {
              const kopya = yanit.clone();
              caches.open(SURUM).then((c) => c.put(istek, kopya));
            }
            return yanit;
          }),
      ),
    );
  }
});

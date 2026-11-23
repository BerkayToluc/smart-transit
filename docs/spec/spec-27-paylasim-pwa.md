# Spec #27: Paylaşılabilir rota linki ve PWA

## Problem
Rota başkasına (WhatsApp) gönderilemiyor; URL durumu taşımıyor. Uygulama telefonda ana ekrana eklenemiyor ve kötü bağlantıda açılmıyor.

## Hedefler
- Plan formu URL'de tutulsun (`/?from=lat,lng,ad&to=...&t=...`): link paylaşınca aynı rota açılır.
- Ana ekrana eklenebilir (PWA), uygulama kabuğu çevrimdışı açılır; veri yoksa anlaşılır mesaj.

## Hedef dışı
- Çevrimdışı rota hesabı (graf sunucuda). Push bildirimi. Kısa link servisi.

## Gereksinimler
**P0**
- URL ↔ durum eşitleme: yer, saat ("şimdi" ise parametre yok), tercih, modlar. Geri/ileri tuşları çalışır.
  - Kabul: link yeni sekmede aynı seçenekleri (aynı saat verilmişse aynı sonuç) gösterir; geçersiz parametre sessizce yok sayılır.
- Web uygulama bildirimi (`manifest`), simge seti, `theme-color` (var), ana ekrana ekle.
**P1**
- Paylaş düğmesi (Web Share API, yoksa kopyala). Service worker: kabuk önbelleği, çevrimdışı sayfası.
**P2**
- Sosyal önizleme (OG görseli, rota özeti).

## Başarı ölçütleri
- Lighthouse PWA kontrolleri geçer. (A1 varsa) link ile açılan oturum payı.

## Açık sorular
- (Ürün, engelleyici) Yayın adresi (A2): link ve manifest `start_url` ona bağlı.
- (Mühendislik) Next.js sürümünde service worker/manifest yaklaşımı `node_modules/next/dist/docs`'tan okunacak.
- (Gizlilik) Linkte konum koordinatı bulunur; kullanıcıya paylaşmadan önce gösterilsin.

## Zamanlama
URL durumu P0'ı bağımsız (1–2 gün); PWA yayın kararından sonra.

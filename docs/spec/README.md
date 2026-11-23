# SmartTransit: ürün yol haritası ve spec'ler

Açık issue'ların ürün gözüyle gözden geçirilmesi (Product Management: spec + yol haritası). Her spec ilgili issue'nun
kabul kriterlerini genişletir; kod yazmadan önce **Açık sorular** (özellikle *engelleyici* olanlar) yanıtlanmalıdır.

## Ürün çerçevesi
- **Kim:** İstanbul'da her gün toplu taşıyla giden kişiler; aktarmalı, çok modlu (metro, Marmaray, vapur, metrobüs, otobüs) rota ister.
- **Temel vaat:** "Şimdi nereden nereye, hangi hatla, ne zaman varırım?" sorusuna Google/Moovit kadar güvenilir ve daha sade yanıt.
- **Ölçülen durum** (`/karsilastir`, planlı tarife): Google'a göre ortanca fark −10 dk; raylı yolculuklarda ±10 dk içinde, otobüs
  ağırlıklılarda 20–40 dk daha iyimser. Eksikler: M11, T5, M5 uzantısı (#42), Tuzla–Pendik–Büyükada (#47).
- **Ölçüm altyapısı yok:** kullanım analitiği yok. Spec'lerdeki metrikler şimdilik `/health`, istek günlüğü ve elle yapılan
  karşılaştırmayla ölçülür; analitik eklenirse (açık soru A1) hedefler canlı ölçülür.

## Issue sınıflandırması (kod gerçeğine göre)
| Issue | Durum | Öneri |
|---|---|---|
| #13 `POST /api/plan` | Yapıldı (mod filtresi, tercih, `arrive_by`, çeşitlilik) | Kapat |
| #16 `page.tsx` bölme | Geçersiz: "Hat Takibi" ekranı kaldırıldı, sayfa tek `RotaPlanla` | Kapat (gerek kalmadı) |
| #17 Rota Planla paneli | Yapıldı | Kapat |
| #18 Sonuç kartları, zaman çizelgesi | Yapıldı | Kapat |
| #19 Haritada mod renkli rota | Yapıldı (resmî güzergâh, işaretçiler); tema PR'ı #73 ile birlikte | Kapat (#73 doğrulandıktan sonra) |
| #20 Mobil, koyu mod, erişilebilirlik | Çekmece + koyu tema (#59) yapıldı; erişilebilirlik denetimi kaldı | Daralt: yalnızca erişilebilirlik denetimi ([spec-20](spec-20-erisilebilirlik-denetimi.md)) |
| #14, #15, #21–#28, #31, #42, #47 | Açık | Aşağıdaki spec'ler |

## Yol haritası (Şimdi / Sonra / Daha sonra)
**Şimdi: güven (veri doğruluğu ve temel)**
1. #42 M11, T5, M5 uzatması: havalimanı ve Sultanbeyli rotaları şu an hiç çıkmıyor ([spec](spec-42-eksik-rayli-hatlar.md)).
2. #47 Tuzla–Pendik–Büyükada vapuru ve resmî tatil takvimi ([spec](spec-47-vapur-adalar-tatil.md)).
3. #14 Durak arama ve yakındaki duraklar: #23 ve #24'ün temeli ([spec](spec-14-durak-arama.md)).

**Sonra: alışkanlık (tekrar kullanım)**
4. #24 Favoriler, son aramalar, Eve/İşe ([spec](spec-24-favoriler.md)).
5. #27 Paylaşılabilir rota linki ve PWA ([spec](spec-27-paylasim-pwa.md)).
6. #22 Canlı ETA destekli rota ([spec](spec-22-canli-eta-rota.md)).
7. #23 Durak sayfası ([spec](spec-23-durak-sayfasi.md)).

**Daha sonra: kapsam ve olgunluk**
8. #28 Hizmet uyarıları ([spec](spec-28-hizmet-uyarilari.md)): veri kaynağı belirsiz.
9. #25 Erişilebilir rota ([spec](spec-25-erisilebilir-rota.md)): veri kaynağı belirsiz.
10. #26 İstanbulkart ücret ([spec](spec-26-ucret.md)): güncel tarife verisi gerekir.
11. #21 i18n tr/en ([spec](spec-21-i18n.md)).
12. #15 Raylı/vapur geometrisi ([spec](spec-15-gecerlilik-geometri.md)).
13. #31 Docker compose ([spec](spec-31-docker.md)): yayına çıkış kararına bağlı (açık soru A2).

## Çapraz açık sorular
- **A1 Analitik:** Anonim, çerezsiz kullanım sayacı (örn. günlük plan sayısı) eklensin mi? (ürün sahibi, gizlilik)
- **A2 Yayın:** Uygulama herkese açık yayınlanacak mı, nerede (alan adı, barındırma)? #29/#31/#27 buna bağlı. (ürün sahibi)
- **A3 Veri güncelliği:** İBB çok modlu besleme 2018–2020 (+ 2022–23 parçaları). Düzenli veri yenileme süreci (aylık?) tanımlanmalı. (ürün sahibi, mühendislik)

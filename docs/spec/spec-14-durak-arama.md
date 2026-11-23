# Spec #14: Durak arama ve yakındaki duraklar

## Problem
Kullanıcı yalnızca adres/koordinat girebiliyor; "Kabataş iskelesi" ya da "Mecidiyeköy metrobüs" gibi bir durağı adıyla bulamıyor ve
bulunduğu yerin yakınındaki duraklara bakamıyor. #23 (durak sayfası) ve #24 (favori duraklar) için de durak kimliğiyle erişim gerekir.

## Hedefler
- Durak adıyla arama: ilk 3 harften sonra 300 ms içinde sonuç.
- "Yakınımdaki duraklar": verilen konumun 500 m çevresindeki duraklar, mesafeyle sıralı, hat ve mod bilgisiyle.
- Plan formunda durak adı, adres önerileriyle birlikte seçilebilsin.

## Hedef dışı
- Durağın canlı varış/kalkış listesi (#23). Harita üzerinde durak katmanı (ayrı iş). Adres (geocoding) araması: Google Places kalır.

## Kullanıcı hikâyeleri
- Yolcu olarak "Kabataş" yazınca iskeleyi, tramvayı ve füniküleri ayrı ayrı mod rozetiyle görmek isterim; doğru olanı seçerim.
- Yolcu olarak bulunduğum yere en yakın duraklardan hangi hatların geçtiğini görmek isterim.

## Gereksinimler
**P0**
- `GET /api/stops/search?q=&limit=` : ad eşleşmesi Türkçe karakter katlamalı (`i/İ/ı`, `ş/s`), önek ve alt dize; sonuç: `stop_id, name, lat, lng, modes[], routes[]` (en çok 12 hat).
  - Kabul: `q=kabatas` → "Kabataş" (füniküler, tramvay, vapur) döner; `q=ab` (2 harf) 422; 100 ms altında (bellek içi indeks).
- `GET /api/stops/nearby?lat=&lng=&radius_m=500&limit=` mesafeye göre sıralı; İstanbul sınırı dışı 422.
  - Kabul: aynı fiziksel istasyonun ayrı durakları (aktarma kümesi) tek satırda gruplanır (`cluster`).
- Yanıtlar `/api/plan` ile aynı `stop_id` biçimini kullanır; hız sınırı (#29) uygulanır.
**P1**
- Plan formu yer alanında önerilerde durakları adres önerilerinin üstünde göster (mod rozetiyle).
**P2**
- Hat adıyla arama (`34BZ`); durak favorileme (#24).

## Başarı ölçütleri
- Öncü: `/api/stops/search` p95 < 100 ms (istek günlüğünden).
- Gecikmeli: yer alanında durak seçimiyle başlatılan plan oranı (analitik varsa, A1).

## Açık sorular
- (Mühendislik, engelleyici değil) Çok kullanılan yazımlar için eş anlamlılar ("Üsküdar İskele", "Üsküdar vapur")?
- (Ürün) Aynı adlı yüzlerce otobüs durağı sonuçları boğmasın: otobüs durakları arama sonucunda sınırlansın mı? Öneri: istasyon türü (metro, tramvay, vapur, Marmaray, metrobüs) önde, otobüs durakları en fazla 5.

## Zamanlama
Bağımlılık yok (graf bellekte). #23 ve #24'ten önce yapılmalı. Küçük iş (1–2 gün).

# Spec #22: Canlı ETA destekli rota

## Problem
Rota planlayıcı planlı tarifeyi kullanır; otobüs bacağında "bir sonraki 401 ne zaman gelir?" gerçek konuma göre değil tarifeye göre hesaplanır.
Canlı araçlar bugün yalnızca "Otobüsleri gör" panelinde ayrı gösteriliyor; seçenek sıralamasını ve toplam süreyi etkilemiyor.
Karşılaştırmada otobüs ağırlıklı rotalarımız Google'dan 20–40 dk iyimser: bekleme ve gecikme gerçek veriyle düzeltilmeli.

## Hedefler
- İlk otobüs bacağında bekleme süresi canlı araç konumundan gelsin; kartta "yaklaşık X dk sonra" ve güncel varış saati görünsün.
- Canlı veri yoksa ya da servis erişilemiyorsa (#30 bayrağı) sessizce planlı tarifeye dönülsün ve bu açıkça belirtilsin.
- Geç kalan/yaklaşan araç nedeniyle bir sonraki alternatif daha iyiyse uyarı verilsin.

## Hedef dışı
- Sonraki bacaklarda (aktarma sonrası) canlı tahmin (belirsizlik büyür). Metro/vapur için canlı veri (kaynak yok). Bildirim (push).

## Kullanıcı hikâyeleri
- Yolcu olarak 34 numaralı hat için durakta ne kadar bekleyeceğimi gerçek araç konumuna göre görmek isterim ki erken çıkıp çıkmayacağıma karar vereyim.
- Yolcu olarak canlı veri alınamadığında bunu bilmek isterim ki tahmini tarifeye göre okuyayım.

## Gereksinimler
**P0**
- `/api/plan` yanıtına ilk otobüs bacağı için `live: {wait_min, source: "canli"|"tarife"}` alanı (mevcut `/api/yaklasan` mantığını yeniden kullan; ek İETT çağrısı yok, 15 sn önbellek).
  - Kabul: canlı araç varsa `wait_min` `/api/yaklasan` ile ±1 dk tutarlı; servis yoksa `source: "tarife"` ve kartta "planlı" etiketi.
- Ön yüz kartta ve adım listesinde canlı/planlı ayrımını gösterir.
**P1**
- Toplam süre ve varış saati canlı bekleme ile güncellenir; seçenek sıralaması (maliyet) bunu hesaba katar.
- "Daha iyi alternatif var" uyarısı: canlı bekleme ≥ 10 dk ve alternatif ≥ 5 dk erken.
**P2**
- Gecikme geçmişinden hat başına öğrenilmiş katsayı (otobüs süresi düzeltmesi).

## Başarı ölçütleri
- Öncü: canlı bacak oranı (planlarda `source=canli` payı); canlı bekleme tahmininin gerçekleşenden sapması (örnek kayıt, elle).
- Gecikmeli: Google ile otobüs ağırlıklı rota farkının (`/karsilastir`) ortancası −10 dk → −5 dk.

## Açık sorular
- (Veri, engelleyici) İETT SOAP servisinin kota/limitleri: kalabalık kullanıcıda hat başına 15 sn önbellek yeterli mi? (İBB şartları)
- (Ürün) Canlı veriyle sıralama değişirse kullanıcı sonucun "zıplamasından" rahatsız olur mu? Öneri: sıralama yalnızca ilk yüklemede canlıyı kullansın, yenilemede yalnızca etiketler güncellensin.

## Zamanlama
#30 (dayanıklılık) tamamlandı; #14'ten bağımsız. Orta iş (3–5 gün).

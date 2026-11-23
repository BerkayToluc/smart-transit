# Spec #47: Vapur Tuzla–Pendik–Büyükada (İDO) ve resmî tatil takvimi

## Problem
Vapur verisi Şehir Hatları kitapçığından (29 hat, 42 iskele) üretildi; Tuzla–Pendik–Büyükada hatları ve turistik turlar dışarıda. Ayrıca takvim yalnızca hafta günü
bitmaskesine dayanır: bayram/resmî tatil günlerinde tarife (pazar tarifesi) uygulanmaz, o günlerde planlar yanlış olur.

## Hedefler
- Tuzla–Pendik–Büyükada hatları rotalanabilir olsun.
- Resmî tatil günlerinde pazar (ya da tatil) tarifesi kullanılsın.

## Hedef dışı
- Turistik Boğaz turları. Hava koşuluna bağlı iptaller (#28).

## Gereksinimler
**P0**
- Tuzla–Pendik–Büyükada seferleri `data/vapur.json`'a (kural ya da açık sefer); iskele koordinatları doğrulanmış.
  - Kabul: Pendik → Büyükada `rota` komutunda vapur bacağı; sefer saatleri kaynakla birebir.
- Tatil takvimi: `data/tatiller.json` (yıl bazlı resmî tatil/bayram günleri); planlayıcı `gun` yerine takvim günü tipini (hafta içi/cumartesi/pazar/tatil) kullanır.
  - Kabul: bayram günü sorgusunda pazar tarifesi seçilir; test (örn. 2026-05-27 Kurban Bayramı için doğrulanmış tarih).
**P1**
- Yıllık tatil verisini güncelleme betiği ve belgesi; kış/yaz tarife dönemi.
**P2**
- Tatil günü için hat bazlı özel tarife.

## Başarı ölçütleri
- Tatil günü planlarında pazar tarifesi %100; Adalar çiftlerinde rota bulunma %100.

## Açık sorular
- (Veri, engelleyici) İDO/Şehir Hatları güncel Adalar tarifesi ve iskele konumları (kaynak ve lisans).
- (Mühendislik) Mevcut `gtfs_calendar` hafta bitmaskesi tatil günlerini ifade edemez: bit maskesi + istisna günleri tablosu şeması (`docs/schema.md`'ye yazılmalı).

## Zamanlama
**Şimdi** (#42 ile birlikte). Tatil takvimi altyapısı küçük (1–2 gün), Adalar verisi 2–3 gün.

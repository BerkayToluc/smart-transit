# Spec #15: Raylı/vapur rota geometrisi ve altın-sonuç testleri

## Problem
Otobüs ve metrobüs bacakları resmî İETT çizgisiyle çiziliyor; metro, tramvay, Marmaray ve vapur ise durak sırasındaki düz çizgilerle
(ya da Google snapping ile) çiziliyor. Marmaray gibi uzun rayda çizgi gerçek hattı izlemiyor. Altın-sonuç (bilinen rota) testleri de
henüz yok; algoritma değişikliklerinin gerilemesi elle fark ediliyor.

## Hedefler
- Raylı ve vapur bacakları gerçek hat geometrisiyle çizilsin (Google'a bağımlılık kalkar).
- 10–15 bilinen yolculuk için "altın sonuç" testi: değişiklikte hat dizisi ve süre bandı korunur.

## Hedef dışı
- Yaya rotasını sokak ağına oturtmak. Gerçek zamanlı çizim animasyonu.

## Gereksinimler
**P0**
- Raylı hatlar için geometri kaynağı belirle ve içe aktar (İBB raylı sistem hat verisi / OSM). Çıktı: `gtfs_data/` altında dizinlenmiş hat çizgileri, `geometry: "resmi"` ile servis edilir.
  - Kabul: Üsküdar–Sirkeci Marmaray bacağı haritada Boğaz tüneli hattını izler (durak sırası düz çizgisi değil).
- Altın testler: `tests/test_altin_rotalar.py`, sentetik değil kayıtlı küçük örnek graf (ya da işaretli, `@pytest.mark.gercek_veri`, yerelde koşan) ile en az 10 çift; aktarma sayısı ve süre bandı (±%15) doğrulanır.
**P1**
- Vapur hatları için iskeleler arası deniz çizgisi (karadan geçmesin).
**P2**
- Gerçek zamanlı araç konumuyla çizgi üstünde animasyon.

## Başarı ölçütleri
- Raylı ve vapur bacaklarının %100'ü `geometry: "resmi"` (yedekleme `durak` yalnızca hat verisi eksikse).
- Altın test paketi CI'da (ya da yerel koşuda) yeşil; algoritma PR'larında zorunlu.

## Açık sorular
- (Mühendislik, engelleyici) Hat geometrisi kaynağı: İBB açık veri mi, OSM mi? Lisans ve kapsam doğrulanmalı.
- (Mühendislik) Gerçek veri (SQLite) CI'da yok: altın testler yerelde mi, küçültülmüş örnek veriyle mi çalışsın?

## Zamanlama
#42 (yeni hatlar) ile birlikte düşünülmeli: yeni hatların geometrisi de aynı hatta girsin.

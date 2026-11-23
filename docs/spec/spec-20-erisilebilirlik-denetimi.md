# Spec #20 (daraltılmış): Erişilebilirlik denetimi

## Problem
Mobil çekmece ve koyu tema tamamlandı (#59/#73); issue'nun kalan parçası erişilebilirlik. Ekran okuyucu, klavye ve kontrast için sistematik
bir denetim yapılmadı; yalnızca tema renkleri hesapla (≥4,5:1) doğrulandı.

## Hedefler
- Tüm akış (yer seç, rota hesapla, seçenek aç, "Otobüsleri gör") yalnızca klavyeyle tamamlanabilsin.
- Axe/Lighthouse erişilebilirlik puanı ≥ 95; kritik ihlal yok.

## Hedef dışı
- WCAG AAA. Harita içi nesnelerin ekran okuyucu betimlemesi (harita ayrı bir araçtır; rota adımları listesi eşdeğer bilgiyi verir).

## Gereksinimler
**P0**
- Klavye: odak sırası mantıklı, her etkileşim `Enter/Space` ile çalışır, çekmece `Esc` ile kapanır; odak halkası her temada görünür.
- Etiketler: tüm form alanlarında görünür/`aria-label`; sonuç alanı `aria-live` (var) ve yükleme durumu bildirilir.
- Dokunma hedefi ≥ 44 px (mobil): seçiciler, tema düğmeleri (şimdi 32 px, büyütülecek).
**P1**
- `prefers-reduced-motion` ile tüm geçişler kapalı (kısmen var), hareketli şerit animasyonları denetlensin.
- Renk tek başına bilgi taşımasın (mod rengi + ikon + ad: var, doğrulanacak).

## Başarı ölçütleri
- Axe otomatik tarama 0 kritik/ciddi ihlal; Lighthouse erişilebilirlik ≥ 95 (masaüstü + mobil).

## Açık sorular
- (Tasarım) Tema düğmeleri 44 px olunca başlık düzeni mobilde nasıl kalsın?

## Zamanlama
Küçük iş; #73 merge sonrası.

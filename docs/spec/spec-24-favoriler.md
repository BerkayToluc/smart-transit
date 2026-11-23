# Spec #24: Favoriler, son aramalar, Eve/İşe kısayolları

## Problem
Çoğu yolculuk tekrar eder (ev ↔ iş). Her seferinde iki adres yazmak, mobilde özellikle, yavaş ve hata eğilimli.

## Hedefler
- Tekrar eden yolculuğu iki dokunuşla başlatmak: "Eve", "İşe" kısayolları, son 5 arama, favori yerler.
- Veriler yalnızca kullanıcının cihazında (hesap/oturum yok).

## Hedef dışı
- Hesap, cihazlar arası eşitleme (sonraki aşama). Otomatik "evi" tahmin etme. Sunucuda kişisel veri saklama.

## Kullanıcı hikâyeleri
- Yolcu olarak "Eve" yerimi bir kez kaydedip sonra tek dokunuşla oraya rota istemek isterim.
- Yolcu olarak son aradığım yerleri yer alanında önerilerde görmek isterim.
- Yolcu olarak kayıtlı yerlerimi silebilmek isterim (gizlilik).

## Gereksinimler
**P0**
- Yer alanı boşken/odaktayken öneri listesi: Eve, İşe (kayıtlıysa), son 5 arama, favoriler (en çok 20).
  - Kabul: seçilen kayıt koordinat+ad ile alanı doldurur; sayfa yenilense de saklı (`localStorage`); depolama yoksa özellik gizlenir, hata vermez.
- Yer kaydetme: yer seçiliyken "Eve/İşe olarak kaydet" / "Favori ekle"; düzenle ve sil.
**P1**
- "Eve git" kısayolu ana ekranda: mevcut konum → ev, tek dokunuşla plan.
- Son aramalar Eve/İşe'yle çakışırsa tekilleştir.
**P2**
- Dışa/içe aktarma; hesaplı eşitleme.

## Başarı ölçütleri
- Öncü (A1 varsa): kısayol/öneriyle başlatılan plan oranı ≥ %30. Aksi hâlde elle kullanım denemesi: 2 dokunuşta plan.
- Hata: depolama kapalıyken 0 çökme.

## Açık sorular
- (Ürün) Konum gizliliği: kayıtlı yerler yalnızca cihazda kalır ve uygulama içinde "Verileri sil" bulunur: yeterli mi? (hukuk/KVKK)
- (Tasarım) Öneri listesi yer alanının açılır paneli mi, ayrı bölüm mü?

## Zamanlama
Bağımlılık: #14 (durak adıyla favori) P1 için; P0 bağımsız. Küçük-orta (2–3 gün).

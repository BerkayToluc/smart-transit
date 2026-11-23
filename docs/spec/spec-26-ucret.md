# Spec #26: İstanbulkart ücret ve aktarma indirimi hesabı

## Problem
Yolcular rotanın kaça mal olacağını bilmek ister; İstanbulkart aktarma indirimi hesabı karmaşıktır (mod ve zaman penceresi). Google/Moovit ücret gösterir, bizde yok.

## Hedefler
- Her rota kartında tahmini ücret (tam kart) ve indirimli aktarma sonrası toplam.

## Hedef dışı
- Abonman/öğrenci/indirimli kart türleri (ilk sürümde yalnızca tam fiyat; sonra). Ödeme. Mobil biletleme.

## Gereksinimler
**P0**
- Güncel tarife tablosu (`data/ucret.json`): mod bazlı biniş ücreti, aktarma indirimi kuralları, geçerlilik tarihi. **Sayılar resmî kaynaktan alınmalı ve tarih etiketlenmeli**; kod sabit ücret taşımaz.
  - Kabul: `/api/plan` her seçenek için `fare: {total, currency: "TRY", valid_from, estimate: true}`; kural dosyası değişince kod değişmez.
- Kartta "~X ₺ (tahmini)"; veri eski ise uyarı.
**P1**
- Kart türü seçimi (tam/öğrenci/60+). Aktarma penceresi (süre sınırı) hesabı.
**P2**
- Haftalık/aylık maliyet özeti.

## Başarı ölçütleri
- (Elle) 10 örnek rotada Google/Moovit veya resmî hesaplayıcıyla ücret eşleşmesi ≥ %90; farklar belgeli.

## Açık sorular
- (Veri, **engelleyici**) Resmî güncel tarife ve aktarma kuralları (İBB/İstanbulkart). Enflasyonla sık değişir: güncelleme sorumlusu kim?
- (Hukuk/Ürün) "Tahmini" ibaresi yeterli mi? Yanlış ücret güveni zedeler.

## Zamanlama
Kural verisi bulununca küçük iş (2 gün); düzenli güncelleme maliyeti sürekli.

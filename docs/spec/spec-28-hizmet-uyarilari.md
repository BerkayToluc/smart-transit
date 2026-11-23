# Spec #28: Hizmet uyarıları / duyurular rozeti

## Problem
Planlı tarifeye göre önerilen bir hat arıza, iptal ya da yoldaki kapanma nedeniyle çalışmıyor olabilir; kullanıcı bunu rota seçtikten sonra öğrenir.

## Hedefler
- Rotadaki hatları etkileyen güncel duyuruları kartta rozetle göster.

## Hedef dışı
- Duyuru yazma/yönetim. Duyuruya göre otomatik yeniden rota (sonraki sürüm). Bildirim.

## Gereksinimler
**P0**
- Kaynak belirle ve kullan (İBB/İETT duyuruları, Metro İstanbul duyuruları). Hat kodu ile eşleştirilmiş, tarihli, önbellekli (örn. 5 dk) uyarı listesi.
  - Kabul: `/api/plan` etap başına `alerts[]` (başlık, özet, kaynak, bitiş) döner; uyarısız rotada alan yok.
- Kartta uyarı rozeti; dokununca özet metin ve kaynak bağlantısı.
**P1**
- Ciddiyet (bilgi/aksama/iptal) ve sıralamada hafif ceza. `/health`'e kaynak sağlığı.
**P2**
- Asansör arızası (#25), vapur seferi iptali (hava durumu).

## Başarı ölçütleri
- Kaynağın başarı oranı ≥ %95 (`/health`); uyarı gecikmesi kaynağa göre ≤ 10 dk.

## Açık sorular
- (Veri, **engelleyici**) Makine okunur, güvenilir bir duyuru kaynağı var mı? Bulut IP'lerinden erişim (İBB portalı bulutu engelliyor olabilir, #42'deki gibi).
- (Hukuk) Üçüncü taraf duyurunun yeniden yayımı koşulları.

## Zamanlama
Veri kaynağına bağlı. Kaynak yoksa ertelenir (kaynak araştırması 1 gün).

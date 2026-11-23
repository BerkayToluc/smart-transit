# Spec #25: Erişilebilir rota filtresi (asansör / tekerlekli sandalye)

## Problem
Tekerlekli sandalye kullanan, bebek arabalı ya da hareket kısıtlı yolcular için asansörsüz istasyon veya merdivenli aktarma rotayı kullanılamaz kılar.
Bugün rota bu bilgiyi hiç bilmiyor.

## Hedefler
- "Erişilebilir rota" seçeneği: yalnızca asansörlü/rampalı istasyon ve erişilebilir araçlarla, merdivenli aktarmasız rota.
- Bilginin belirsiz olduğu yerde dürüst uyarı.

## Hedef dışı
- Kaldırım/yaya yolu erişilebilirliği (sokak ağı verisi yok). Asansör anlık arıza bilgisi (kaynak yok, #28 ile birlikte sonra).

## Gereksinimler
**P0**
- Veri: istasyon erişilebilirliği için kaynak belirle (GTFS `wheelchair_boarding`, Metro İstanbul/İBB istasyon bilgisi). Her durağa `erisilebilir: evet|hayır|bilinmiyor`.
  - Kabul: veri kaynağı ve tarihi `docs/veri-kaynaklari.md`'de; kapsam raporu (yüzde kaç durak biliniyor).
- Planlayıcı: filtre açıkken "hayır" olan duraklarda biniş/iniş/aktarma yok; "bilinmiyor" olanlar ayrı bir ayar (varsayılan: izinli ama kartta uyarı).
**P1**
- Kartta her etap için erişilebilirlik rozeti; aktarmada asansör bilgisi.
**P2**
- Asansör arızası uyarısı (#28).

## Başarı ölçütleri
- Kapsam: raylı istasyonların ≥ %90'ında erişilebilirlik bilgisi var.
- (Elle) 10 örnek rotada filtre açıkken hiçbir etapta "hayır" durak yok.

## Açık sorular
- (Veri, **engelleyici**) Güvenilir, güncel bir kaynak var mı? Yoksa bu spec uygulanamaz; önce kaynak araştırması (1–2 gün) yapılmalı.
- (Ürün) Yanlış "erişilebilir" bilgisi kullanıcıya zarar verir: bilgi bilinmiyorsa filtre varsayılan olarak ne yapsın? (öneri: kesin evet olanlarla sınırlı)
- (Hukuk) Sorumluluk reddi metni.

## Zamanlama
Veri kaynağına bağlı; "Daha sonra". Veri bulunursa orta iş (1 hafta).

# Spec #42: Eksik raylı hatlar (M11, T5, M5 uzatması, M4 uzantısı)

## Problem
Çok modlu İBB beslemesi bazı hatları içermiyor. İstanbul Havalimanı → Taksim için Google "H-6 > M11 > M2" önerirken bizde yalnızca otobüs
yolları var (ya da hiç rota yok). Havalimanı yolcuları en yüksek değerli kullanıcı ve bugün onlara cevap veremiyoruz.

## Hedefler
- M11 (Gayrettepe–İstanbul Havalimanı), T5 (Eminönü–Alibeyköy), M5 Sultanbeyli uzatması ve M4 Sabiha Gökçen uzantısı rotalarda kullanılabilsin.
- `/karsilastir` sayfasında İstanbul Havalimanı → Taksim çifti metro içeren bir rota göstersin.

## Hedef dışı
- Yeni hatların gerçek zamanlı bilgisi. Marmaray dışındaki banliyö hatları (ayrı issue).

## Gereksinimler
**P0**
- M11 elle tanımlı besleme (Marmaray gibi): istasyon konumları ve resmî tarifeden `ilk/son/her X dk` kuralları (`data/m11.json`, `app/gtfs/manual.py`).
  - Kabul: `hatlar` raporunda M11 doğru durak sırası ve makul süreyle; `rota` komutu İstanbul Havalimanı → Taksim'de M11 içeren seçenek üretir.
- Aktarma: M11 Gayrettepe istasyonu M2'ye (Gayrettepe) bağlı; `aktarma` komutu bağlantıyı üretir.
- Kaynak ve veri tarihi `docs/veri-kaynaklari.md`'de.
**P1**
- T5 (kural tabanlı), M5 Çekmeköy–Sultanbeyli, M4 Tavşantepe–Sabiha Gökçen (beslemede yoksa).
- Hat geometrisi (#15) ve hat rengi (M11 ve T5 için `HAT_RENKLERI` girdisi var).
**P2**
- Gelecekte açılan hatlar için "yeni hat ekleme" kılavuzu.

## Başarı ölçütleri
- `/karsilastir` İstanbul Havalimanı → Taksim "yok" değil; Google ile süre farkı ±20 dk.
- Havalimanı ve Sultanbeyli çiftlerinde rota bulunma oranı %100.

## Açık sorular
- (Veri, engelleyici) M11 resmî tarife ve istasyon koordinatları kaynağı: TCDD sayfası mı, Metro İstanbul API'si mi? (bulut sunucularından açılmıyor olabilir; yerelde denenmeli)
- (Ürün) M11'in Halkalı uzantısı ve açık/kapalı durum bilgisi.

## Zamanlama
**Şimdi.** Veri araştırması 1 gün + uygulama 2 gün. #11 (aktarmalar) ve #8–#9 altyapısına dayanır (tamam).

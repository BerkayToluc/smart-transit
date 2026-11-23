# Spec #23: Durak sayfası ve "yakınımdaki duraklar"

## Problem
Yolcu çoğu zaman rota değil "bu durağa şimdi ne geliyor?" bilmek ister. Uygulama yalnızca rota planı üzerinden canlı araç gösteriyor.

## Hedefler
- Bir durağın sayfası: geçen tüm hatlar, bir sonraki planlı kalkışlar, otobüslerde canlı kalan dakika.
- Ana ekranda "Yakınımdaki duraklar" kartı (konum izniyle).

## Hedef dışı
- Metro/vapur gerçek zamanlı (kaynak yok; yalnızca planlı). Durak yorumu/fotoğrafı. Bildirim.

## Kullanıcı hikâyeleri
- Yolcu olarak durakta dururken hangi otobüsün kaç dakikada geleceğini görmek isterim.
- Yolcu olarak yakınımdaki en yakın metro/vapur duraklarını görmek isterim.

## Gereksinimler
**P0**
- `GET /api/stops/{stop_id}/departures?limit=` : hat, yön, sıradaki planlı kalkışlar (bugünün takvimine göre); otobüslerde `canli_dk` (varsa).
  - Kabul: canlı araç yoksa yalnızca planlı saatler; servis yoksa `canli_erisilemiyor: true` (#30 ile aynı biçim).
- Durak sayfası (`/durak/[id]` ya da çekmecede görünüm) ve "Yakınımdaki duraklar" kartı; #14 uçlarını kullanır.
**P1**
- Duraktan "buradan git" ile plan formunu doldur; favori durak (#24).
**P2**
- Hat filtresi, harita üzerinde durak odağı.

## Başarı ölçütleri
- Öncü: durak sayfası yükleme p95 < 1 sn (istek günlüğü). Gecikmeli (A1 varsa): durak sayfası oturum payı.

## Açık sorular
- (Mühendislik, engelleyici) Durak başına tüm hatlar için canlı veri 1 çağrı değil hat sayısı kadar SOAP çağrısıdır: limit ve önbellek stratejisi (öneri: yalnızca ilk 6 hat canlı).
- (Tasarım) Çekmece mi, ayrı sayfa mı? (Paylaşılabilir link için ayrı yol daha iyi, #27)

## Zamanlama
Bağımlılık: #14. Orta iş (3–4 gün).

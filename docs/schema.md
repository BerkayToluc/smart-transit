# Çok modlu toplu taşıma şeması (`gtfs_*` tabloları)

Aktarmalı rota planlayıcının (Faz 2) kullanacağı veri modeli. GTFS'e dayanır, ama bu projenin
veri sorunlarına (docs/veri-kaynaklari.md) göre uyarlanmıştır. Kod: `app/gtfs/`.

**Mevcut canlı takip tabloları (`hatlar`, `duraklar`, `otobusler`, `guzergah_noktalari`) AYNEN
kalır**; yeni tablolar yanlarına eklenir (`gtfs_` öneki) ve uygulama açılırken oluşur.

## Temel kararlar
1. **Kaynak önekli kimlikler.** Her kimliğin başına besleme kimliği eklenir: `iett:292235`,
   `ibb:292235`. Farklı kurumların beslemelerinde aynı ham kimlik çakışabildiği için.
2. **Besleme (`feed_id`) her tabloda.** Bir besleme tekrar yüklenirse yalnızca o beslemenin kayıtları
   silinip yeniden eklenir; diğerleri etkilenmez.
3. **Saatler saniye olarak** (gece yarısından beri): `25:20:00` = 91200. 24 saati aşabilir; gece
   yarısından sonraki seferler bir önceki günün hizmeti sayılır.
4. **Mod hesaplanır.** `route_type` kaynakta güvenilmez (Marmaray `1`, minibüs `9`), bu yüzden
   `gtfs_route.mode` ayrıca hesaplanır; ham değer `route_type`'ta korunur.
5. **Takvim tarihleri yok sayılır.** Çoğu hizmetin `end_date`'i 31.12.2024. Planlama yalnızca haftanın
   günlerine bakar. Hiçbir günü işaretli olmayan hizmetler hiç çalışmaz.
6. **Aralıklı seferler ham saklanır** (`gtfs_frequency`); gerçek seferlere açma planlama aşamasında
   yapılır (`app/gtfs/rules.py`).

## Tablolar
| Tablo | Anahtar | Önemli sütunlar |
|---|---|---|
| `gtfs_feed` | `id` | `name`, `data_date` (verinin kendi tarihi), `source_note`, `imported_at` |
| `gtfs_agency` | `id` | `feed_id`, `name`, `url`, `timezone` |
| `gtfs_stop` | `id` | `feed_id`, `code`, `name`, `lat`, `lon`, `location_type` (0 durak, 1 istasyon), `parent_station`, `wheelchair_boarding` |
| `gtfs_route` | `id` | `feed_id`, `agency_id`, `short_name`, `long_name`, `route_type` (ham), **`mode`** |
| `gtfs_calendar` | `service_id` | `monday`…`sunday` (bool), `start_date`, `end_date` (ham) |
| `gtfs_calendar_date` | `service_id`, `date` | `exception_type` (1 eklendi, 2 kaldırıldı); mevcut beslemelerde boş |
| `gtfs_trip` | `id` | `feed_id`, `route_id`, `service_id`, `headsign`, `direction_id`, `shape_id`, `wheelchair_accessible` |
| `gtfs_stop_time` | `trip_id`, `stop_sequence` | `stop_id`, `arrival_secs`, `departure_secs`, `pickup_type`, `drop_off_type` |
| `gtfs_frequency` | `id` | `trip_id`, `start_secs`, `end_secs`, `headway_secs`, `exact_times` |
| `gtfs_transfer` | `id` | `from_stop_id`, `to_stop_id`, `transfer_type`, `min_transfer_secs`, `source` (feed/manual/auto) |

İlişkiler: `route → agency`, `trip → route`, `stop_time → trip, stop`, `frequency → trip`,
`transfer → stop`. `trip.service_id` bilerek yabancı anahtar DEĞİL (bazı beslemelerde takvimde
olmayan hizmet kimlikleri var).

**Büyüklük uyarısı:** `gtfs_stop_time` en büyük tablodur (İETT için yaklaşık bir milyon satır,
indeksleriyle yüzlerce MB olabilir). Neon ücretsiz planında yer sınırı var; #7'de İETT
`stop_times`'ın veritabanına mı yoksa yalnızca derlenmiş graf dosyasına mı yükleneceği
ölçülerek karar verilecek.

## Modlar (`gtfs_route.mode`)
`bus`, `metrobus`, `minibus`, `taxi`, `metro`, `tram`, `funicular`, `cable_car`, `rail`, `ferry`, `other`.

Belirleme sırası (`app/gtfs/modes.py`): hat adı kuralları (ör. metrobüs hat kodları) → kurum kuralları
(ör. TCDD → `rail`) → `route_type` (standart + genişletilmiş GTFS numaraları ve 9 = minibüs, 10 = taksi
dolmuş).

## Besleme ayarları (`app/gtfs/feeds.py`)
`FeedConfig`: besleme kimliği, bozuk kodlama düzeltmesi, mod kuralları, dışarıda bırakılacak modlar ve
hatlar. Hazır ayarlar: `IETT` (otobüs + metrobüs) ve `IBB_MULTIMODAL` (metro, tramvay, füniküler,
vapur, Marmaray portal verisi; minibüs/taksi/tipsiz hatlar ve turistik vapurlar elenir).

## Okuma ve yükleme
```python
from app.db import SessionLocal
from app.gtfs.feeds import IBB_MULTIMODAL
from app.gtfs.loader import load_feed

with SessionLocal() as oturum:
    ozet = load_feed(oturum, "gtfs_data/multimodal", IBB_MULTIMODAL)   # sayım özeti döner
```
- Okuyucu (`app/gtfs/reader.py`) kodlamayı (UTF-8 / Windows-1254) ve ayracı (`,` / `;`) kendisi algılar;
  bozuk koordinatları ve 24 saati aşan saatleri çözer.
- Zorunlu dosyalar: `routes`, `trips`, `stops`, `stop_times`. İsteğe bağlı: `agency`, `calendar`,
  `calendar_dates`, `frequencies`, `transfers`.
- Yalnızca yüklenen seferlerin kullandığı duraklar (ve üst istasyonları) yüklenir. Geçersiz
  koordinatlı duraklar ve onlara ait saat satırları atlanır; sayıları özette görünür.
- Tüm yükleme tek işlemde yapılır; hata olursa hiçbir şey değişmez.

## Derleme betiği (`scripts/build_gtfs.py`)
Portal bulut sunucularından açılmadığı için **yerel makinede**, proje kök klasöründen çalıştırılır:
```bash
python scripts/build_gtfs.py indir iett ibb                                  # gtfs_data/ altına indir
python scripts/build_gtfs.py yukle iett ibb --hedef sqlite:///gtfs_data/gtfs.db
python scripts/build_gtfs.py rapor iett ibb --hedef sqlite:///gtfs_data/gtfs.db
python scripts/build_gtfs.py hepsi iett ibb --hedef sqlite:///gtfs_data/gtfs.db   # üçü birden
```
- Beslemeler: `iett` (otobüs + metrobüs, `gtfs_data/iett`), `ibb` (çok modlu, `gtfs_data/multimodal`).
- İndirme, portalın CKAN API'siyle (`package_show`) dosya adreslerini bulur; adresler koda yazılı değildir.
  Aynı dosya hem CSV hem ZIP ise **ZIP tercih edilir** ve içinden CSV açılır (İETT `stop_times.csv` kırpılmış).
  Boyutu portalla aynı olan dosyalar atlanır; kesilen indirmeler tekrar denenir.
- **`--hedef` verilmezse** `.env`'deki `DATABASE_URL` (Neon) kullanılır ve **`--evet`** istenir.
  İETT durak saatleri çok büyüktür; önce yerel SQLite dosyasına yükleyip `rapor`daki `Boyut:` satırına bakın.
- Yükleme, besleme başına bir sayım özeti basar: `route`, `route_excluded`, `trip`, `stop`,
  `stop_invalid_coordinates` (koordinatı bozuk), `stop_not_found` (`stops`'ta olmayan), `stop_time`,
  `stop_time_duplicate` (aynı sefer/sıra tekrarı, atlanır), `stop_time_unknown_stop`, `frequency`.
- `stop_times.csv` tam olarak 1.048.575 veri satırıysa (Excel sınırı) dosya kırpılmış sayılır ve yükleme reddedilir.
- `rapor`: mod bazında hat/sefer sayıları, günsüz hizmetler, durak saati olmayan seferler ve (Postgres'te
  tablo bazında, SQLite'ta dosya) boyut.
- **Çıktı biçimi kararı:** ayrı bir `graph.pkl` yerine veritabanı (SQLite dosyası ya da Neon) kullanılır;
  rota motoru (#12) bellek içi yapıları açılışta bu tablolardan kurar.

**Ölçek denemesi** (gerçek İETT `routes/stops/trips` dosyalarının eski sürümü + sentetik `stop_times`):
9261 hat, 135.144 sefer, 15.387 durak, 405.432 durak saati yaklaşık **10 sn** ve **60 MB** SQLite dosyası
(durak saati başına kabaca 100 bayt).

**Boyut tahmini (doğrulanmadı):** Portaldaki `stop_times.csv` kırpılmış olduğundan (bkz.
`docs/veri-kaynaklari.md`) eksiksiz İETT verisi milyonlarca durak saati içerir (~135 bin sefer × onlarca durak).
Yukarıdaki orana göre bu, **yarım gigabayt civarı** bir veritabanı demektir ve **Neon ücretsiz planının
0,5 GB sınırına sığmayabilir**. Gerçek rakam ZIP'ten yüklemeden sonra `rapor`daki `Boyut:` satırıyla
öğrenilecek. Sığmazsa seçenekler (karar #12'de): (a) veriyi uygulamayla birlikte salt-okunur bir SQLite
dosyası olarak tutmak, (b) durak saatlerini hat/sefer başına sıkıştırılmış satırlarda saklamak,
(c) ücretli plan. Rota motoru zaten verileri açılışta belleğe kuracağı için veritabanı yalnızca kaynaktır.

## Planlama kuralları (`app/gtfs/rules.py`)
- `expand_frequency_starts(start, end, headway)`: `[start, end)` penceresindeki sefer başlangıçları.
  Aralık pencereden uzunsa yalnızca pencere başında tek sefer çıkar.
- `expand_frequency_trips(şablon, pencereler)`: şablon seferi kaydırarak gerçek seferleri üretir;
  pencere uçlarında çift sefer olmaz.
- `service_runs_on_weekday(takvim, gün)`: haftanın günü (0=Pazartesi); tarih aralıkları yok sayılır.

## Henüz yapılmayanlar (sonraki issue'lar)
- Gerçek İETT/çok modlu verinin yüklenmesi ve derleme betiği: #7.
- Metro, tramvay, Marmaray, vapur verilerinin tamamlanması: #8, #9, #10.
- Aktarma noktaları ve elle aktarma tablosu: #11.
- `shapes` (güzergah çizgisi) tablosu: #15.

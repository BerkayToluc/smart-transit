# Veri kaynakları ve bulgular (Faz 1)

Aktarmalı rota planlayıcının kullanacağı verilerin kaynakları, durumları ve veriyle ilgili
kurallar. Bu belge **Faz 1 araştırmasının sonucudur**; veri yükleme (#6–#11) buna göre yapılacak.

> Araştırma tarihi: 18 Kasım 2026. Portal sayfalarının içeriği, repo sahibinin kendi bilgisayarından
> aldığı çıktılara dayanır (aşağıda "Erişim notu"). Doğrulanmayanlar ayrıca işaretlidir.

## Erişim notu
- **İBB Açık Veri Portalı (`data.ibb.gov.tr`) bulut sunucularından açılmıyor.** Bağlantı kurulup
  yaklaşık 11 sn sonra karşı taraftan kesiliyor. Bu yüzden indirme ve derleme betikleri
  (`scripts/build_gtfs.py`, #7) **yerel makinede** çalıştırılacak. Testler küçük sahte veriyle çalışır,
  bundan etkilenmez.
- Veri dosyaları `gtfs_data/` altına indirilir (`.gitignore`'da, repoya girmez).

## Kaynak özeti

| Mod | Kaynak | Güncellik | Durum |
|---|---|---|---|
| Otobüs, metrobüs | `iett-gtfs-verisi` | Nisan 2026 | **Ana kaynak.** `stop_times` dahil tam GTFS |
| Metro, tramvay, füniküler, teleferik | `public-transport-gtfs-data` (Metro İstanbul) | **Temmuz 2020** | Eski; M11 ve T5 yok |
| Marmaray | TCDD resmi tarife (bu belgenin sonu) | **5 Mayıs 2026** | Çizelge elle tanımlanacak |
| Vapur, deniz otobüsü | `public-transport-gtfs-data` (Şehir Hatları, İDO, Turyol, Dentur) | **2019** | Eski; turistik seferler filtrelenecek |
| Vapur hat/iskele konumu | `deniz-ulasim-hatlari-vektor-verisi`, `deniz-ulasim-istasyonlari-vektor-verisi` | Kasım 2026 | Konum var, sefer saati yok |
| İETT hat çizgileri | `iett-hat-guzergahlari` (GeoJSON) | Mart 2026 | Mevcut kodda kullanılıyor |

Portaldaki "son güncelleme" tarihi her zaman verinin tarihi değildir. `public-transport-gtfs-data`
kaydı Mart 2025'te güncellenmiş görünse de açıklaması içindeki verilerin 2018–2020 tarihli olduğunu
ve **bir daha güncellenmeyeceğini** söylüyor.

### `iett-gtfs-verisi` (otobüs + metrobüs)
- Dosyalar: `agency`, `calendar`, `routes` (~0,8 MB), `stops` (~1,5 MB), `trips` (~5,8 MB),
  `stop_times` (CSV ~26 MB ve ayrıca **ZIP ~22,7 MB**). `shapes` ve `frequencies` **yok**.
- **`stop_times.csv` portalda KIRPILMIŞ:** yerel çalıştırmada dosya **tam 1.048.575 veri satırı** çıktı
  (Excel'in bir sayfaya sığdırdığı sınır). İETT'nin ~135 bin seferi var; her sefer onlarca durak içerdiğinden
  eksiksiz dosya milyonlarca satırdır, kırpılmış CSV ise yalnızca küçük bir kısmını kapsar. Yükleyici bu
  durumu (tam sınırda satır sayısı) reddeder. **ZIP sürümü tercih edilir** (`scripts/build_gtfs.py indir`
  ZIP'i indirip içinden CSV'yi açar); ZIP'in tam dosya olduğu, boyutundan (sıkıştırma oranından) çıkarılan
  bir tahmindi ve **doğrulandı**: ZIP'ten açılan dosya **6.143.249 durak saati** içeriyor (kırpılmış CSV 1.048.575);
  45 satır aynı (sefer, sıra) çiftini tekrarlıyor (yükleyici bunları atlar).
- Repodaki `routes/stops/trips.csv` bu verinin **eski bir sürümü** (boyutlar daha küçük).
- Bozulma: `;` ayraçlı, isimlerde UTF-8 çift kodlama bozulması (`KADIKÃ–Y`), koordinatlarda
  nokta bozulması (`410.191.700.005.564`). Düzeltme yardımcıları `app/gtfs_admin.py` içinde.
- Hatların hepsi `route_type=3`. Metrobüs ayrı tipte değil, **hat kısa adıyla** ayrılır: repodaki gerçek veride
  `34` ile başlayan tüm hatlar metrobüstür (**34, 34A, 34AS, 34B, 34BZ, 34C, 34G, 34T, 34U, 34Z**) ve bu
  kalıba uyan başka hat yoktur (kural: `^34[A-Z]*$`, `app/gtfs/feeds.py`). Adında "METROBÜS" geçen yüzlerce
  hat ise metrobüse **bağlanan normal otobüslerdir** ve `bus` kalır. Bir hattın yön/varyantları ayrı
  `route_id` satırlarıdır (ör. `34` için 20 satır).
- Gerçek veride görülen kusurlar (hepsi `app/gtfs/` tarafından ele alınır):
  - **Bozuk karakterler iki türlü:** Windows-1252 okuması (`Åž` = Ş) ve Latin-1 okuması (`Å\x9e` = Ş;
    0x9E/0x9F kontrol karakteri olarak kalmış). Düzeltme tablosu ikisini de kapsar; partneri kaybolmuş
    yetim `Å` -> Ş, `Ä` -> Ğ olur. Düzeltmeden sonra routes/stops/trips'te beklenmeyen karakter kalmadı.
  - **Kaymış sütunlu bozuk satırlar:** 18 hat satırında `route_type` boş (5'inde `route_id` de boş);
    bunlar yüklenmez. 3 durak satırının enlem alanında metin (`direction: GİDİŞ`) ve boylamında Excel
    bilimsel gösterimi (`4,12E+14`) var; bilimsel gösterim koordinat sayılmaz, bu duraklar atlanır
    (`stop_invalid_coordinates`).
  - `route_desc`/`route_code` alanlarında hat açıklamaları var (ör. kampüs ring hatları).

### `public-transport-gtfs-data` (çok modlu)
- Dosyalar: `agency`, `calendar`, `frequencies`, `routes`, `shapes`, `stop_times`, `stops`, `trips`.
- Standart GTFS başlıkları, **virgül ayraçlı**.
- **Kodlama UTF-8 değil** (4 dosyada doğrulandı), büyük olasılıkla Windows-1254. İçe aktarıcı önce
  UTF-8, olmazsa `cp1254` denemeli.
- Ajanslar: Şehir Hatları, TCDD, Metro İstanbul, Minibus, Taksi Dolmuş, IDO, Turyol, Dentur Avrasya.
- `route_type` standart değil: 4 (vapur) 100, 1 (metro/Marmaray) 15, 7 (füniküler) 3, 6 (teleferik) 2,
  0 (tramvay) 3, **9 (minibüs) 317, 10 (taksi dolmuş) 58**, boş 1. **Hat tipine güvenilmeyecek;**
  mod, `agency` ve hat koduyla eşlenecek.
- Veri tarihleri (kaynağın kendi açıklamasından): Minibüs 02.2018, Taksi Dolmuş 01.2018,
  Şehir Hatları 09.2019, Metro İstanbul 07.2020, TCDD 10.2019, İDO 10.2019, Turyol 10.2019,
  Dentur 10.2019.

#### Takvim (`calendar.csv`) kuralları
- Hizmetlerin çoğu **31.12.2024'te** bitiyor. Bugünün tarihiyle filtrelenirse hiçbir sefer kalmaz.
  **Tarih aralığı yok sayılacak**, yalnızca haftanın günleri kullanılacak.
- Hiçbir günü işaretli olmayan hizmetler (ör. `308`, `309`; 2019 Ramazan gece seferleri) **atlanacak**.

#### Aralıklı seferler (`frequencies.csv`)
- Sütunlar: `trip_id, start_time, end_time, headway_secs, exact_times` (`exact_times=0`: saatler yaklaşık).
- Aralıklı seferler yolculuk planlamasından önce **gerçek seferlere açılacak** (`pencere ÷ aralık`,
  yukarı yuvarlanır). Aralık pencereye eşit/büyükse (ör. 08:30–19:00 için 37800 sn) pencere başında
  tek sefer demektir.

#### Hatlar (sefer sayıları)
| Grup | Hatlar | Sefer |
|---|---|---|
| Tam tarifeli | M1A, M1B, M2, M2A, M3, M3A, M4, M5, M6, T1, T3, T4, F1 | 219 – 1368 |
| Yalnızca aralıklı | M8, M9, F3, TF1, TF2, F2 | 2 – 6 |
| Az sefer | M7 | 20 |
| Marmaray (portal verisi) | `Marmaray`, `Marmaray1`, `Marmaray2` | 2 – 4 (**kullanılmayacak**, aşağıya bakın) |

- **Eksik hatlar:** M11, T5 (ve M5'in sonraki uzatmaları). Kaynak adayları:
  `metro-istanbul-sefer-tarifeleri-listesi-web-servisi` (REST `.../MetroMobile/V2/GetTimeTable`, kayıt
  tarihi 2022, güncelliği doğrulanmadı), `metro-istanbul-istasyon-bilgi-listesi` (Şubat 2026),
  T5 için KMZ/XLSX (sefer saati yok). M11 (Gayrettepe–Halkalı) TCDD sitesinde ayrı bir sayfa olarak
  görünüyor; Marmaray ile **ilgisiz**, #8'de ele alınacak.

#### Vapur
- 100 hat tipi 4, gördüğümüz hepsi Şehir Hatları. İDO/Turyol/Dentur hatları çıktı kesildiği için
  doğrulanmadı.
- **Turistik/özel seferler planlamadan çıkarılacak** (ad filtresi): "BOĞAZA GİDİŞ", "BOĞAZDAN GELİŞ",
  "... TURU", "LALE FESTİVALİ" vb.
- Seferlerin 2019 tarifesi bugünkü mevsimlik tarifeyle uyuşmayabilir; sabit aralıklı elle tanım
  gerekebilir (#10).

#### Minibüs / dolmuş
375 hat, standart olmayan tiplerle (9, 10). İlk aşamada **dışarıda** bırakılacak.

### Diğer kurallar
- **Farklı beslemelerde `stop_id` çakışabilir.** Birleştirirken kaynak öneki kullanılacak
  (`iett:`, `ibb:`, `marmaray:` ...).
- `stops.csv` içinde `parent_station` ve `wheelchair_boarding`, `trips.csv` içinde
  `wheelchair_accessible` sütunları var; dolu olup olmadıkları doğrulanmadı (#11, #25).

## Marmaray: resmi tarife (TCDD, 5 Mayıs 2026)

Kaynak: TCDD Taşımacılık "Marmaray Günlük Tren Saatleri" sayfası; görüntü
[`docs/kaynaklar/tcdd-marmaray-tarife-2026-05-05.webp`](kaynaklar/tcdd-marmaray-tarife-2026-05-05.webp).
Portaldaki 2019 TCDD verisi (`Marmaray`, `Marmaray1`, `Marmaray2`) bugünkü hizmetle uyuşmuyor
(ör. "Halkalı–Bahçeşehir" ve "Söğütlüçeşme–Zeytinburnu" kalıpları yok, Ataköy–Pendik kalıbı yok),
bu yüzden **çizelge elle tanımlanacak**; istasyon listesi, koordinatlar ve istasyonlar arası süreler
portal verisinden alınabilir (43 istasyon, Halkalı→Gebze 111,5 dk).

### Kalıp 1: Halkalı ↔ Gebze (43 istasyon)
| | Halkalı → Gebze | Gebze → Halkalı |
|---|---|---|
| İlk tren | 05:58 | 06:05 |
| Son tren (normal) | 23:28 | 23:20 |
| Son tren (Cuma→Cmt ve Cmt→Paz geceleri) | 01:28 | 01:20 |

- Sıklık **15 dakika**. Zamanlar 15 dakikalık ızgaraya tam oturuyor: Halkalı'dan 05:58 ... 22:58,
  Gebze'den 06:05 ... 22:50'ye kadar 15 dakikada bir; ardından 30 dakika sonra son tren (23:28 / 23:20).
- Cuma→Cumartesi ve Cumartesi→Pazar geceleri 22:50'den sonra **30 dakika** aralıkla 01:28 / 01:20'ye kadar
  (tablodaki "haftasonu son tren" sütunu ve alt not).

### Kalıp 2: Ataköy ↔ Pendik (25 istasyon)
| | Ataköy → Pendik | Pendik → Ataköy |
|---|---|---|
| İlk tren | 06:09 | 06:09 |
| Son tren | 21:54 | 20:39 |

- Sıklık **8 dakika**.
- **Pendik'ten 20:50'den sonra kalkan trenler Zeytinburnu'na kadar** gider; Pendik'ten son tren 22:39
  (Zeytinburnu'na 23:33). Bu akşam kalıbının sıklığı tabloda yok; 8 dk varsayılıp işaretlenecek.
- Resmi tabloda **yoğun saatte 5–6 dk** yazmıyor (bazı üçüncü taraf sitelerde yazıyordu); düz 8 dk kullanılacak.

### Bilinen sınırlama
Tabloda her istasyon için ayrı "ilk tren" saati var ve bazı seferler hat ortasından çıkıyor
(ör. Kartal 06:00, Küçükyalı 06:00). İlk aşamada bu **yok sayılıp** her kalıp terminalinden
başlatılacak; sabah ilk saatlerde ortadan binenler için birkaç dakikalık fark olabilir.

### Aktarma (#11'e girdi)
Marmaray istasyonları ile diğer hat durakları farklı kurumların verisinde, ortak kimlik yok.
Yürüme süresi kuş uçuşu mesafeyle tutmaz (Yenikapı, Üsküdar gibi derin istasyonlar). Otomatik
≤150 m kuralı yerine, Marmaray için **elle tutulan küçük bir aktarma tablosu** kullanılacak
(istasyon çifti + dakika). Her Marmaray istasyonu için yakın durak adayları koordinatla
listelenip onaylanacak.

## Karara bağlanmış / ertelenmiş konular
- Marmaray için **ayrı mod/rozet**: şimdilik **yok** (normal raylı hat gibi davranır), sonra bakılacak.
- Arayüzde **veri tarihi gösterimi**: şimdilik **yok**, sonra bakılacak.
- Metro/vapur verisinin tazelenmesi (canlı Metro İstanbul API, 2026 GeoJSON'lar): temel akış
  çalıştıktan sonra.

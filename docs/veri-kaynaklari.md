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
| Vapur, deniz otobüsü | `public-transport-gtfs-data` (Şehir Hatları, İDO, Turyol, Dentur) | **2019** | Güvenilmez; **yüklenmez**. Yerine Şehir Hatları 2026-27 kış tarifesi (`data/vapur.json`) |
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

- **Eksik hatlar:** M11, T5, M5'in sonraki uzatmaları (Sultanbeyli) ve sonradan açılan diğer uzatmalar.
  Kaynak adayları: `metro-istanbul-sefer-tarifeleri-listesi-web-servisi` (REST `.../MetroMobile/V2/GetTimeTable`,
  güncelliği doğrulanmadı), `metro-istanbul-istasyon-bilgi-listesi` (Şubat 2026), T5 için KMZ/XLSX (sefer saati yok),
  M11 için TCDD sitesindeki "Gayrettepe-Halkalı" tarife sayfası. Marmaray'da olduğu gibi **kurallarla elle tanımlama**
  da bir seçenektir (`app/gtfs/manual.py`). Takip: ayrı issue.


#### Doğrulama (#8): gerçek yükleme çıktısı (19 Kasım 2026)
Beslemenin yerelde yüklenmesi (`hepsi ibb`) ve `hatlar` raporu sonucu: 92 hat, 13.232 sefer, 272 durak,
168.812 durak saati, 245 aralıklı tanım, 49 hizmet. Elenen 407 hat: minibüs, taksi dolmuş, tipsiz, turistik vapur
ve eski TCDD hatları. İsim kontrolünde bozuk karakter şüphesi yok.

| Hat | Güzergah | Durak | Süre (veride) |
|---|---|---|---|
| M1A | Yenikapı → Atatürk Havalimanı | 18 | 32,5 dk |
| M1B | Yenikapı → Kirazlı | 13 | 22,1 dk |
| M2 | Yenikapı → Hacıosman | 15 | 29,1 dk |
| M3 | Kirazlı → Başakşehir-Metrokent | 9 | 17,2 dk |
| M4 | Kadıköy → Tavşantepe | 19 | 38,1 dk |
| M5 | Üsküdar → Çekmeköy | 16 | 26,6 dk |
| M7 | Yıldız → Mahmutbey | 17 | 26,7 dk |
| M8 | Bostancı → Parseller | 13 | 21,8 dk |
| T1 | Bağcılar → Kabataş | 31 | 68,1 dk |
| T4 | Topkapı → Mescid-i Selam | 22 | 52,8 dk |
| F1 / F2 | Taksim–Kabataş / Karaköy–Beyoğlu | 2 | 2,0 / 1,6 dk |
| TF1 / TF2 | Maçka–Taşkışla / Eyüp–Piyerloti | 2 | 3,2 / 2,5 dk |

Durak sayıları ve süreler bilinen hat bilgileriyle uyumlu görünüyor (resmi kaynakla satır satır karşılaştırılmadı).
**Önemli bulgu:** Metro İstanbul bölümü, portal açıklamasındaki "Temmuz 2020" tarihinden **daha yeni**: **M8**
(Bostancı–Parseller, Ocak 2023'te açıldı) verisi içeriyor ve takvimi 31.12.2022'den başlıyor; yani büyük olasılıkla
Aralık 2022 – Ocak 2023 tarihli. M11 (TCDD işletiyor) ve T5 yok.
Uyarılar: 5 hizmetin günü işaretli değil (2019 Ramazan gece seferleri vb., planlamada çalışmaz); 7 seferin durak saati
yok (`rapor` artık hangi hatlar olduğunu gösterir).

#### Vapur
- 100 hat tipi 4, gördüğümüz hepsi Şehir Hatları. İDO/Turyol/Dentur hatları çıktı kesildiği için
  doğrulanmadı.
- **Turistik/özel seferler planlamadan çıkarılacak** (ad filtresi): "BOĞAZA GİDİŞ", "BOĞAZDAN GELİŞ",
  "... TURU", "LALE FESTİVALİ" vb.
- Seferlerin 2019 tarifesi bugünkü mevsimlik tarifeyle uyuşmayabilir; sabit aralıklı elle tanım
  gerekebilir (#10).
- **Gerçek yükleme gözlemleri (19 Kasım 2026, #8 çıktısı):** turistik hatlar elendikten sonra **72 vapur hattı** kaldı
  (Şehir Hatları "ŞH.", İDO, Turyol, Dentur, Feribot). Aynı güzergâh birden çok işletmeciyle ve varyantla yinelenir
  (ör. Kadıköy–Eminönü: ŞH, Turyol, `EMN_KDK`, `EMN_KDK2`; Üsküdar–Eminönü). Hatların çoğu 2 seferlik, bir kısmı
  yüzlerce seferli (Turyol/ŞH ana hatlar). **Şüpheli süreler (doğrulanmalı):** `KDK-EMN` (Yeni Kadıköy → Eminönü Camlı
  İskele) 13,4 dk görünüyor (Turyol aynı hat 25,9 dk); `USK_K.KOY_EMN` 3 durakta 119,8 dk; `AVC-ADA`, `ADA-EMN` gibi
  adalar hatları 100-120 dk. Yani vapur verisi metro/tramvay kadar güvenilir değil. **Karar (#10): 2019 vapur
  verisi hiç yüklenmez** (`ibb` beslemesinde `exclude_modes` içinde `ferry`; Turyol/Dentur/İDO da dahil);
  vapur, Şehir Hatları'nın resmi kış tarifesinden elle tanımlanır (aşağıda "Vapur: resmi tarife").

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

### Uygulama (#9)
- Çizelge **elle tanımlı**: kurallar `data/marmaray.json` dosyasındadır ("Halkalı → Gebze, 05:58'den 22:58'e
  her 15 dakikada bir" gibi). `app/gtfs/manual.py` bunları GTFS dosyalarına çevirir, aynı yükleyici
  (`scripts/build_gtfs.py yukle marmaray`) veritabanına alır. İndirme gerekmez.
- **Kalıplar:** Halkalı→Gebze, Gebze→Halkalı (43 istasyon), Ataköy→Pendik, Pendik→Ataköy (25 istasyon),
  Pendik→Zeytinburnu (22 istasyon, akşam). Hizmetler: `her_gun` ve `cuma_cumartesi_gecesi` (gece yarısından
  sonraki seferler, ör. 25:28 = ertesi gün 01:28).
- **İstasyon konumları ve süreleri** 2019 TCDD GTFS'inden alındı (Halkalı→Gebze 111,5 dk). **Doğrulama:** üretilen
  istasyon süreleri, TCDD'nin 2026 tarifesindeki her istasyon saatiyle karşılaştırıldı (4 kalıp, 58 istasyon saati):
  ortalama fark 1 dakikadan az, en kötü fark ~3 dakika (resmi saatler dakikaya yuvarlanmış). Test olarak kayıtlıdır.
- **Ters yönde** aynı süreler kullanılır (simetrik varsayım).
- **Son sefer sorunu:** gerçek tarifeler aralık ızgarasına oturmaz (ör. 06:09'dan her 8 dk, son tren 21:54; ızgara
  21:53'e denk gelir). İlk ve son sefer **tam** korunur; ızgaranın son noktası son seferden `aralık/2`'den yakınsa
  son seferle değiştirilir (art arda iki tren çıkmasın), uzaksa son sefer ayrıca eklenir.
- **Varsayımlar (doğrulanmadı):** Pendik→Zeytinburnu akşam kalıbının sıklığı tabloda yok, 8 dk alındı ve
  `20:50` ilk sefer sayıldı ("20:50'den sonra kalkan trenler"); `exact_times=0` (saatler yaklaşık).
- **Portaldaki 2019 TCDD hatları (`ibb` beslemesinde agency 4) artık YÜKLENMEZ** (`exclude_agencies`), yeni
  tanımla çakışmasınlar.
- **Güncelleme:** TCDD tarifeyi değiştirirse `data/marmaray.json` içindeki `ilk`/`son`/`aralik_dk` değerleri ve
  `besleme.veri_tarihi` güncellenir; `python scripts/build_gtfs.py yukle marmaray` yeniden çalıştırılır.

## Vapur: resmi tarife (Şehir Hatları 2026-2027 Kış Tarifesi, 7 Eylül 2026 - 27 Haziran 2027)

Neden elle tanımlı: vapurun güncel, makinece okunabilir (GTFS/API) tarifesi yok; resmi kaynak, kurumun
kitapçığıdır ve **her iskelenin her kalkış saatini tek tek** verir. Marmaray'daki gibi "her X dakikada bir"
kuralı yazmak yerine saatler olduğu gibi `data/vapur.json`'da tutulur (düzensiz seferler tarifedeki gibi kalır).
Moovit/Google de vapur saatlerini işletmecinin tarifesinden alır; İBB'nin 2019 GTFS'i bugünkü tarifeyle uyuşmaz.

### Kitapçığın okunuşu
- Sütunlar **iskele bazlıdır** ve satırlar sefer değildir (ör. Kadıköy 07:00, Karaköy 07:20, Eminönü 07:30 aynı
  satırda ama bağımsız listelerdir). Sefer zincirleri saatlerin eşleştirilmesiyle çıkarılmıştır: bir iskelenin
  kalkışı, bir önceki iskelenin kalkışından 15-30 dk (hat ve dilime göre) sonraya denk gelir. **Doğrulama:**
  eşleştirme `*`/`**` dipnotlarıyla çelişmedi (aynı zincirdeki tüm duraklar aynı dipnotu taşıyor), Üsküdar–Eminönü'nde
  Üsküdar'ın 46 ve Eminönü'nün 46 saati hiç artık kalmadan eşleşti, Kadıköy–Karaköy–Eminönü'nde tüm 53/53/42 saat
  eşleşti; Karaköy 20:55 (`***` "yolcu almaz") Kadıköy 20:30 → Karaköy 20:55 → Eminönü 21:05 zincirinin ortasıdır.
- **Dipnotlar → hizmet:** işaretsiz = her gün; `*` = Cumartesi/Pazar/tatil yapılmaz → `hafta_ici` (Pzt-Cum);
  `**` = Pazar/tatil yapılmaz → `pzt_cmt`. Gün sütunlu sayfalar (Kabataş): `hafta_ici`, `cumartesi`, `pazar_tatil`;
  Ortaköy hatları: `hafta_ici` ve `hafta_sonu`. Gece seferleri: Cuma ve Cumartesi geceleri (`gece`, 24:00 sonrası
  saatler 24-29 olarak yazılır).
- Kadıköy (Eski) ve (Yeni) iskeleleri tek durak (`kadikoy`) olarak alındı (yaklaşık 150 m; ayrı durak gerekirse #11).
- **Resmî tatiller:** takvim yalnız hafta günü bilir; tatil gününe denk gelen hafta içi günü hafta içi tarifesiyle
  çalışır (tatil tarifesi için `calendar_dates` desteği ileri bir iş).

### Adalar ve Bostancı hatları (sayfa 12-18)
Bu sayfalarda tablolar **satır = sefer** biçimindedir (başlık sütunları: iskeleler, "-" = o iskeleye uğramaz), yani
eşleştirme gerekmez; süreler kitapçıktaki saatlerin kendisidir. Hatlar: Kabataş–Adalar (Eminönü/Kadıköy/Kınalıada/
Burgazada/Heybeliada/Büyükada/Bostancı), Adalar–Beşiktaş, Maltepe–Adalar (`*` = Pazar/tatil yapılmaz → `pzt_cmt`),
Bostancı–Adalar ring (Bostancı iki kez geçer), Bostancı–Moda–Karaköy–Kabataş ve Büyükada–Sedef Adası.
Parantezli saatler (Bostancı–Kabataş hattı) durak sırasının tersine denk gelir (ör. Kabataş (19:20) sonra Karaköy
(19:35)); duraklar saate göre sıralanır. 24:00'ı aşan seferler 24-26 olarak yazılır. Sayfa 12-13'te gece tarifesi
notu: 00:30-05:30 arası iki kat ücret (planlayıcıda ücret hesabı #26).

### Varsayımlar (kitapçıkta yok, doğrulanmadı)
- **Yolculuk süreleri:** Kitapçıkta kalkış saati var, süre yok. Eşleşen zincirlerde süreler saatlerin kendisinden
  gelir (Kadıköy→Karaköy 20-30, Karaköy→Eminönü ~10 dk). Eşleşmeyen dönüş seferlerinde varsayım: Eminönü→Kadıköy 25,
  Üsküdar→Eminönü 20 (Eminönü→Üsküdar 20), Karaköy→Kadıköy 25, Karaköy→Üsküdar 15, Kadıköy↔Beşiktaş 25,
  Kadıköy↔Kabataş 25, gece Beşiktaş→Kadıköy 30.
- **Dönüş zinciri:** Kadıköy–Karaköy–Eminönü ve Üsküdar–Karaköy–Eminönü'nde Eminönü kalkışları, geldiği yerin
  tersine (Kadıköy / Üsküdar) dönüş seferi sayıldı; Karaköy'de Eminönü'ne devam etmeyen kalkışlar Kadıköy'e mekik
  sayıldı (akşam 21:00'dan sonra Kadıköy↔Karaköy 30 dk'lık iki yönlü mekik gibi görünüyor).
- **İskele konumları:** kullanıcının sağladığı Şehir Hatları iskeleleri KML dosyasından (56 iskele; ilk tahminler 100-350 m
  sapıyordu). Kadıköy için iki iskelenin (KADIKÖY-1/-2) ortası, Eminönü için EMİNÖNÜ-3 alındı. Kalan iskeleler sonraki
  hatlarda kullanılacak.

### Boğaz, Haliç ve diğer hatlar (sayfa 20-37)
- **Satır = sefer** olan hatlar: Rumeli Kavağı–Eminönü, Ortaköy–Beşiktaş–Eminönü (kırmızı `*` = yalnız Cumartesi/Pazar/tatil),
  Anadolu Kavağı–Rumeli Kavağı–Sarıyer (`*` Pazar/tatil yok, `**` yalnız Pazar/tatil), Anadolu Kavağı–Üsküdar,
  Üsküdar–Haliç, Beşiktaş–Haliç, Kadıköy–Haliç, Çengelköy–Kuzguncuk–Beşiktaş–Kabataş, Bebek–Emirgan (yalnız Pazar/tatil),
  Çengelköy–İstinye ring ve Aşiyan–Anadolu Hisarı–Küçüksu ring (`(V)` = sefer Anadolu Hisarı'nda biter).
  Haliç hatlarında `*` → `pzt_cmt`, `**` → `pazar_tatil`; Çengelköy–İstinye ringinde `*` Cumartesi yapılmaz → `hafta_ici`.
- **Boğaz Hattı (s.20-21):** iki sayfaya yayılan tek matris. Satır = sefer; sol yarı sayfa 20, sağ yarı sayfa 21'dedir
  (aynı satır sırası). Gün tipi satır arka plan renginden okundu (turuncu/beyaz = hafta içi, gri = Cumartesi, kırmızı = Pazar
  ve tatil; piksel ölçümüyle doğrulandı). Boğaza gidiş: 12 hafta içi + 2 Cumartesi + 1 Pazar; Boğazdan geliş: 12 + 3 + 1.
  Duraklar saate göre sıralanır; `(K)` kalkış, `(V)` varış.
- **Bağımsız kalkış listeleri (satırlar eşleşmiyor):** Küçüksu–İstinye, Üsküdar–Aşiyan, İstinye–Çubuklu (araba vapuru
  iskeleleri, `*_arabali` kayıtları). Her iskelenin kalkışları ayrı sefer sayıldı; **süreler varsayım:** Küçüksu–İstinye
  20, Üsküdar–Aşiyan 30, İstinye–Çubuklu 15 dk. Küçüksu–Beşiktaş–Kabataş'ın dört seferi elle eşleştirildi (08:35 Küçüksu seferinin
  Beşiktaş 09:00 / Kabataş 09:05 varışları varsayım).
- **Kapsam dışı:** Uzun/Kısa Boğaz Turu (sayfa 35, turistik; planlamaya girmez) ve Tuzla–Pendik–Büyükada (İDO iskeleleri,
  doğrulanmış koordinat yok; ayrı iş). Turyol/Dentur/İDO kitapçıkta yok ve kapsam dışı.

### Kapsam
Kitapçığın tüm düzenli hatları: Kadıköy/Üsküdar/Karaköy/Eminönü/Beşiktaş/Kabataş/Ortaköy (s.4-9), Adalar ve Bostancı
(s.12-18), Boğaz (s.20-28), Haliç ve diğerleri (s.29-34, 37). Toplam **1148 sefer, 29 hat**.

### Uygulama (#10)
`app/gtfs/vapur.py` dosyayı doğrular ve GTFS'e çevirir (`route_type=4`, her sefer ayrı GTFS seferi, frekans yok,
`binis_yok` → `pickup_type=1`). Yeni besleme adı `vapur`:

```
python scripts/build_gtfs.py hepsi vapur --hedef sqlite:///gtfs_data/gtfs.db
python scripts/build_gtfs.py saatler vapur --hedef sqlite:///gtfs_data/gtfs.db
```

Güncelleme: kurum yeni tarife yayımlarsa `data/vapur.json` ve `besleme.veri_tarihi` güncellenir.

## Aktarma noktaları (#11)

`python scripts/build_gtfs.py aktarma --hedef sqlite:///gtfs_data/gtfs.db` (`app/gtfs/transfers.py`) yüklü tüm
beslemelerin duraklarından:
- **Yürüme kenarları** (`gtfs_transfer`, `source=auto`, `transfer_type=2`): ≤150 m çiftler (tüm durak türleri) ve
  **farklı beslemelerin istasyon türü durakları için ≤600 m**. Süre = mesafe × 1.3 / 4.8 km/s (yukarı yuvarlanır).
  Geniş yarıçap **gerçek veri ölçümünden** geldi: Marmaray Üsküdar ↔ iskele 236 m, Bostancı 262 m, Sirkeci ↔ Eminönü
  542 m, Maltepe 504 m; yalnız 150 m kuralı bu aktarmaları kaçırırdı. Aynı beslemede yalnız **ortak hattı olmayan**
  istasyonlar bağlanır (M2 Taksim ↔ F1 Taksim); aynı hattın ardışık durakları ve otobüs durakları geniş yarıçapa girmez.
- **İstasyon kümeleri:** metro, tramvay, füniküler, teleferik, Marmaray, metrobüs ve vapur durakları ≤120 m ise tek
  üst istasyon altında toplanır (`gtfs_stop`, `location_type=1`, besleme `kume`, kimlik `kume:ad-xxxxxx`; üyelerin
  `parent_station` alanı dolar). Küme çapı ≤300 m (zincirleme birleşme yok). Otobüs durakları kümelenmez.
- **Aynı isim hiçbir zaman birleştirme nedeni değildir** (yalnız mesafe); isim yalnız küme etiketi seçer.
- **Küme içi aktarma** en az 120 sn; bilinen büyük noktalar için süreler `data/aktarma.json`'dan (**varsayım**,
  doğrulanmadı): Yenikapı 8, Mecidiyeköy 8, Ayrılık Çeşmesi 6, Üsküdar/Kadıköy/Taksim/Sirkeci/Zincirlikuyu 5,
  Karaköy/Kabataş 4 dk.
- **Yeniden üretim:** her çalışmada önceki otomatik kayıtlar silinip yeniden hesaplanır (idempotent). Bir besleme
  yeniden yüklenirse (`_beslemeyi_sil` o beslemenin duraklarına bağlı otomatik kenarları da siler) `aktarma`
  komutu yeniden çalıştırılmalıdır.
- **Rapor:** komut kenar/küme sayısını, besleme çiftlerine göre kenarları ve `data/aktarma.json`'daki 10 büyük
  noktayı (Yenikapı, Üsküdar, Kadıköy, Mecidiyeköy, Zincirlikuyu, Taksim, Sirkeci-Eminönü, Karaköy, Kabataş, Ayrılık
  Çeşmesi) için bulunan durakları/modları ve kaç bağlı gruba bölündüklerini basar (`OK` = beklenen tüm modlar var ve
  tek grup).

## Karara bağlanmış / ertelenmiş konular
- Marmaray için **ayrı mod/rozet**: şimdilik **yok** (normal raylı hat gibi davranır), sonra bakılacak.
- Arayüzde **veri tarihi gösterimi**: şimdilik **yok**, sonra bakılacak.
- Metro/vapur verisinin tazelenmesi (canlı Metro İstanbul API, 2026 GeoJSON'lar): temel akış
  çalıştıktan sonra.

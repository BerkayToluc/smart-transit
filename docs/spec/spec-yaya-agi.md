# Spec: planlayıcı gerçek yaya yol ağını kullansın (OpenStreetMap)

> Issue gövdesi olarak hazırlandı; GitHub erişimi geçici kesildiği için önce buraya yazıldı.

## Amaç
Planlayıcı yürüyüş mesafe ve sürelerini bugün **kuş uçuşu × 1,3 ÷ 4,8 km/s** tahminiyle hesaplıyor. Haritadaki yürüyüş çizgisi artık Google yürüyüş rotasıyla sokaklara oturuyor (#86), ama bu yalnızca gösterim: gerçek yürüyüş 4 dk çıksa da planlayıcı 3 dk sayıyor, bu yüzden bir aktarma ya da otobüs kaçabilir ve **hangi duraktan binileceği** (yakın durak seçimi) yanlış kuş uçuşu mesafeye göre yapılır.

Hedef: yürüyüşleri (başlangıç→durak, durak→varış, aktarma) **gerçek yaya yol ağı** üzerinden hesaplamak.

## Maliyet
**Ücretli bir servis gerekmiyor.**
- Veri: OpenStreetMap (ODbL lisansı, ücretsiz; arayüzde "© OpenStreetMap contributors" atfı gerekir). İstanbul/Türkiye çıkarımı Geofabrik'ten ücretsiz indirilir.
- Yazılım: açık kaynak (Valhalla / OSRM / GraphHopper ya da Python'da `pyrosm`/`osmnx` ile kendi yaya grafı).
- Tek gerçek maliyet: yayında barındırma (bellek/işlemci). Seçenek A (aşağıda) ek sunucu istemez; Seçenek B küçük bir ek servis çalıştırır.
- Google Directions/Distance Matrix'e planlayıcı çağrılarında **bağımlı olmayacağız** (kota ve ücret riski yok).

## Seçenekler
**A) Kendi yaya grafımız (öneri):** OSM'den yaya yollarını (kaldırım, yaya yolu, merdiven, alt/üst geçit, yürünebilir yollar) çıkarıp RAPTOR grafı gibi bir kez derleyen (`gtfs_data/yaya.pkl`) bellek içi yaya ağı. Durakları ağa tutturup (snap) en kısa yolu Dijkstra/A* ile bulur. Ek servis yok, yerelde derlenir (İBB gibi bulut engeli olan kaynak yok; Geofabrik erişilebilir olmalı, değilse yerelde indirilir).
**B) Valhalla ya da OSRM sunucusu:** Hazır yaya yönlendirme, matris API'si hızlı; ayrı süreç/Docker (#31 ile birlikte düşünülür), ~1-2 GB bellek.

## Yapılacaklar
- [ ] Veri: İstanbul OSM çıkarımı (yaya ağı) ve derleme betiği (`scripts/yaya_agi.py`), doğrulama (bağlantılı bileşen sayısı, durakların ağa uzaklığı raporu)
- [ ] Duraktan ağa tutturma (snap) ve en kısa yol (A*); merdiven/eğim cezası, ana yol geçişleri için hız varsayımı (4,8 km/s tabanı korunur)
- [ ] Planlayıcıya entegrasyon: `yakin_duraklar` (erişim/çıkış) ve aktarma kenarları (`transfers`) kuş uçuşu yerine yaya yol mesafesiyle; `max_walk_m` yol mesafesi üzerinden
- [ ] `/api/plan` yürüyüş etaplarına gerçek yol geometrisi (`polyline`) ve `distance_m`; ön yüzde Google yürüyüş rotasına bağımlılık kalkar (#86'daki çağrılar yedek ya da kaldırılır)
- [ ] OSM atfı arayüzde; `docs/veri-kaynaklari.md` ve `docs/schema.md` güncellemesi
- [ ] Testler: sentetik küçük ağda en kısa yol; durak tutturma; plan sonucunda yürüyüş süresinin yol mesafesinden gelmesi; `/karsilastir` ile Google farkının (özellikle yürüyüşün uzun olduğu çiftler) küçülmesi

## Kabul kriterleri
- Planlayıcının yürüyüş süresi, Google yürüyüş rotasıyla ±%20 içinde (örnek 20 çift)
- Çizgi binaların içinden geçmez; sunucuya Google çağrısı gitmez
- Plan sorgu süresi önemli artmaz (hedef: +%20)

## Bağımlılık / notlar
#86 (gösterim tarafı), #31 (Docker; Seçenek B için). Spec gerekirse `docs/spec/` altında yazılır.


# Arayüz (Faz 3)

`frontend/` Next.js 16 + React 19 + Tailwind 4. Tek sayfa, tek harita: **Rota planla** (`components/rota/`). Eski "Hat takibi"
ekranı kaldırıldı; canlı otobüs özelliği rota planlamanın içine ("Otobüsleri gör") taşındı.

## Çalıştırma
```
uvicorn main:app --reload --port 8000        # kök klasörde; rota grafı için gtfs_data/graf.pkl (build_gtfs.py rota ile üretilir)
cd frontend && npm run dev                   # http://localhost:3000
```
İki veritabanı: canlı otobüs takibi (eski hat/durak tabloları) `.env` içindeki `DATABASE_URL`'e (Neon) bakar; rota planlayıcının GTFS verisi
ise `GTFS_DATABASE_URL=sqlite:///gtfs_data/gtfs.db` ile ayrı bir yerden okunur (tam veri Neon'a sığmaz). Birini diğeriyle
DEĞİŞTİRMEYİN.

`frontend/.env.local`: `NEXT_PUBLIC_API_URL` (varsayılan http://localhost:8000) ve `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`.
Google anahtarı geçersizse/Places kapalıysa yer arama kutuları düz girişe düşer (enlem,boylam yazılabilir) ve harita
yerine açıklayıcı bir mesaj görünür; rota listesi çalışmaya devam eder.

## Tasarım
- **Akılda kalan öğe: zaman şeridi.** Her seçenek, süresine orantılı renkli bir şerit (yürüme noktalı, hatlar kendi
  renginde); çubuğun toplam uzunluğu en uzun seçeneğe göredir. Detayda tren içindeki istasyon şeritleri gibi dikey hat şeması.
- **Renkler** (`app/globals.css`): Sis (zemin), Mürekkep (metin), Boğaz (vurgu), İskele (`#F59F0F`, Şehir Hatları
  tarife kitapçığından ölçülen turuncu; yalnız "şimdi/seçili"). Gündüz teması "Sis", gece teması "Liman".

  **Tema seçimi (#59):** başlıktaki açık / sistem / koyu seçici (`TemaSecici`, radyo grubu, ok tuşlarıyla gezilir). Seçim
  `localStorage` (`smarttransit-tema`) ve `<html data-theme="light|dark">` ile tutulur; "sistem"de öznitelik yoktur ve CSS
  `prefers-color-scheme`'i izler. `app/layout.tsx` içindeki satır içi betik öznitelik sayfa boyanmadan önce koyar (parlama
  olmaz), depolama erişilemezse sistem teması kalır. `lib/tema.ts` (`useTema`) seçimi, gerçekten uygulanan temayı ve
  `theme-color` meta etiketlerini yönetir. Harita stilleri `lib/haritaStili.ts` (`GUNDUZ_STILI` / `GECE_STILI`), temaya göre
  değişir. Rozet yazıları `--mod-*-on` belirteçleriyle her temada AA kontrastlıdır (metin çiftleri ≥4,5:1).
- **Yazı:** Bricolage Grotesque (başlık, süreler, marka) + Instrument Sans (arayüz), `latin-ext` ile Türkçe karakterler.
- Metro/tramvay hat renkleri yaklaşık işletme renkleridir (`lib/modes.ts`); eşleşmeyen hatlar mod rengini alır.
- Masaüstünde 26 rem sol panel, telefonda üç duruşlu sürüklenebilir alt çekmece (`Cekmece.tsx`).
- Erişilebilirlik: görünür klavye odağı, `radiogroup`/`aria-pressed`/`aria-expanded`, `aria-live` sonuç alanı,
  azaltılmış hareket desteği.

## Dosyalar
`lib/plan.ts` (API istemcisi, Türkçe hata çevirisi), `lib/modes.ts` (mod/hat renkleri), `lib/google.ts` (tek harita
yükleyici), `components/rota/*` (RotaPlanla, YerAlani, Kontroller, SecenekListesi, AdimAdim, RotaHaritasi, Cekmece).

## Harita çizimi
- Çizgiler ve işaretçiler `components/rota/RotaHaritasi.tsx` içinde **doğrudan Google Maps API'siyle** oluşturulur ve her
  değişiklikte (seçim, giriş, tema) temizlenir; yalnızca seçili seçeneğin rotası görünür.
- **Otobüs/metrobüs bacakları için önce resmî güzergâh çizgisi:** backend `geometry: "resmi"` döndürürse (İETT GeoJSON'u,
  `python scripts/build_gtfs.py guzergah`) çizgi olduğu gibi çizilir. Yoksa:
- **Otobüs ve metrobüs bacakları yollara oturtulur (yedek):** durak sırası boyunca Google Directions (araç yolu). Uzun bacak (özellikle
  seyrek duraklı metrobüs) 8'er aralıklı parçalara bölünür; çok sapan ya da başarısız parça düz çizgi kalır, diğerleri yolu
  izler; sonuçlar bellekte önbelleklenir. Metro, tramvay,
  Marmaray ve vapur durak sırasıyla çizilir (ray/deniz yolunu yaklaşık izler).
- **Metro, tramvay, Marmaray ve füniküler** bacakları ray hattına oturtulur: Google toplu taşıma güzergâhının adım çizgileri
  (`TRANSIT`, uygun modlar) kullanılır; uçlar istasyondan 500 m'den uzaksa ya da çizgi çok uzunsa düz çizgi kalır. Vapur durak
  sırasıyla çizilir.
- Kalıcı çözüm GTFS `shapes` verisini yüklemektir (#15): Google kotası harcamaz ve resmî güzergâhı verir.

## Yer arama
Listeden seçmeden Enter'a basılırsa ya da alandan çıkılırsa yazılan metin Google'ın ilk önerisiyle çözülür
(`AutocompleteService` + `PlacesService`, Türkiye ve İstanbul öncelikli). `enlem, boylam` yazmak da çalışır.

## Otobüsleri gör (canlı yaklaşan otobüsler)
Seçili rotanın hemen üstünde **"Canlı otobüsler"** bölümü vardır (önceki "Hemen deneyin" örneklerinin yerine); rotadaki her
**İETT otobüsü bacağı** (metrobüs hariç) için bir satır ve "Otobüsleri gör" düğmesi içerir. Adım listesindeki bacak da aynı düğmeyi taşır ve
aynı paneli açar/kapar. Açılınca o bacağın biniş durağından iniş
durağına giden tüm hatlar çip olarak listelenir (**çoklu seçim** ve **Hepsi**); seçili hatların canlı araçları kapı
numarası ve biniş durağına kalan dakikayla sıralanır (10 sn'de bir yenilenir), tüm araçları haritada görünür (biniş durağına
yaklaşanlar turuncu halkalı). Aktarmalı rotada her otobüs bacağı kendi durağı için ayrı çalışır. Canlı araç yoksa planlı
kalkışlar gösterilir. Uç nokta: `GET /api/yaklasan` (docs/schema.md).

## Zaman ve filtre
- Zaman: **Şimdi**, **Kalkış** (şu saatte yola çıkmak istiyorum) ya da **Varış** (en geç şu saatte varmak istiyorum;
  `arrive_by`, en geç uygun kalkışı 1 dk çözünürlükle bulur).
- **Ulaşım türleri** açılır bölümü: rotada kullanmak istemediğiniz türlerin işaretini kaldırırsınız; kapalı türler hiç
  önerilmez.


## Kayıtlı yerler: Eve / İşe / favoriler / son aramalar (#24)

- Yalnızca kullanıcının cihazında (`localStorage`, anahtar `smarttransit-yerler`); hesap ve sunucu kaydı yok. Depolama yazılamıyorsa
  (gizli pencere, engelli çerez) kaydetme düğmeleri gizlenir, uygulama aynen çalışır.
- Yer alanı **boşken** odaklanınca liste açılır (Eve, İşe, favoriler, son aramalar); bir satıra dokunmak alanı doldurur. Her kayıtta
  silme düğmesi, "Son aramalar"da "Temizle", altta "Kayıtlı yerleri sil" ve "Yalnızca bu cihazda saklanır" notu var. Yazmaya başlayınca
  Google önerileri devreye girer, liste kapanır.
- Bir yer seçilince alanın yanındaki yer imi düğmesi menü açar: Eve / İşe olarak kaydet, favorilere ekle ya da çıkar (klavye: ok
  tuşları, Esc).
- Rota bulununca iki uç nokta son aramalara eklenir (en çok 5, aynı yer tekilleşir; "Konumum" eklenmez). Favoriler en çok 20.
- "Eve git" / "İşe git" kısayolları (kayıt varsa): varışı doldurur; başlangıç boşsa konumunuzu alır.
- Mantık `lib/yerlerMantik.ts` (saf, depolamasız) ve testi `lib/yerlerMantik.test.ts` (`npm test`, Node'un yerleşik test koşucusu); React
  bağlayıcısı `lib/yerler.ts`. Bozuk ya da İstanbul dışı kayıtlar okunurken atılır.


## Paylaşılabilir rota bağlantısı ve PWA (#27)

- **Bağlantı:** tamamlanmış arama (iki yer seçili) adres çubuğuna yazılır: `/?from=41.03700,28.98500&fn=Taksim&to=...&tn=...&t=k&d=2026-11-24T10:00&tercih=az_aktarma&modlar=metro,bus&yurume=1200`.
  Varsayılan değerler yazılmaz; "Şimdi" ise zaman parametresi yoktur. Yeni nereden/nereye geçmişe yeni kayıt ekler (geri/ileri tuşu önceki
  aramaya döner), seçenek değişiklikleri aynı kaydı günceller. Geçersiz/İstanbul dışı parametreler sessizce yok sayılır. Mantık: `lib/baglanti.ts`
  (saf, `lib/baglanti.test.ts`).
- **Konum gizliliği:** başlangıç "Konumum" ise bağlantıya yazılmaz; paylaşım sonrası "Konumunuz eklenmedi" notu gösterilir.
- **"Rotayı paylaş" düğmesi** (sonuç başlığında): Web Share API varsa sistem paylaşım menüsü, yoksa bağlantı panoya kopyalanır.
- **PWA:** `app/manifest.ts` (standalone, simgeler `public/icon-*.png`, maskable simge, `app/apple-icon.png`, `app/icon.svg`). Simge, uygulamadaki
  başlangıç (halka) ve varış (turuncu kare) işaretçisinin devamıdır. Servis çalışanı `public/sw.js` yalnızca üretim sürümünde kaydedilir
  (`PwaKayit`): uygulama kabuğu ve `_next/static` önbelleği, ağ yoksa kabuk ya da `public/cevrimdisi.html`. **API istekleri asla
  önbelleğe alınmaz** (rota ve canlı veri sunucuda; bayat veri gösterilmesin). `next.config.ts` `sw.js` için önbelleksiz başlık verir.
- Yayın adresi (A2) belli olunca `start_url`/`scope` ve (isteğe bağlı) paylaşım önizlemesi (OG görseli, P2) ayarlanır.


## Durak sayfası ve "Yakınımdaki duraklar" (#23)

- **Sayfa:** `/durak/<stop_id>` (kimlik adres çubuğunda kodlu). Başlık (durak adı, ulaşım türleri), favori yıldızı (#24), "Buradan git" / "Buraya git"
  (plan formunu doldurur), duraktan kalkan hatlar: rozet, yön ("X yönü"), büyük sayı = canlı kalan dakika (otobüs, "canlı" noktasıyla) ya da
  sıradaki planlı kalkış; altta sonraki tarife saatleri. 15 sn'de bir yenilenir (görünür sekmede). İETT erişilemiyorsa not düşer ve
  planlı kalkışlar gösterilir. "N hat daha göster" ile liste 12'den 30'a kadar genişler.
- **Arka uç:** `GET /api/stops/{stop_id}/departures?limit=` (`app/durak_api.py`). Aynı istasyonun kardeş durakları (aynı ad, ≤400 m) birleşir; (hat, yön)
  başına en çok seferli örüntü; bugünkü seferi bitmiş hatlar listelenmez; sıralama canlı ya da planlı kalan dakikaya göre. Canlı veri yalnızca
  otobüste ve kalkışı en yakın ilk 6 hat için aranır (İETT SOAP çağrı sayısı sınırlı; 15 sn önbellek). Hız sınırı dakikada 30.
- **Yakınımdaki duraklar:** ana ekranda (rota yokken) düğme; konum yalnızca düğmeye basınca istenir. `GET /api/stops/nearby` (varsayılan **600 m**,
  seçenekler 300 m / 600 m / 1 km, en çok 12 durak). **Haritada** (`YakinKatman`): konumunuz Google Haritalar'daki gibi beyaz halkalı mavi nokta
  (konum doğruluğu 25-400 m ise açık mavi doğruluk çemberiyle), arama yarıçapı kesikli daire (kapsama alanı), duraklar ulaşım türü renginde
  noktalar ve adlarıyla (22 karakterden uzun adlar kısaltılır; etiket `.harita-etiket`, zemin rengiyle halkalı). Listeden bir durağı ya da haritada
  işaretçisini seçince konumunuzdan o durağa **noktalı yürüyüş yolu** çizilir (Google yürüyüş rotası; alınamazsa düz noktalı çizgi), durak
  turuncu halkayla vurgulanır, satır açılır: "Kalkışlar ve canlı otobüsler" (durak sayfası) ve "Buraya git". Satırlarda mesafe ve yaklaşık yürüyüş süresi
  (kuş uçuşu × 1,3 / 4,8 km/s). "Haritadan kaldır" katmanı temizler; rota arayınca katman gizlenir.

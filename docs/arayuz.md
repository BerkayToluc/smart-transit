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
  tarife kitapçığından ölçülen turuncu; yalnız "şimdi/seçili"). Koyu tema `prefers-color-scheme` ile gelir.
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

# Arayüz (Faz 3)

`frontend/` Next.js 16 + React 19 + Tailwind 4. İki sekme: **Rota planla** (yeni, `components/rota/`) ve **Hat takibi**
(eski canlı otobüs ekranı, `components/HatTakibi.tsx`, davranışı değişmeden taşındı).

## Çalıştırma
```
uvicorn main:app --reload --port 8000        # kök klasörde; rota grafı için gtfs_data/graf.pkl (build_gtfs.py rota ile üretilir)
cd frontend && npm run dev                   # http://localhost:3000
```
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

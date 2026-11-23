# Spec #21: Sayfa başlığı/lang düzeltmeleri ve i18n (tr/en)

## Problem
Arayüz yalnızca Türkçe. İstanbul'daki turist ve yabancı yolcular rotayı okuyamıyor. `lang="tr"` doğru, fakat metinler koda gömülü.

## Hedefler
- Tüm arayüz metinleri tek sözlükten gelsin (tr, en); dil seçici ile geçiş, tarayıcı diline göre varsayılan.
- Rota yanıtındaki mesajlar (`mesaj`, `neden`) ve hata metinleri de çevrilebilsin.

## Hedef dışı
- Ek diller (ar, ru…) bu sürümde yok ama yapı onlara açık. Durak/hat adlarının çevirisi (resmî ad kalır).

## Gereksinimler
**P0**
- Metinleri `messages/tr.json` ve `messages/en.json` dosyalarına taşı; bileşenler anahtarla çağırır; `html lang` seçilen dile uyar.
  - Kabul: dil İngilizce seçilince panelde Türkçe metin kalmaz (durak/hat adları hariç); yenilemede dil korunur.
- Backend hata ayrıntıları kod + parametre döndürsün (örn. `neden: "baglanti_yok"` zaten var), metin ön yüzde çevrilsin.
**P1**
- Tarih/saat ve sayı biçimleri dile göre (`Intl`).
**P2**
- Sağdan sola diller için yerleşim hazırlığı.

## Başarı ölçütleri
- Çevrilmemiş anahtar sayısı 0 (CI'da kontrol). (Analitik varsa) İngilizce arayüz oturum oranı.

## Açık sorular
- (Ürün) Hedef kitle gerçekten turist mi? Yoksa Türkçe öncelik sürsün mü? (Değer/maliyet kararı; bu iş ~2–3 gün.)
- (Mühendislik) Next.js sürümüne uygun i18n yaklaşımı (`node_modules/next/dist/docs` içindeki rehberle belirlenmeli).

## Zamanlama
Metinler son halini bulmadan çevirme riskli: Faz 4 UI özellikleri (#24, #23) bittikten sonra.

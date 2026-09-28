import csv
import json
from main import SessionLocal, Hat, Durak


def ayirici_bul(dosya_yolu):
    try:
        with open(dosya_yolu, 'r', encoding='utf-8-sig') as f:
            ilk_satir = f.readline()
            if ';' in ilk_satir: return ';'
            if '\t' in ilk_satir: return '\t'
            return ','
    except:
        return ','


def guvenli_float(deger):
    if not deger:
        return 0.0
    deger = str(deger).replace(',', '.').strip()
    try:
        return float(deger)
    except ValueError:
        parcalar = deger.split('.')
        if len(parcalar) > 1:
            temiz = parcalar[0] + '.' + ''.join(parcalar[1:])
            try:
                return float(temiz)
            except:
                return 0.0
        return 0.0


def hatta_durak_ekle(istenen_hat_kodu, hat_adi):
    db = SessionLocal()

    try:
        istenen_hat_kodu = istenen_hat_kodu.strip().upper()

        hat = db.query(Hat).filter(Hat.hat_kodu == istenen_hat_kodu).first()
        if not hat:
            hat = Hat(hat_kodu=istenen_hat_kodu, hat_adi=hat_adi)
            db.add(hat)
            db.commit()
            db.refresh(hat)
            print(f"✅ {istenen_hat_kodu} ({hat_adi}) hattı veritabanına başarıyla eklendi.")
        else:
            print(f"⚠️ {istenen_hat_kodu} zaten var, eski durakları temizleniyor...")
            db.query(Durak).filter(Durak.hat_id == hat.id).delete()
            db.commit()

        # 2. Durakları Oku (stops.csv gerçek bir CSV dosyası, noktalı virgüllü)
        durak_bilgileri = {}
        try:
            ayirici = ayirici_bul('stops.csv')
            with open('stops.csv', mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=ayirici)
                for row in reader:
                    row_clean = {k.strip().lower() if k else '': str(v).strip() for k, v in row.items()}

                    durak_id = row_clean.get('stop_id') or row_clean.get('durak_id') or row_clean.get(
                        'durakkodu') or row_clean.get('sd_durak_id')
                    if durak_id:
                        durak_bilgileri[durak_id] = {
                            "adi": row_clean.get('stop_name') or row_clean.get('durak_adi') or row_clean.get(
                                'durakadi') or "Bilinmeyen",
                            "lat": guvenli_float(
                                row_clean.get('stop_lat') or row_clean.get('enlem') or row_clean.get('y')),
                            "lon": guvenli_float(
                                row_clean.get('stop_lon') or row_clean.get('boylam') or row_clean.get('x'))
                        }
        except FileNotFoundError:
            print("❌ HATA: stops.csv dosyası bulunamadı!")
            return

        # 3. Güzergahı Oku (Ajan Dosya Yakalama Operasyonu)
        eklenen_durak_sayisi = 0
        try:
            satirlar = []
            with open('guzergah.csv', mode='r', encoding='utf-8-sig') as f:
                ilk_karakter = f.read(1)
                f.seek(0)  # Dosyayı tekrar başa sarıyoruz

                # Eğer dosya { veya [ ile başlıyorsa bu bir JSON'dır!
                if ilk_karakter in ['{', '[']:
                    print(
                        "🕵️‍♂️ DİKKAT: guzergah.csv kılık değiştirmiş bir JSON dosyası! Maskesi düşürülüp okunuyor...")
                    veri = json.load(f)

                    # İETT'nin GeoJSON yapısı "features" içinde "properties" olarak gelir
                    if isinstance(veri, dict) and "features" in veri:
                        satirlar = [feat.get("properties", {}) for feat in veri["features"]]
                    elif isinstance(veri, list):
                        satirlar = veri
                    else:
                        satirlar = [veri]
                else:
                    # Eğer olur da bir gün gerçekten CSV koyarsan normal çalışsın
                    ayirici = ayirici_bul('guzergah.csv')
                    reader = csv.DictReader(f, delimiter=ayirici)
                    satirlar = list(reader)

            # Artık elimizde temiz bir liste var, taramaya başla!
            for row in satirlar:
                row_clean = {str(k).strip().lower(): str(v).strip() for k, v in row.items() if k}

                hat_kodu = row_clean.get('route_short_name') or row_clean.get('hat_kodu') or row_clean.get('hatkodu')

                if hat_kodu and hat_kodu.upper() == istenen_hat_kodu:
                    durak_id = row_clean.get('stop_id') or row_clean.get('durak_id') or row_clean.get(
                        'durakkodu') or row_clean.get('sd_durak_id')

                    if durak_id and durak_id in durak_bilgileri:
                        yeni_durak = Durak(
                            hat_id=hat.id,
                            durak_adi=durak_bilgileri[durak_id]["adi"],
                            latitude=durak_bilgileri[durak_id]["lat"],
                            longitude=durak_bilgileri[durak_id]["lon"],
                            sira_no=int(row_clean.get('stop_sequence') or row_clean.get('sira_no') or row_clean.get(
                                'sirano') or 0),
                            yon=str(row_clean.get('direction_id') or row_clean.get('yon') or "0")
                        )
                        db.add(yeni_durak)
                        eklenen_durak_sayisi += 1

            db.commit()
            print(
                f"🚀 MUHTEŞEM! {istenen_hat_kodu} hattına ait toplam {eklenen_durak_sayisi} durak Neon veritabanına yüklendi.")

        except FileNotFoundError:
            print("❌ HATA: guzergah.csv dosyası bulunamadı!")

    except Exception as e:
        print(f"Beklenmeyen bir hata oluştu: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    print("Akıllı Bot çalıştırılıyor, veriler analiz ediliyor...")
    hatta_durak_ekle("133GP", "GÖÇBEYLİ - KARTAL")
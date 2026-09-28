import json
from main import engine, SessionLocal, Base, Hat, Durak, text


def geojson_yukle():
    db = SessionLocal()
    dosya_adi = "hat_guzergahlari.geojson"  # Projeye attığın dosyanın tam adı

    print("1. Veritabanı tabloları hazırlanıyor...")
    # Tabloları temizleyip sıfırdan kuruyoruz
    db.execute(text("DROP TABLE IF EXISTS binis_loglari, otobusler, duraklar, hatlar CASCADE"))
    db.commit()
    Base.metadata.create_all(bind=engine)

    print(f"2. {dosya_adi} dosyası okunuyor (Bu biraz sürebilir)...")
    with open(dosya_adi, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    print(f"Toplam {len(features)} adet veri kaydı bulundu. İnceleme ve aktarım başlıyor...")

    # Öncelikle örnek bir kaydın anahtarlarını ekrana basalım ki yapıyı görelim
    if features:
        print("Örnek Veri Yapısı (Properties):", list(features[0].get("properties", {}).keys()))
        print("Örnek Geometri Tipi:", features[0].get("geometry", {}).get("type"))

    hat_cache = {}
    eklenen_durak = 0

    # Dosyadaki kayıtları dönüp veritabanına aktarma
    for index, item in enumerate(features):
        props = item.get("properties", {})
        geom = item.get("geometry", {})

        # Farklı İBB isimlendirme varyasyonlarına karşı toleranslı anahtar bulucu
        hat_kodu = str(props.get("HATKODU") or props.get("HAT_KODU") or props.get("hat_kodu") or "").strip().upper()
        durak_adi = str(props.get("DURAKADI") or props.get("DURAK_ADI") or props.get("durak_adi") or props.get(
            "AD") or "Bilinmeyen Durak").strip()
        yon = str(props.get("YON") or props.get("yon") or "GİDİŞ").strip().upper()
        sira_no = props.get("SIRA") or props.get("SIRA_NO") or props.get("sira_no") or (index + 1)

        coords = geom.get("coordinates", [])

        # Point tipi durak noktası ise: [lng, lat]
        if geom.get("type") == "Point" and len(coords) >= 2:
            lng, lat = float(coords[0]), float(coords[1])
        # LineString tipi güzergah ise (eğer duraklar değil yol çizgisi olarak verildiyse)
        elif geom.get("type") == "LineString" and coords:
            lng, lat = float(coords[0][0]), float(coords[0][1])
        else:
            continue

        if not hat_kodu:
            continue

        # Hattı ekle veya mevcut olanı getir
        if hat_kodu not in hat_cache:
            hat = Hat(hat_kodu=hat_kodu, hat_adi=f"Hat {hat_kodu}")
            db.add(hat)
            db.commit()
            db.refresh(hat)
            hat_cache[hat_kodu] = hat.id

        hat_id = hat_cache[hat_kodu]

        # Durağı ekle
        db.add(Durak(
            hat_id=hat_id,
            durak_adi=durak_adi,
            latitude=lat,
            longitude=lng,
            sira_no=int(sira_no) if str(sira_no).isdigit() else index + 1,
            yon=yon
        ))
        eklenen_durak += 1

        if eklenen_durak % 500 == 0:
            db.commit()
            print(f"{eklenen_durak} durak işlendi...")

    db.commit()
    db.close()
    print(f"TAMAMLANDI! Toplam {len(hat_cache)} hat ve {eklenen_durak} durak veritabanına aktarıldı.")


if __name__ == "__main__":
    geojson_yukle()
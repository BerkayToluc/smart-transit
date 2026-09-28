import csv
from main import engine, SessionLocal, Base, Hat, Durak, text


# İETT'nin bozuk Türkçe karakterlerini onaran sihirli sözlük
def turkce_duzelt(metin):
    if not metin: return ""
    return metin.replace('Ã–', 'Ö').replace('Ä°', 'İ').replace('Ã‡', 'Ç') \
        .replace('Åž', 'Ş').replace('Äž', 'Ğ').replace('Ãœ', 'Ü') \
        .replace('Ã¶', 'ö').replace('Ä±', 'ı').replace('Ã§', 'ç') \
        .replace('ÅŸ', 'ş').replace('ÄŸ', 'ğ').replace('Ã¼', 'ü')


# Hatalı koordinatları düzelten zırh (Örn: 410.191.700 -> 41.01917)
def safe_float(val):
    if not val: return 0.0
    val = str(val).replace(',', '.')
    try:
        return float(val)
    except ValueError:
        clean_str = ''.join(c for c in val if c.isdigit())
        if len(clean_str) > 2:
            return float(clean_str[:2] + '.' + clean_str[2:])
        return 0.0


# 🚀 OTOMATİK AYRAÇ DEDEKTİFİ
def ayar_bul(dosya_yolu):
    with open(dosya_yolu, 'r', encoding='utf-8-sig') as f:
        ilk_satir = f.readline()
        if ';' in ilk_satir:
            return ';'
        return ','


def gtfs_yukle():
    hedef_hatlar = ["401", "500T"]

    print("1. routes.csv okunuyor...")
    hedef_route_ids = {}
    ayrac = ayar_bul('routes.csv')
    with open('routes.csv', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=ayrac)
        for row in reader:
            short_name = str(row.get('route_short_name', '')).strip().upper()
            if short_name in hedef_hatlar:
                hedef_route_ids[row.get('route_id', '').strip()] = short_name

    if not hedef_route_ids:
        print("HATA: 401 veya 500T hâlâ bulunamadı!")
        return

    print(f"BAŞARILI! Hat ID'leri bulundu.")

    print("2. trips.csv okunuyor...")
    trip_info = {}
    secilen_yonler = set()
    ayrac = ayar_bul('trips.csv')
    with open('trips.csv', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=ayrac)
        for row in reader:
            r_id = str(row.get('route_id', '')).strip()
            if r_id in hedef_route_ids:
                hat_kodu = hedef_route_ids[r_id]
                dir_id = str(row.get('direction_id', '0')).strip()

                key = (hat_kodu, dir_id)
                if key not in secilen_yonler:
                    secilen_yonler.add(key)
                    trip_info[str(row.get('trip_id', '')).strip()] = (hat_kodu, dir_id)

    print(f"Seçilen Seferler: {len(trip_info)} adet. (Gidiş-Dönüş)")

    print("3. stop_times.csv.txt okunuyor... (Lütfen bekleyin)")
    trip_stops = {trip_id: [] for trip_id in trip_info.keys()}
    ayrac = ayar_bul('stop_times.csv.txt')
    with open('stop_times.csv.txt', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=ayrac)
        for row in reader:
            t_id = str(row.get('trip_id', '')).strip()
            if t_id in trip_stops:
                s_seq_raw = str(row.get('stop_sequence', '0')).strip()
                s_seq = int(s_seq_raw) if s_seq_raw.isdigit() else 0
                trip_stops[t_id].append({
                    'stop_id': str(row.get('stop_id', '')).strip(),
                    'stop_sequence': s_seq
                })

    print("4. stops.csv okunuyor...")
    stop_details = {}
    ayrac = ayar_bul('stops.csv')
    with open('stops.csv', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=ayrac)
        for row in reader:
            stop_details[str(row.get('stop_id', '')).strip()] = {
                'name': turkce_duzelt(str(row.get('stop_name', 'Bilinmeyen Durak')).strip()),
                'lat': safe_float(row.get('stop_lat', '0')),
                'lon': safe_float(row.get('stop_lon', '0'))
            }

    print("5. Veritabanı hazırlanıyor ve GERÇEK veriler yazılıyor...")
    db = SessionLocal()
    db.execute(text("DROP TABLE IF EXISTS binis_loglari, otobusler, duraklar, hatlar CASCADE"))
    db.commit()
    Base.metadata.create_all(bind=engine)

    hat_nesneleri = {}
    for hat_kodu in hedef_hatlar:
        yeni_hat = Hat(hat_kodu=hat_kodu, hat_adi=f"İETT {hat_kodu} Hattı")
        db.add(yeni_hat)
        db.commit()
        db.refresh(yeni_hat)
        hat_nesneleri[hat_kodu] = yeni_hat.id

    eklenen_durak = 0
    for trip_id, stops in trip_stops.items():
        hat_kodu, direction_id = trip_info[trip_id]
        yon_adi = "GİDİŞ" if direction_id == "0" else "DÖNÜŞ"
        hat_db_id = hat_nesneleri.get(hat_kodu)

        if not hat_db_id: continue

        stops.sort(key=lambda x: x['stop_sequence'])

        for s in stops:
            s_detail = stop_details.get(s['stop_id'])
            if s_detail:
                if s_detail['lat'] == 0.0 or s_detail['lon'] == 0.0:
                    continue

                db.add(Durak(
                    hat_id=hat_db_id,
                    durak_adi=s_detail['name'],
                    latitude=s_detail['lat'],
                    longitude=s_detail['lon'],
                    sira_no=s['stop_sequence'],
                    yon=yon_adi
                ))
                eklenen_durak += 1

    db.commit()
    db.close()
    print(f"MÜKEMMEL! Tam {eklenen_durak} adet GERÇEK durak veritabanına işlendi.")


if __name__ == "__main__":
    gtfs_yukle()
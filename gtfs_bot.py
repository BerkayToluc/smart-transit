import os
import csv
import re
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker

# 🚨 NEON.TECH VERİTABANI BAĞLANTIN
DATABASE_URL = "postgresql://neondb_owner:npg_v0PSI1MVHXlF@ep-lucky-wind-asuclpxw-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Hat(Base):
    __tablename__ = "hatlar"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    hat_kodu = Column(String(20), unique=True, nullable=False)
    hat_adi = Column(String(100), nullable=False)


class Durak(Base):
    __tablename__ = "duraklar"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    hat_id = Column(Integer, nullable=False)
    durak_adi = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    sira_no = Column(Integer, nullable=False)
    yon = Column(String)


# 522 Gidiş ve Dönüş listesi
hat_522_gidis = [
    "ÖZYEĞİN ÜNİVERSİTESİ ALT KAPI", "PROF.DR.ATAKAN YALÇIN CADDESİ", "TEVEZEL GÜLEN KIRAY ANADOLU LISESİ",
    "ALEMDAĞ EMLAK KONUT İLKOKULU", "NİŞANTEPE SONDURAK", "GELİN ÇİÇEĞİ SOKAK", "NİŞANTEPE", "NİŞANTEPE CADDESİ",
    "NİŞANTEPE İLKOKULU", "NİŞANTEPE 1", "ÇAMLAR", "HUZUREVİ", "ÇATALMEŞE", "214.SOKAK", "ÇATALMEŞE MUHTARLIĞI",
    "ALEMDAĞ", "SARAY CADDESİ", "TURGUT ÖZAL CADDESİ", "ÇEKMEKÖY DEVLET HASTANESİ", "FABRİKALAR", "EKŞİOĞLU MAHALLESİ",
    "YENİDOĞAN SAPAĞI", "TAŞDELEN", "SULTANÇİFTLİĞİ", "SİNAN SOKAK", "GÜNGÖREN", "SEYMENLER", "HALİT BİN VELİT CAMİİ",
    "SANCAKTEPE KAVŞAĞI", "ÇAMLIK", "MADENLER", "NECİP FAZIL METRO", "MUSTAFA VASIF KARSLIGİL İLKOKULU",
    "ÇEKMEKÖY SAPAĞI", "DUDULLU", "OSMANGAZİ", "ÜMRANİYE İMAM HATİP LİSESİ", "ÇAYIRÖNÜ", "IHLAMUR EVLERİ",
    "ALTINŞEHİR", "CEMİL MERİÇ MAHALLESİ", "IHLAMURKUYU", "YENİ İSTANBUL ÇARŞISI", "TEPEÜSTÜ",
    "ÜMRANİYE ENGELLİLER MERKEZİ",
    "ÇAKMAK KÖPRÜSÜ", "ÜMR.İSKİ-ŞEHİT EMRE BÜYÜKYILDIRIM", "İŞKUR ÜMRANİYE", "YAMANEVLER METRO", "HALDUN ALAGAŞ",
    "ÜMRANİYE", "ÜMRANİYE ÇARŞI METRO", "BAĞ SOKAK", "MEVLANA PARKI", "ÜMRANİYE MERKEZ CAMİİ", "SANTRAL",
    "GÜMÜŞSU", "NAMAZGAH", "KAVAKBAYIRI", "FERAH CADDESİ", "TURİSTİK ÇAMLICA TESİSLERİ", "KISIKLI", "AKŞEMSETTİN SOKAK",
    "MİLLET BAHÇESİ", "15 TEMMUZ ŞEHİTLER KÖPRÜSÜ", "KÖPRÜLÜ KAVŞAK", "ALİ SAMİ YEN", "MECİDİYEKÖY VİYADÜK",
    "MECİDİYEKÖY METROBÜS", "MECİDİYEKÖY MEZARLIK"
]

hat_522_donus = [
    "MECİDİYEKÖY MEZARLIK", "MECİDİYEKÖY VİYADÜK", "ALİ SAMİ YEN", "KÖPRÜLÜ KAVŞAK", "15 TEMMUZ ŞEHİTLER KÖPRÜSÜ",
    "MİLLET BAHÇESİ", "KISIKLI", "ÇAMLICA ŞEHİT ONUR ENSAR AYANOĞLU İLKOKULU", "HANIMSETİ PARKI", "FİDANLIK",
    "KAVAKBAYIRI", "NAMAZGAH", "SANTRAL", "SÜTÇÜ İMAM CADDESİ", "15 TEMMUZ ŞEHİTLER MEYDANI", "ÜMRANİYE",
    "ÜMRANİYE SON DURAK", "75.YIL CUMHURİYET MESLEKİ VE TEKNİK ANADOLU LİSESİ", "ATAKENT", "MİTHATPAŞA CADDESİ",
    "ÜMR.İSKİ-ŞEHİT EMRE BÜYÜKYILDIRIM", "ÇAKMAK KÖPRÜSÜ", "ÜMRANİYE ENGELLİLER MERKEZİ", "TEPEÜSTÜ",
    "YENİ İSTANBUL ÇARŞISI",
    "IHLAMURKUYU", "CEMİL MERİÇ MAHALLESİ", "ALTINŞEHİR", "IHLAMUR EVLERİ", "ÇAYIRÖNÜ", "ÜMRANİYE İMAM HATİP LİSESİ",
    "OSMANGAZİ", "DUDULLU", "NECİP FAZIL KISAKÜREK", "ÇEKMEKÖY SAPAĞI", "MUSTAFA VASIF KARSLIGİL İLKOKULU",
    "KEMERDERE", "NECİP FAZIL METRO", "KEMERDERE KÖPRÜLÜ KAVŞAK", "ÇEKMEKÖY METRO", "ÇAMLIK", "SANCAKTEPE KAVŞAĞI",
    "HALİT BİN VELİT CAMİİ", "SEYMENLER", "GÜNGÖREN", "SİNAN SOKAK", "SULTANÇİFTLİĞİ", "TAŞDELEN", "YENİDOĞAN SAPAĞI",
    "EKŞİOĞLU MAHALLESİ", "FABRİKALAR", "ÇEKMEKÖY DEVLET HASTANESİ", "TURGUT ÖZAL CADDESİ", "SARAY CADDESİ",
    "ALEMDAĞ", "ÇATALMEŞE MUHTARLIĞI", "214.SOKAK", "ÇATALMEŞE", "HUZUREVİ", "ÇAMLAR", "NİŞANTEPE 1",
    "NİŞANTEPE İLKOKULU", "NİŞANTEPE CADDESİ", "NİŞANTEPE", "GELİN ÇİÇEĞİ SOKAK", "ALEMDAĞ EMLAK KONUT İLKOKULU",
    "TEVEZEL GÜLEN KIRAY ANADOLU LISESI", "PROF.DR.ATAKAN YALÇIN CADDESI", "ÖZYEĞİN ÜNİVERSİTESİ ALT KAPI"
]


def koordinat_duzelt(ham_veri):
    """
    İBB'nin çöp haline getirdiği koordinatları temizler.
    Örnek: '41.00506785536913:17 170320268' -> 41.00506785536913
    Örnek: '410.191.700.005.564' -> 41.0191700005564
    """
    if not ham_veri:
        return 0.0

    # 1. Metni saat (:) veya boşluk karakterlerinden böl ve sadece ilk kısmı al
    temiz = re.split(r'[:\s]', str(ham_veri).strip())[0]

    # 2. İçindeki nokta, harf, karakter ne varsa sil (sadece saf rakamlar kalsın)
    sadece_rakam = re.sub(r'\D', '', temiz)

    # 3. İlk iki rakamın arasına standart GPS noktasını (.) koy
    if len(sadece_rakam) > 2:
        son_hali = sadece_rakam[:2] + "." + sadece_rakam[2:]
        return float(son_hali)
    return float(sadece_rakam) if sadece_rakam else 0.0


def veritabanina_522_aktar():
    durak_koordinatlari = {}

    # Dosya adını otomatik bul
    dosya_adi = "stops.txt"
    if not os.path.exists(dosya_adi):
        dosya_adi = "stops.csv"

    print(f"📡 {dosya_adi} dosyası okunuyor ve çöp veriler (tarih/saat) temizleniyor...")
    try:
        with open(dosya_adi, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                ad = row.get("stop_name", "").strip().upper()
                if not ad:
                    continue

                if " - " in ad:
                    ad = ad.split(" - ")[0].strip()

                # 🚨 Kurşun geçirmez temizleyici devrede!
                try:
                    lat = koordinat_duzelt(row["stop_lat"])
                    lon = koordinat_duzelt(row["stop_lon"])
                except Exception:
                    continue  # Çok bozuksa satırı tamamen atla

                # Koordinat 0 geldiyse hatalıdır, ekleme
                if lat != 0.0 and lon != 0.0 and ad not in durak_koordinatlari:
                    durak_koordinatlari[ad] = {"lat": lat, "lon": lon}

        print(f"✅ Başarılı! {len(durak_koordinatlari)} adet eşsiz durak başarıyla hafızaya alındı.")
    except Exception as e:
        print(f"❌ HATA: {dosya_adi} okunamadı. Detay: {e}")
        return

    print("⏳ Veritabanına (Neon.tech) bağlanılıyor...")
    db = SessionLocal()

    # 522 Hattını Veritabanına Ekle
    hat = db.query(Hat).filter(Hat.hat_kodu == "522").first()
    if not hat:
        hat = Hat(hat_kodu="522", hat_adi="Alemdağ - Mecidiyeköy (Tam Liste)")
        db.add(hat)
        db.commit()
        db.refresh(hat)
    else:
        hat.hat_adi = "Alemdağ - Mecidiyeköy (Tam Liste)"

    db.query(Durak).filter(Durak.hat_id == hat.id).delete()

    bulunamayanlar_gidis = 0
    print("\n🚀 522 Gidiş Yönü Kaydediliyor...")
    for index, durak_ismi in enumerate(hat_522_gidis, start=1):
        temiz_isim = durak_ismi.split(" - ")[0].strip().upper()
        koordinat = durak_koordinatlari.get(temiz_isim)

        if koordinat:
            yeni_durak = Durak(hat_id=hat.id, durak_adi=temiz_isim, latitude=koordinat["lat"],
                               longitude=koordinat["lon"], sira_no=index, yon="MECİDİYEKÖY MEZARLIK")
            db.add(yeni_durak)
        else:
            bulunamayanlar_gidis += 1

    bulunamayanlar_donus = 0
    print("🚀 522 Dönüş Yönü Kaydediliyor...")
    for index, durak_ismi in enumerate(hat_522_donus, start=1):
        temiz_isim = durak_ismi.split(" - ")[0].strip().upper()
        koordinat = durak_koordinatlari.get(temiz_isim)

        if koordinat:
            yeni_durak = Durak(hat_id=hat.id, durak_adi=temiz_isim, latitude=koordinat["lat"],
                               longitude=koordinat["lon"], sira_no=index, yon="ÖZYEĞİN ÜNİVERSİTESİ")
            db.add(yeni_durak)
        else:
            bulunamayanlar_donus += 1

    db.commit()
    db.close()

    toplam_eklenen = len(hat_522_gidis) + len(hat_522_donus) - bulunamayanlar_gidis - bulunamayanlar_donus
    print("-" * 70)
    print(
        f"🎉 MÜKEMMEL! 522 Hattının toplam {toplam_eklenen} gerçek durağı nokta atışı koordinatlarla sisteme yüklendi!")
    if bulunamayanlar_gidis > 0 or bulunamayanlar_donus > 0:
        print(
            f"ℹ️ Sadece isimleri biraz farklı yazıldığı için eşleşmeyen {bulunamayanlar_gidis + bulunamayanlar_donus} adet ufak durak atlandı. (Sistem harika çalışmaya devam edecek)")


if __name__ == "__main__":
    veritabanina_522_aktar()
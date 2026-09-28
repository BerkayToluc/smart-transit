from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime, timezone
from pydantic import BaseModel
from cachetools import cached, TTLCache
import math
import requests
import xml.etree.ElementTree as ET
import json
import csv
import os
import threading
import ijson  # pip install ijson

app = FastAPI(title="SmartTransit API")

# 🚨 GÜVENLİK DUVARI AÇIK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🚨 NEON.TECH VERİTABANI
DATABASE_URL = "postgresql://neondb_owner:npg_v0PSI1MVHXlF@ep-lucky-wind-asuclpxw-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

GTFS_KLASORU = "./gtfs_data"  # main.py ile aynı dizine göre göreceli yol
GEOJSON_DOSYA = os.path.join(GTFS_KLASORU, "iett-hat-guzergahlari.geojson")


# =====================================================================
# 📦 VERİTABANI MODELLERİ
# =====================================================================
class Hat(Base):
    __tablename__ = "hatlar"
    id = Column(Integer, primary_key=True, index=True)
    hat_kodu = Column(String(20), unique=True, nullable=False)
    hat_adi = Column(String(100), nullable=False)


class Durak(Base):
    __tablename__ = "duraklar"
    id = Column(Integer, primary_key=True, index=True)
    hat_id = Column(Integer, ForeignKey("hatlar.id"), nullable=False)
    durak_adi = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    sira_no = Column(Integer, nullable=False)
    yon = Column(String)


class OtobusLive(Base):
    __tablename__ = "otobusler"
    id = Column(Integer, primary_key=True, index=True)
    plaka = Column(String(20), unique=True, nullable=False)
    hat_id = Column(Integer, ForeignKey("hatlar.id"), nullable=False)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)
    son_guncelleme = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Guzergah(Base):
    __tablename__ = "guzergah_noktalari"
    id = Column(Integer, primary_key=True, index=True)
    hat_id = Column(Integer, ForeignKey("hatlar.id"), nullable=False)
    yon = Column(String, nullable=False)
    sira_no = Column(Integer, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    print("Mükemmel! Veritabanı bağlandı ve tablolar oluşturuldu.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================================
# 🚀 (ESKİ/KULLANILMIYOR) — otomatik_kurulum, gtfs_aktar ile değiştirildi.
# main.py'de sadece referans/geçmiş olsun diye duruyor, artık çağırmıyoruz.
# =====================================================================
def yola_durak_diz(db, hat_id, durak_isimleri, yon_adi, baslangic_idx, bitis_idx, lat1, lon1, lat2, lon2,
                   baslangic_sira):
    secilen_duraklar = durak_isimleri[baslangic_idx:bitis_idx]
    adet = len(secilen_duraklar)
    if adet == 0: return baslangic_sira
    step_lat = (lat2 - lat1) / adet
    step_lon = (lon2 - lon1) / adet
    for i, isim in enumerate(secilen_duraklar):
        d_lat = lat1 + (step_lat * i)
        d_lon = lon1 + (step_lon * i)
        db.add(Durak(hat_id=hat_id, durak_adi=isim, latitude=d_lat, longitude=d_lon, sira_no=baslangic_sira + i,
                     yon=yon_adi))
    return baslangic_sira + adet


# =====================================================================

@app.get("/")
def ana_sayfa():
    return {"mesaj": "SmartTransit API Tıkır Tıkır Çalışıyor"}


def mesafe_hesapla_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@app.get("/api/hatlar")
def api_hatlari_getir(db: Session = Depends(get_db)):
    hatlar = db.query(Hat).all()
    return [{"id": h.id, "hat_kodu": h.hat_kodu, "hat_adi": h.hat_adi} for h in hatlar]


@app.get("/api/duraklar/{hat_id}")
def api_duraklari_getir(hat_id: int, db: Session = Depends(get_db)):
    duraklar = db.query(Durak).filter(Durak.hat_id == hat_id).order_by(Durak.sira_no).all()
    return [{
        "id": d.id,
        "durak_adi": d.durak_adi,
        "latitude": float(d.latitude),
        "longitude": float(d.longitude),
        "sira_no": d.sira_no,
        "yon": d.yon
    } for d in duraklar]


# 🚀 15 SANİYELİK İETT ÖNBELLEĞİ (CACHE SİSTEMİ)
iett_cache = TTLCache(maxsize=100, ttl=15)

# 🚗 OTOBÜS GEÇMİŞİ: her aracın (hat_kodu + kapı no ile) SON bilinen konumunu,
# zamanını ve eşleştiği durak sıra numarasını tutuyoruz. Bu, iki şeyi sağlıyor:
#   1) GERÇEK ZAMANLI HIZ: iki ardışık konum arasındaki mesafe/süre = anlık hız
#      (trafikte otomatik düşer, açık yolda otomatik yükselir) — sabit 25 km/s
#      varsayımı yerine.
#   2) GERİYE SIÇRAMAYI ÖNLEME: yol kıvrımlı olduğunda otobüsün kuş uçuşu en
#      yakın durağı yanlışlıkla "ileride bir durak" çıkabiliyordu (otobüs henüz
#      geçmediği halde listeden anında siliniyordu). Artık sıra numarası bir
#      önceki bilinen değerden mantıksız şekilde ileri/geri sıçrayamıyor.
# 10 dakika boyunca konum güncellemesi gelmeyen bir araç listeden otomatik düşer.
_otobus_gecmisi = TTLCache(maxsize=2000, ttl=600)

VARSAYILAN_HIZ_KMH = 25.0   # geçmişi olmayan araçlar için tipik şehir içi otobüs hızı
MAKS_MAKUL_HIZ_KMH = 80.0   # bundan hızlıysa muhtemelen GPS sıçraması, güvenme
ETKIN_HIZ_MIN_KMH = 10.0    # ETA hesabında kullanılacak en düşük hız (sonsuz bekleme çıkmasın)
ETKIN_HIZ_MAX_KMH = 45.0    # ETA hesabında kullanılacak en yüksek hız
GECTI_TOLERANS_KM = 0.05    # otobüs durağı bundan fazla geçtiyse listeden düşer (50 m)
ROTADAN_MAKS_SAPMA_KM = 2.0 # rotaya bundan uzaktaki araç bu güzergahta sayılmaz

# TTLCache thread-safe DEĞİL; FastAPI sync endpoint'leri thread havuzunda çalıştığı
# için okuma/yazmayı kilitle koruyoruz.
_gecmis_kilit = threading.Lock()


def _gecmis_al(anahtar):
    with _gecmis_kilit:
        return _otobus_gecmisi.get(anahtar)


def _gecmis_yaz(anahtar, deger):
    with _gecmis_kilit:
        _otobus_gecmisi[anahtar] = deger


def _rota_kumulatif_mesafe(duraklar):
    """Durak listesi boyunca ilk duraktan her durağa kadar YOL BOYU kümülatif mesafe (km)."""
    kum = [0.0]
    for i in range(1, len(duraklar)):
        kum.append(kum[-1] + mesafe_hesapla_km(
            float(duraklar[i - 1].latitude), float(duraklar[i - 1].longitude),
            float(duraklar[i].latitude), float(duraklar[i].longitude),
        ))
    return kum


def _noktayi_segmente_izdusur(p_lat, p_lon, a_lat, a_lon, b_lat, b_lon):
    """
    P noktasını A-B doğru parçasına izdüşürür. (P'nin doğru parçasına uzaklığı km, t) döner.
    t: 0 = A noktası, 1 = B noktası. Kısa mesafelerde düzlemsel yaklaşım yeterince hassas.
    """
    ort_lat = math.radians((a_lat + b_lat) / 2)
    kx = 111.320 * math.cos(ort_lat)  # 1 derece boylam kaç km
    ky = 110.540                       # 1 derece enlem kaç km
    bx, by = (b_lon - a_lon) * kx, (b_lat - a_lat) * ky
    px, py = (p_lon - a_lon) * kx, (p_lat - a_lat) * ky
    ab2 = bx * bx + by * by
    t = 0.0 if ab2 < 1e-12 else max(0.0, min(1.0, (px * bx + py * by) / ab2))
    return math.hypot(px - bx * t, py - by * t), t


def _otobus_rota_konumu(arac_lat, arac_lon, duraklar, kum, onceki, gecen_sn):
    """
    Otobüsün rota üzerindeki konumunu bulur. (rotaya_sapma_km, rota_konumu_km) döner.
    En yakın DURAĞA değil, en yakın DOĞRU PARÇASINA bakılır; böylece iki durak arasındaki
    otobüs, henüz geçmediği bir durağa 'yakın' diye yanlışlıkla ileri sayılmaz.
    Önceki bilinen konum varsa, makul bir ileri/geri pencere içindeki eşleşme tercih edilir.
    """
    adaylar = []
    for i in range(len(duraklar) - 1):
        a, b = duraklar[i], duraklar[i + 1]
        sapma, t = _noktayi_segmente_izdusur(
            arac_lat, arac_lon,
            float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude),
        )
        adaylar.append((sapma, kum[i] + t * (kum[i + 1] - kum[i])))

    if not adaylar:
        return None

    genel_en_iyi = min(adaylar, key=lambda c: c[0])

    if onceki and onceki.get("s") is not None:
        ileri_pay = 0.6 + MAKS_MAKUL_HIZ_KMH * (min(gecen_sn, 600) / 3600)
        geri_pay = 0.3
        pencere = [c for c in adaylar if onceki["s"] - geri_pay <= c[1] <= onceki["s"] + ileri_pay]
        if pencere:
            pencere_en_iyi = min(pencere, key=lambda c: c[0])
            # Pencere içindeki eşleşme genel en iyiden en fazla 80 m kötüyse pencereye güven
            if pencere_en_iyi[0] <= genel_en_iyi[0] + 0.08:
                return pencere_en_iyi

    return genel_en_iyi


@cached(cache=iett_cache)
def iett_verisi_cek(hat_kodu: str):
    SOAP_URL = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <GetHatOtoKonum_json xmlns="http://tempuri.org/">
          <HatKodu>{hat_kodu}</HatKodu>
        </GetHatOtoKonum_json>
      </soap:Body>
    </soap:Envelope>"""
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': '"http://tempuri.org/GetHatOtoKonum_json"'
    }
    try:
        response = requests.post(SOAP_URL, data=soap_body, headers=headers)
        response.raise_for_status()
        root = ET.fromstring(response.text)
        namespaces = {'ns': 'http://tempuri.org/'}
        result = root.find('.//ns:GetHatOtoKonum_jsonResult', namespaces)
        if result is None or not result.text:
            return []
        return json.loads(result.text)
    except:
        return []


@app.get("/api/canli-otobus/{hat_kodu}")
def canli_otobus_getir(hat_kodu: str):
    otobusler = iett_verisi_cek(hat_kodu)
    if not otobusler:
        return {"mesaj": "Aktif araç bulunamadı", "araclar": []}
    return {"mesaj": f"{hat_kodu} hattında {len(otobusler)} araç bulundu", "araclar": otobusler}


@app.get("/api/moovit/{hat_kodu}/{durak_id}/{hedef_yon}")
def moovit_dinamik_algoritma(hat_kodu: str, durak_id: int, hedef_yon: str, db: Session = Depends(get_db)):
    durak = db.query(Durak).filter(Durak.id == durak_id).first()
    if not durak:
        return {"hata": f"{durak_id} ID numaralı durak veritabanında bulunamadı!"}

    tum_hat_duraklari = db.query(Durak).filter(Durak.hat_id == durak.hat_id).all()
    hedef_duraklar = sorted([d for d in tum_hat_duraklari if d.yon == hedef_yon], key=lambda x: x.sira_no)
    ters_duraklar = sorted([d for d in tum_hat_duraklari if d.yon != hedef_yon], key=lambda x: x.sira_no)

    if len(hedef_duraklar) < 2:
        return {"hata": "Bu yöne ait yeterli durak bulunamadı."}

    hedef_son_metin = " ".join([d.durak_adi.upper() for d in hedef_duraklar[-15:]])
    ters_son_metin = " ".join([d.durak_adi.upper() for d in ters_duraklar[-15:]])

    otobusler = iett_verisi_cek(hat_kodu)
    if not otobusler:
        return {"mesaj": "Bu hatta şu an aktif araç bulunamadı."}

    kesin_ters_yonler = set()
    kesin_hedef_yonler = set()

    for arac in otobusler:
        i_yon = str(arac["yon"]).upper()
        kelimeler = [k for k in i_yon.replace("-", " ").split() if len(k) > 2]
        is_ters = any(k in ters_son_metin for k in kelimeler)
        is_hedef = any(k in hedef_son_metin for k in kelimeler)
        if is_ters and not is_hedef:
            kesin_ters_yonler.add(i_yon)
        elif is_hedef and not is_ters:
            kesin_hedef_yonler.add(i_yon)

    # Rota boyunca kümülatif mesafe ve yolcunun durağının rota üzerindeki konumu (km)
    kum = _rota_kumulatif_mesafe(hedef_duraklar)
    yolcu_idx = next((i for i, d in enumerate(hedef_duraklar) if d.id == durak.id), None)
    if yolcu_idx is None:
        yolcu_idx = next((i for i, d in enumerate(hedef_duraklar) if d.sira_no == durak.sira_no), 0)
    yolcu_s = kum[yolcu_idx]

    yaklasan_araclar = []
    simdi = datetime.now(timezone.utc)

    for arac in otobusler:
        i_yon = str(arac["yon"]).upper()
        if i_yon in kesin_ters_yonler:
            continue
        if len(kesin_ters_yonler) > 0 and i_yon not in kesin_ters_yonler:
            pass
        elif len(kesin_hedef_yonler) > 0 and i_yon not in kesin_hedef_yonler:
            continue

        try:
            arac_lat = float(str(arac["enlem"]).replace(',', '.'))
            arac_lon = float(str(arac["boylam"]).replace(',', '.'))
        except (KeyError, ValueError):
            continue

        # Geçmiş anahtarına YÖN de dahil: farklı yönlerin rota konumları birbirine karışmasın
        gecmis_anahtar = f"{hat_kodu}:{hedef_yon}:{arac.get('kapino', '')}"
        onceki = _gecmis_al(gecmis_anahtar)
        gecen_sn = (simdi - onceki["zaman"]).total_seconds() if onceki else 0

        # --- 🛣️ Otobüsün rota üzerindeki gerçek konumu (en yakın doğru parçasına izdüşüm) ---
        konum = _otobus_rota_konumu(arac_lat, arac_lon, hedef_duraklar, kum, onceki, gecen_sn)
        if konum is None:
            continue
        sapma_km, s_bus = konum
        if sapma_km > ROTADAN_MAKS_SAPMA_KM:
            continue  # bu güzergahta değil (ör. garaja dönen / farklı hat varyantı)

        # --- ⚡ Gerçek zamanlı hız (üstel yumuşatmalı) ---
        # IETT verisi 15 sn önbellekten geliyor: konum değişmediyse (önbellek ya da duran araç)
        # eski kaydı olduğu gibi bırakıyoruz ki bir sonraki gerçek hareket, DOĞRU süreyle
        # (son farklı konumdan itibaren) karşılaştırılsın.
        ema = onceki.get("hiz_ema") if onceki else None
        yeni_kayit = {"lat": arac_lat, "lon": arac_lon, "zaman": simdi, "s": s_bus, "hiz_ema": ema}

        if onceki:
            kat_edilen_km = mesafe_hesapla_km(onceki["lat"], onceki["lon"], arac_lat, arac_lon)
            if kat_edilen_km < 0.005:
                yeni_kayit = onceki
            elif gecen_sn > 2:
                anlik = kat_edilen_km / (gecen_sn / 3600)
                anlik = min(max(anlik, 1.0), MAKS_MAKUL_HIZ_KMH)
                ema = anlik if ema is None else 0.5 * ema + 0.5 * anlik
                yeni_kayit["hiz_ema"] = ema

        _gecmis_yaz(gecmis_anahtar, yeni_kayit)

        # Gözlenen hızı tipik hızla harmanla: tek bir kırmızı ışık ya da hızlı ölçüm ETA'yı zıplatmasın
        etkin_hiz = VARSAYILAN_HIZ_KMH if ema is None else 0.5 * ema + 0.5 * VARSAYILAN_HIZ_KMH
        etkin_hiz = min(max(etkin_hiz, ETKIN_HIZ_MIN_KMH), ETKIN_HIZ_MAX_KMH)

        # --- Yolcunun durağına yol boyu kalan mesafe (işaretli) ---
        kalan_km = yolcu_s - s_bus
        if kalan_km < -GECTI_TOLERANS_KM:
            continue  # durağı gerçekten geçti
        kalan_km = max(kalan_km, 0.0)

        # 1 dakikadan az kalan araç da listede kalsın (min 1 dk)
        kalan_dakika = max(1, int(round(kalan_km / etkin_hiz * 60)))

        if kalan_dakika < 120:
            yaklasan_araclar.append({
                "kapi_no": arac["kapino"],
                "mesafe_km": round(kalan_km, 2),
                "tahmini_varis_dakika": kalan_dakika,
                "gittigi_yon": arac["yon"],
                "hiz_kmh": round(etkin_hiz, 1),
            })

    yaklasan_araclar = sorted(yaklasan_araclar, key=lambda k: k['tahmini_varis_dakika'])

    return {
        "sorgulanan_durak": durak.durak_adi,
        "secilen_hedef": hedef_yon,
        "yolcuya_bilgi": yaklasan_araclar
    }


class EvrenselRotaIstegi(BaseModel):
    hat_kodu: str
    baslangic_lat: float
    baslangic_lng: float
    hedef_lat: float
    hedef_lng: float


@app.post("/api/en-yakin-durak")
def en_yakin_durak_bul(istek: EvrenselRotaIstegi, db: Session = Depends(get_db)):
    hat = db.query(Hat).filter(Hat.hat_kodu == istek.hat_kodu.upper()).first()
    if not hat:
        return {"hata": f"{istek.hat_kodu} hattı veritabanında bulunamadı."}

    tum_duraklar = db.query(Durak).filter(
        Durak.hat_id == hat.id,
        Durak.yon != None,
        Durak.sira_no != None
    ).all()

    if not tum_duraklar:
        return {"hata": "Bu hatta ait kayıtlı geçerli durak bulunamadı."}

    yonler = set([d.yon for d in tum_duraklar])
    dogru_yon = None
    en_yakin_baslangic = None
    en_kisa_yurume = float('inf')

    try:
        for y in yonler:
            duraklar_y = [d for d in tum_duraklar if d.yon == y]
            if not duraklar_y:
                continue
            baslangic_d = min(duraklar_y, key=lambda d: mesafe_hesapla_km(istek.baslangic_lat, istek.baslangic_lng,
                                                                          float(d.latitude), float(d.longitude)))
            hedef_d = min(duraklar_y,
                          key=lambda d: mesafe_hesapla_km(istek.hedef_lat, istek.hedef_lng, float(d.latitude),
                                                          float(d.longitude)))
            baslangic_sira = int(baslangic_d.sira_no)
            hedef_sira = int(hedef_d.sira_no)
            if baslangic_sira <= hedef_sira:
                dogru_yon = y
                en_yakin_baslangic = baslangic_d
                en_kisa_yurume = mesafe_hesapla_km(istek.baslangic_lat, istek.baslangic_lng,
                                                   float(baslangic_d.latitude), float(baslangic_d.longitude))
                break
    except Exception:
        pass

    if not dogru_yon or not en_yakin_baslangic:
        return {"hata": "Seçtiğiniz rotaya uygun bu hatta bir güzergah bulunamadı."}

    return {
        "mesaj": "Evrensel durak ve yön başarıyla hesaplandı!",
        "durak_id": en_yakin_baslangic.id,
        "durak_adi": en_yakin_baslangic.durak_adi,
        "durak_lat": float(en_yakin_baslangic.latitude),
        "durak_lon": float(en_yakin_baslangic.longitude),
        "hesaplanan_yon": dogru_yon,
        "yurume_mesafesi_km": round(en_kisa_yurume, 2)
    }


# =====================================================================
# 🔤 METİN/KOORDİNAT TEMİZLEME YARDIMCILARI (TEK VE GÜNCEL SÜRÜM)
# =====================================================================

_MOJIBAKE_ESLESTIRME = [
    ("Ã‡", "Ç"), ("Ã§", "ç"),
    ("Äž", "Ğ"), ("ÄŸ", "ğ"),
    ("Ä±", "ı"), ("Ä°", "İ"),
    ("Ã–", "Ö"), ("Ã¶", "ö"),
    ("Åž", "Ş"), ("ÅŸ", "ş"),
    ("Ãœ", "Ü"), ("Ã¼", "ü"),
    ("Ã¢", "â"), ("Ã®", "î"), ("Ã»", "û"),
]


def _mojibake_duzelt(metin: str) -> str:
    """
    routes.csv / trips.csv / stops.csv içindeki isimlerdeki bozuk karakterleri
    düzeltir. Bilinen bozuk-karakter KALIPLARINI tek tek değiştirir (encode/decode
    DEĞİL) — böylece bir karakter kaynakta zaten hasarlıysa bile diğerleri etkilenmez.
    """
    if not metin:
        return metin
    for bozuk, dogru in _MOJIBAKE_ESLESTIRME:
        metin = metin.replace(bozuk, dogru)
    # 🩹 Partneri kaynak veride ZATEN KAYBOLMUŞ, tek başına "yetim" kalmış "Ä"
    # karakterleri için en olası aday "Ğ" (Türkçe'de en sık rastlanan durum).
    metin = metin.replace("Ä", "Ğ")
    return metin


def _koordinat_duzelt(ham):
    """
    stops.csv'deki '410.191.700.005.564' tipi bozulmuş sayıları gerçek
    koordinata çevirir: tüm noktaları atıp rakamları birleştiriyoruz, ilk 2
    rakam tam kısım (41 ya da 28), geri kalanı ondalık kısım oluyor.
    """
    if not ham:
        return None
    s = str(ham).strip().replace(",", ".")
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 3:
        return None
    tam = digits[:2]
    ondalik = digits[2:]
    try:
        return float(f"{tam}.{ondalik}")
    except ValueError:
        return None


def _ayrac_tespit_et(dosya_yolu: str) -> str:
    """CSV'nin ',' mi ';' mi ile ayrıldığını ilk satıra bakarak otomatik tespit eder."""
    with open(dosya_yolu, encoding="utf-8-sig") as f:
        ilk_satir = f.readline()
    return ";" if ilk_satir.count(";") > ilk_satir.count(",") else ","


def _route_kodu_parcala(route_code: str):
    """route_code formatı: "{hat_kodu}_{yon_harfi}_{varyant}" örn "401_D_D0" """
    parcalar = (route_code or "").split("_")
    if len(parcalar) < 3:
        return None, None
    return parcalar[1], parcalar[2]


# =====================================================================
# 🚌 TEK HAT AKTARIMI (GTFS)
# =====================================================================
@app.get("/api/admin/gtfs-aktar/{hat_kodu}")
def gtfs_aktar(hat_kodu: str, db: Session = Depends(get_db)):
    try:
        yol = lambda dosya: os.path.join(GTFS_KLASORU, dosya)
        hat_kodu = hat_kodu.strip()

        routes_satirlar = []
        with open(yol("routes.csv"), encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=_ayrac_tespit_et(yol("routes.csv"))):
                if satir.get("route_short_name", "").strip() == hat_kodu:
                    routes_satirlar.append(satir)

        if not routes_satirlar:
            return {"hata": f"routes.csv içinde '{hat_kodu}' kodlu hat bulunamadı."}

        adaylar = {"D": [], "G": []}
        for r in routes_satirlar:
            yon_harfi, varyant = _route_kodu_parcala(r.get("route_code", ""))
            if yon_harfi in ("D", "G"):
                adaylar[yon_harfi].append({
                    "route_id": r["route_id"].strip(),
                    "varyant": varyant,
                    "uzun_isim": _mojibake_duzelt(r.get("route_long_name", "")),
                })

        secilen_route_id = {}
        for yon_harfi in ("D", "G"):
            liste = adaylar[yon_harfi]
            if not liste:
                continue
            ana = [x for x in liste if x["varyant"] == "D0"]
            secilen_route_id[yon_harfi] = ana[0] if ana else liste[0]

        if not secilen_route_id:
            return {"hata": f"'{hat_kodu}' için gidiş/dönüş yönü tespit edilemedi (route_code formatı beklenmedik)."}

        hedef_route_idler = {v["route_id"] for v in secilen_route_id.values()}
        trip_to_route = {}
        trip_headsign = {}
        with open(yol("trips.csv"), encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=_ayrac_tespit_et(yol("trips.csv"))):
                rid = satir.get("route_id", "").strip()
                if rid in hedef_route_idler:
                    tid = satir["trip_id"].strip()
                    trip_to_route[tid] = rid
                    trip_headsign[tid] = _mojibake_duzelt(satir.get("trip_headsign", "").strip())

        if not trip_to_route:
            return {"hata": "trips.csv içinde bu route_id'lere ait sefer bulunamadı."}

        hedef_trip_idler = set(trip_to_route.keys())
        trip_duraklari = {}
        stop_times_yolu = yol("stop_times.csv")
        stop_times_satir_sayisi = 0
        with open(stop_times_yolu, encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=_ayrac_tespit_et(stop_times_yolu)):
                stop_times_satir_sayisi += 1
                tid = satir.get("trip_id", "").strip()
                if tid in hedef_trip_idler:
                    trip_duraklari.setdefault(tid, []).append(
                        (int(satir["stop_sequence"]), satir["stop_id"].strip())
                    )

        if stop_times_satir_sayisi >= 1_048_575 and not trip_duraklari:
            return {
                "hata": (
                    f"stop_times.csv tam olarak {stop_times_satir_sayisi} satır — bu, dosyanın Excel'de "
                    "açılıp kaydedilirken kırpıldığının işareti. Lütfen dosyayı orijinal haliyle kullanın."
                )
            }

        secilen_trip = {}
        for yon_harfi, bilgi in secilen_route_id.items():
            rid = bilgi["route_id"]
            aday_tidler = [t for t, r in trip_to_route.items() if r == rid]
            if not aday_tidler:
                continue
            en_iyi_tid = max(aday_tidler, key=lambda t: len(trip_duraklari.get(t, [])))
            if trip_duraklari.get(en_iyi_tid):
                secilen_trip[yon_harfi] = en_iyi_tid

        if not secilen_trip:
            return {"hata": "Seçilen seferler için stop_times.csv içinde durak kaydı bulunamadı."}

        gereken_stop_idler = set()
        for tid in secilen_trip.values():
            for _, stop_id in trip_duraklari[tid]:
                gereken_stop_idler.add(stop_id)

        stop_bilgisi = {}
        with open(yol("stops.csv"), encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=_ayrac_tespit_et(yol("stops.csv"))):
                sid = satir.get("stop_id", "").strip()
                if sid in gereken_stop_idler:
                    lat = _koordinat_duzelt(satir.get("stop_lat"))
                    lon = _koordinat_duzelt(satir.get("stop_lon"))
                    if lat and lon:
                        stop_bilgisi[sid] = (_mojibake_duzelt(satir.get("stop_name", "").strip()), lat, lon)

        hat = db.query(Hat).filter(Hat.hat_kodu == hat_kodu).first()
        dogru_isim = (secilen_route_id.get("D") or secilen_route_id.get("G"))["uzun_isim"] or hat_kodu
        if not hat:
            hat = Hat(hat_kodu=hat_kodu, hat_adi=dogru_isim)
            db.add(hat)
            db.commit()
            db.refresh(hat)
        else:
            hat.hat_adi = dogru_isim
            db.query(Durak).filter(Durak.hat_id == hat.id).delete()
            db.commit()

        toplam_eklenen = 0
        for yon_harfi, tid in secilen_trip.items():
            yon_etiketi = trip_headsign.get(tid) or secilen_route_id[yon_harfi]["uzun_isim"] or yon_harfi
            sirali = sorted(trip_duraklari[tid], key=lambda x: x[0])
            sira_no = 1
            for _, stop_id in sirali:
                if stop_id not in stop_bilgisi:
                    continue
                ad, lat, lon = stop_bilgisi[stop_id]
                db.add(Durak(
                    hat_id=hat.id, durak_adi=ad, latitude=lat, longitude=lon,
                    sira_no=sira_no, yon=yon_etiketi,
                ))
                sira_no += 1
                toplam_eklenen += 1

        db.commit()

        _guzergah_esle_ve_kaydet(db, hat, secilen_trip, trip_headsign, secilen_route_id)

        return {
            "mesaj": f"'{hat_kodu}' hattı için GERÇEK GTFS verisiyle {toplam_eklenen} durak başarıyla işlendi.",
            "yonler": {yh: trip_headsign.get(tid, yh) for yh, tid in secilen_trip.items()},
        }

    except FileNotFoundError as e:
        return {"hata": f"GTFS dosyası bulunamadı: {e.filename}. '{GTFS_KLASORU}' klasörüne routes.csv, trips.csv, stops.csv, stop_times.csv dosyalarını koyduğunuzdan emin olun."}
    except Exception as e:
        db.rollback()
        return {"hata": str(e)}


# =====================================================================
# 🗺️ RESMİ GÜZERGAH ÇİZGİSİ (İETT Hat Güzergahları GeoJSON'undan)
# Not: page.tsx artık Google DirectionsRenderer kullandığı için bu satırlar
# doğrudan görsel çizim için kullanılmıyor, ama /api/guzergah endpoint'i
# ileride lazım olursa diye (yedek plan) tutuluyor.
# =====================================================================
def _geojson_guzergah_bul(hat_kodu: str, yon_harfi: str):
    if not os.path.exists(GEOJSON_DOSYA):
        print(f"UYARI: {GEOJSON_DOSYA} bulunamadı, güzergah çizgisi atlanıyor.")
        return None

    olasi_ana_kodlar = {f"{hat_kodu}_{yon_harfi}_D0", f"{hat_kodu}_{yon_harfi}_G0"}
    en_iyi = None
    en_iyi_nokta_sayisi = -1

    with open(GEOJSON_DOSYA, "rb") as f:
        for feature in ijson.items(f, "features.item", use_float=True):
            p = feature.get("properties", {})
            if p.get("HAT_KODU", "").strip() != hat_kodu:
                continue
            kod = p.get("GUZERGAH_KODU", "")
            parcalar = kod.split("_")
            if len(parcalar) < 2 or parcalar[1] != yon_harfi:
                continue

            geom = feature.get("geometry", {})
            koordinatlar = geom.get("coordinates", [])
            if geom.get("type") != "LineString" or len(koordinatlar) < 2:
                continue

            if kod in olasi_ana_kodlar:
                return [(nokta[1], nokta[0]) for nokta in koordinatlar]

            if len(koordinatlar) > en_iyi_nokta_sayisi:
                en_iyi_nokta_sayisi = len(koordinatlar)
                en_iyi = koordinatlar

    if en_iyi:
        return [(nokta[1], nokta[0]) for nokta in en_iyi]
    return None


def _guzergah_esle_ve_kaydet(db, hat, secilen_trip, trip_headsign, secilen_route_id):
    db.query(Guzergah).filter(Guzergah.hat_id == hat.id).delete()
    db.commit()

    for yon_harfi, tid in secilen_trip.items():
        yon_etiketi = trip_headsign.get(tid) or secilen_route_id[yon_harfi]["uzun_isim"] or yon_harfi
        koordinatlar = _geojson_guzergah_bul(hat.hat_kodu, yon_harfi)

        if not koordinatlar:
            print(f"UYARI: '{hat.hat_kodu}' hattı '{yon_harfi}' yönü için resmi güzergah bulunamadı.")
            continue

        for i, (lat, lon) in enumerate(koordinatlar):
            db.add(Guzergah(hat_id=hat.id, yon=yon_etiketi, sira_no=i, latitude=lat, longitude=lon))

    db.commit()


@app.get("/api/guzergah/{hat_id}/{yon}")
def guzergah_getir(hat_id: int, yon: str, db: Session = Depends(get_db)):
    noktalar = (
        db.query(Guzergah)
        .filter(Guzergah.hat_id == hat_id, Guzergah.yon == yon)
        .order_by(Guzergah.sira_no)
        .all()
    )
    return [{"lat": float(n.latitude), "lng": float(n.longitude)} for n in noktalar]


# =====================================================================
# 🚌 TÜM HATLARI TOPLU AKTARMA
# =====================================================================
def _tum_hat_kodlarini_bul():
    routes_yolu = os.path.join(GTFS_KLASORU, "routes.csv")
    delim = _ayrac_tespit_et(routes_yolu)
    hat_kodlari = set()
    with open(routes_yolu, encoding="utf-8-sig") as f:
        for satir in csv.DictReader(f, delimiter=delim):
            kod = satir.get("route_short_name", "").strip()
            if kod:
                hat_kodlari.add(kod)
    return sorted(hat_kodlari)


@app.get("/api/admin/tum-hatlari-listele")
def tum_hatlari_listele():
    kodlar = _tum_hat_kodlarini_bul()
    return {"toplam_hat_sayisi": len(kodlar), "hatlar": kodlar}


@app.get("/api/admin/tum-hatlari-aktar")
def tum_hatlari_aktar(baslangic: int = 0, adet: int = 50, db: Session = Depends(get_db)):
    tum_kodlar = _tum_hat_kodlarini_bul()
    islenecekler = tum_kodlar[baslangic: baslangic + adet]

    if not islenecekler:
        return {
            "mesaj": "İşlenecek hat kalmadı (liste sonuna gelindi, hepsi tamamlanmış olabilir).",
            "toplam_hat_sayisi": len(tum_kodlar),
        }

    islenecekler_set = set(islenecekler)

    try:
        routes_yolu = os.path.join(GTFS_KLASORU, "routes.csv")
        delim = _ayrac_tespit_et(routes_yolu)
        hat_route_adaylari = {}
        with open(routes_yolu, encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=delim):
                kod = satir.get("route_short_name", "").strip()
                if kod not in islenecekler_set:
                    continue
                yon_harfi, varyant = _route_kodu_parcala(satir.get("route_code", ""))
                if yon_harfi not in ("D", "G"):
                    continue
                hat_route_adaylari.setdefault(kod, {"D": [], "G": []})
                hat_route_adaylari[kod][yon_harfi].append({
                    "route_id": satir["route_id"].strip(),
                    "varyant": varyant,
                    "uzun_isim": _mojibake_duzelt(satir.get("route_long_name", "")),
                })

        hat_secilen_route = {}
        for kod, yonler in hat_route_adaylari.items():
            secim = {}
            for yon_harfi in ("D", "G"):
                liste = yonler[yon_harfi]
                if not liste:
                    continue
                ana = [x for x in liste if x["varyant"] == "D0"]
                secim[yon_harfi] = ana[0] if ana else liste[0]
            if secim:
                hat_secilen_route[kod] = secim

        hedef_route_idler = {v["route_id"] for secim in hat_secilen_route.values() for v in secim.values()}

        trips_yolu = os.path.join(GTFS_KLASORU, "trips.csv")
        delim = _ayrac_tespit_et(trips_yolu)
        trip_to_route = {}
        trip_headsign = {}
        with open(trips_yolu, encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=delim):
                rid = satir.get("route_id", "").strip()
                if rid in hedef_route_idler:
                    tid = satir["trip_id"].strip()
                    trip_to_route[tid] = rid
                    trip_headsign[tid] = _mojibake_duzelt(satir.get("trip_headsign", "").strip())

        hedef_trip_idler = set(trip_to_route.keys())
        trip_duraklari = {}
        stop_times_yolu = os.path.join(GTFS_KLASORU, "stop_times.csv")
        delim = _ayrac_tespit_et(stop_times_yolu)
        with open(stop_times_yolu, encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=delim):
                tid = satir.get("trip_id", "").strip()
                if tid in hedef_trip_idler:
                    trip_duraklari.setdefault(tid, []).append(
                        (int(satir["stop_sequence"]), satir["stop_id"].strip())
                    )

        hat_secilen_trip = {}
        for kod, secim in hat_secilen_route.items():
            secilen_trip = {}
            for yon_harfi, bilgi in secim.items():
                rid = bilgi["route_id"]
                aday_tidler = [t for t, r in trip_to_route.items() if r == rid]
                if not aday_tidler:
                    continue
                en_iyi_tid = max(aday_tidler, key=lambda t: len(trip_duraklari.get(t, [])))
                if trip_duraklari.get(en_iyi_tid):
                    secilen_trip[yon_harfi] = en_iyi_tid
            if secilen_trip:
                hat_secilen_trip[kod] = secilen_trip

        gereken_stop_idler = set()
        for secilen_trip in hat_secilen_trip.values():
            for tid in secilen_trip.values():
                for _, sid in trip_duraklari[tid]:
                    gereken_stop_idler.add(sid)

        stops_yolu = os.path.join(GTFS_KLASORU, "stops.csv")
        delim = _ayrac_tespit_et(stops_yolu)
        stop_bilgisi = {}
        with open(stops_yolu, encoding="utf-8-sig") as f:
            for satir in csv.DictReader(f, delimiter=delim):
                sid = satir.get("stop_id", "").strip()
                if sid in gereken_stop_idler:
                    lat = _koordinat_duzelt(satir.get("stop_lat"))
                    lon = _koordinat_duzelt(satir.get("stop_lon"))
                    if lat and lon:
                        stop_bilgisi[sid] = (_mojibake_duzelt(satir.get("stop_name", "").strip()), lat, lon)

        basarili = []
        basarisiz = []

        for kod in islenecekler:
            secilen_trip = hat_secilen_trip.get(kod)
            if not secilen_trip:
                basarisiz.append(kod)
                continue
            try:
                hat = db.query(Hat).filter(Hat.hat_kodu == kod).first()
                dogru_isim = (hat_secilen_route[kod].get("D") or hat_secilen_route[kod].get("G"))["uzun_isim"] or kod
                if not hat:
                    hat = Hat(hat_kodu=kod, hat_adi=dogru_isim)
                    db.add(hat)
                    db.commit()
                    db.refresh(hat)
                else:
                    hat.hat_adi = dogru_isim
                    db.query(Durak).filter(Durak.hat_id == hat.id).delete()
                    db.commit()

                toplam_eklenen = 0
                for yon_harfi, tid in secilen_trip.items():
                    yon_etiketi = (
                            trip_headsign.get(tid)
                            or hat_secilen_route[kod][yon_harfi]["uzun_isim"]
                            or yon_harfi
                    )
                    sirali = sorted(trip_duraklari[tid], key=lambda x: x[0])
                    sira_no = 1
                    for _, sid in sirali:
                        if sid not in stop_bilgisi:
                            continue
                        ad, lat, lon = stop_bilgisi[sid]
                        db.add(Durak(
                            hat_id=hat.id, durak_adi=ad, latitude=lat, longitude=lon,
                            sira_no=sira_no, yon=yon_etiketi,
                        ))
                        sira_no += 1
                        toplam_eklenen += 1
                db.commit()

                if toplam_eklenen > 0:
                    basarili.append({"hat_kodu": kod, "durak_sayisi": toplam_eklenen})
                else:
                    basarisiz.append(kod)
            except Exception as e:
                db.rollback()
                basarisiz.append(kod)
                print(f"'{kod}' aktarılırken hata: {e}")

        sonraki = baslangic + adet
        return {
            "mesaj": f"{len(basarili)} hat başarıyla işlendi, {len(basarisiz)} hat işlenemedi.",
            "toplam_hat_sayisi": len(tum_kodlar),
            "bu_turda_islenen_araligi": f"{baslangic}-{baslangic + len(islenecekler)}",
            "sonraki_baslangic": sonraki if sonraki < len(tum_kodlar) else None,
            "basarili_hatlar": basarili,
            "basarisiz_hatlar": basarisiz,
        }

    except FileNotFoundError as e:
        return {"hata": f"GTFS dosyası bulunamadı: {e.filename}."}
    except Exception as e:
        db.rollback()
        return {"hata": str(e)}
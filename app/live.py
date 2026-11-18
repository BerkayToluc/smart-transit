"""İETT canlı araç verisi ve durak bazlı varış tahmini (ETA)."""
import json
import math
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests
from cachetools import cached, TTLCache
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import Durak, get_db
from app.utils import mesafe_hesapla_km

router = APIRouter()

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


@router.get("/api/canli-otobus/{hat_kodu}")
def canli_otobus_getir(hat_kodu: str):
    otobusler = iett_verisi_cek(hat_kodu)
    if not otobusler:
        return {"mesaj": "Aktif araç bulunamadı", "araclar": []}
    return {"mesaj": f"{hat_kodu} hattında {len(otobusler)} araç bulundu", "araclar": otobusler}


@router.get("/api/moovit/{hat_kodu}/{durak_id}/{hedef_yon}")
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

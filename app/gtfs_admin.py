"""GTFS aktarımı (yönetici uç noktaları) ve metin/koordinat temizleme yardımcıları."""
import csv
import os

import ijson  # pip install ijson
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import Durak, Guzergah, Hat, get_db

router = APIRouter()

GTFS_KLASORU = "./gtfs_data"  # çalışma dizinine göre göreceli yol
GEOJSON_DOSYA = os.path.join(GTFS_KLASORU, "iett-hat-guzergahlari.geojson")


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
@router.get("/api/admin/gtfs-aktar/{hat_kodu}")
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


@router.get("/api/admin/tum-hatlari-listele")
def tum_hatlari_listele():
    kodlar = _tum_hat_kodlarini_bul()
    return {"toplam_hat_sayisi": len(kodlar), "hatlar": kodlar}


@router.get("/api/admin/tum-hatlari-aktar")
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

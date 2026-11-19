"""Aktarma noktaları (#11): yürüme kenarları, istasyon kümeleri, elle süreler.

Sentetik duraklarla çalışır; her test başında tüm gtfs_* kayıtları silinir (tablolar testler arasında paylaşılır).
"""
import math

import pytest
from sqlalchemy import func, select

from app.gtfs import loader, transfers
from app.gtfs.models import (
    GtfsFeed, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTransfer, GtfsTrip,
)

LAT0, LON0 = 41.0, 29.0


def yer(kuzey_m=0.0, dogu_m=0.0):
    """Başlangıç noktasından (kuzey, doğu) metre kadar uzaktaki (lat, lon)."""
    return LAT0 + kuzey_m / 111_195.0, LON0 + dogu_m / (111_195.0 * math.cos(math.radians(LAT0)))


@pytest.fixture(autouse=True)
def temiz(oturum):
    def sil():
        oturum.rollback()
        for f in oturum.scalars(select(GtfsFeed.id)).all():
            loader._beslemeyi_sil(oturum, f)
        oturum.commit()
    sil()
    yield
    sil()


def kur(oturum, besleme, durak_id, ad, mod, kuzey=0.0, dogu=0.0, sefer=True):
    """Bir besleme + durak (+ varsa o modda bir hat ve sefer) ekler."""
    if oturum.get(GtfsFeed, besleme) is None:
        oturum.add(GtfsFeed(id=besleme, name=besleme))
        oturum.flush()
    lat, lon = yer(kuzey, dogu)
    sid = f"{besleme}:{durak_id}"
    oturum.add(GtfsStop(id=sid, feed_id=besleme, name=ad, lat=lat, lon=lon, location_type=0))
    oturum.flush()
    if sefer:
        rid = f"{besleme}:r_{mod}"
        if oturum.get(GtfsRoute, rid) is None:
            oturum.add(GtfsRoute(id=rid, feed_id=besleme, short_name=mod.upper(), mode=mod))
            oturum.flush()
        tid = f"{besleme}:t_{durak_id}"
        oturum.add(GtfsTrip(id=tid, feed_id=besleme, route_id=rid, service_id="s"))
        oturum.flush()
        oturum.add(GtfsStopTime(trip_id=tid, stop_sequence=1, stop_id=sid, arrival_secs=3600, departure_secs=3600))
    oturum.commit()
    return sid


BOS = {"sureler": [], "bilinen_noktalar": []}


def kenar(oturum, a, b):
    return oturum.scalars(select(GtfsTransfer).where(GtfsTransfer.from_stop_id == a, GtfsTransfer.to_stop_id == b)).first()


def test_yurume_suresi_formulu():
    assert transfers.yurume_suresi_sn(100) == 98            # 100 × 1.3 / 1.3333 = 97.5
    assert transfers.yurume_suresi_sn(150) == 147           # 146.25
    assert transfers.yurume_suresi_sn(0) == 0
    assert abs(transfers.mesafe_m(*yer(0, 0), *yer(100, 0)) - 100) < 0.5


def test_yakin_duraklar_iki_yonlu_kenar_alir_uzaklar_almaz(oturum):
    a = kur(oturum, "x", "a", "Durak A", "bus", 0, 0)
    b = kur(oturum, "y", "b", "Durak B", "bus", 100, 0)
    c = kur(oturum, "y", "c", "Durak C", "bus", 400, 0)
    d = kur(oturum, "y", "d", "Durak D", "bus", 0, 200)     # 200 m > 150
    ozet = transfers.uret(oturum, tanim=BOS)
    for x, y in ((a, b), (b, a)):
        k = kenar(oturum, x, y)
        assert k is not None and k.source == "auto" and k.transfer_type == 2 and k.feed_id is None
        assert k.min_transfer_secs == 98
    assert kenar(oturum, a, c) is None and kenar(oturum, a, d) is None
    assert ozet["kenar"] == 2 and ozet["kume"] == 0                           # otobüs durakları kümelenmez
    assert ozet["beslemeler_arasi_kenar"] == {"x-y": 2}


def test_ayni_besleme_otobus_duraklari_da_kenar_alir(oturum):
    a = kur(oturum, "x", "a", "Karşı Yön 1", "bus", 0, 0)
    b = kur(oturum, "x", "b", "Karşı Yön 2", "bus", 60, 0)
    transfers.uret(oturum, tanim=BOS)
    assert kenar(oturum, a, b) is not None and kenar(oturum, b, a) is not None


def test_ayni_isim_farkli_yer_birlesmez(oturum):
    kur(oturum, "x", "m", "Taksim", "metro", 0, 0)
    kur(oturum, "y", "t", "Taksim", "tram", 3000, 0)        # aynı ad, 3 km ötede
    ozet = transfers.uret(oturum, tanim=BOS)
    assert ozet["kume"] == 0 and ozet["kenar"] == 0
    assert oturum.scalars(select(GtfsStop).where(GtfsStop.parent_station.is_not(None))).first() is None


def test_farkli_isim_ayni_yer_birlesir(oturum):
    # isim hiçbir zaman neden değil, mesafe yeterli: farklı adlı iki iskele/istasyon aynı yerdeyse küme olur
    m = kur(oturum, "x", "m", "Yenikapı M1", "metro", 0, 0)
    r = kur(oturum, "y", "r", "Yenikapı Marmaray", "rail", 50, 0)
    transfers.uret(oturum, tanim=BOS)
    assert oturum.get(GtfsStop, m).parent_station == oturum.get(GtfsStop, r).parent_station is not None


def test_istasyon_kumesi_ust_durak_ve_uyeler(oturum):
    m = kur(oturum, "metro", "m", "Kadıköy", "metro", 0, 0)
    t = kur(oturum, "tram", "t", "Kadıköy Tramvay", "tram", 40, 30)
    f = kur(oturum, "vapur", "f", "Kadıköy", "ferry", 70, -20)
    o = kur(oturum, "iett", "o", "Kadıköy İskele", "bus", 90, 0)
    ozet = transfers.uret(oturum, tanim=BOS)
    assert ozet["kume"] == 1
    ust = oturum.scalars(select(GtfsStop).where(GtfsStop.location_type == 1)).one()
    assert ust.feed_id == "kume" and ust.id.startswith("kume:") and ust.name == "Kadıköy"
    for s in (m, t, f):
        assert oturum.get(GtfsStop, s).parent_station == ust.id
    assert oturum.get(GtfsStop, o).parent_station is None                       # otobüs kümelenmez...
    assert kenar(oturum, o, m) is not None                                      # ...ama yürüme kenarı alır
    assert ozet["kumeler"][ust.id]["modlar"] == ["ferry", "metro", "tram"]
    # küme içi aktarma en az 120 sn (kısa yürüme mesafesi olsa bile)
    k = kenar(oturum, m, t)
    assert k.min_transfer_secs == max(120, transfers.yurume_suresi_sn(50))
    assert ozet["kume_ici_kenar"] == 6                                          # 3 üye, her iki yön


def test_elle_tanimli_istasyon_ici_sure(oturum):
    a = kur(oturum, "metro", "m", "Yenikapı", "metro", 0, 0)
    b = kur(oturum, "rail", "r", "Yenikapı", "rail", 60, 0)
    c = kur(oturum, "iett", "o", "Otobüs", "bus", 100, 0)
    lat, lon = yer(30, 0)
    tanim = {"sureler": [{"ad": "Yenikapı", "enlem": lat, "boylam": lon, "yaricap_m": 300, "sure_dk": 8}],
             "bilinen_noktalar": []}
    ozet = transfers.uret(oturum, tanim=tanim)
    assert kenar(oturum, a, b).min_transfer_secs == 480 and kenar(oturum, b, a).min_transfer_secs == 480
    assert kenar(oturum, a, c).min_transfer_secs == transfers.yurume_suresi_sn(100)     # küme dışı: yalnız yürüme
    assert ozet["elle_sureli_kenar"] == 2


def test_kume_boyutu_sinirli_zincirleme_birlesme_olmaz(oturum):
    ids = [kur(oturum, "x", f"s{i}", f"Durak {i}", "metro", 110 * i, 0) for i in range(8)]   # 770 m'lik zincir
    ozet = transfers.uret(oturum, tanim=BOS)
    assert ozet["kume"] >= 2
    gruplar = {}
    for s in oturum.scalars(select(GtfsStop).where(GtfsStop.id.in_(ids))).all():
        if s.parent_station:
            gruplar.setdefault(s.parent_station, []).append(s)
    for uyeler in gruplar.values():
        assert max(transfers.mesafe_m(a.lat, a.lon, b.lat, b.lon) for a in uyeler for b in uyeler) <= 300 + 1e-6


def test_uretim_idempotent_ve_yeniden_yukleme_guvenli(oturum):
    a = kur(oturum, "x", "a", "A", "metro", 0, 0)
    b = kur(oturum, "y", "b", "B", "tram", 50, 0)
    ilk = transfers.uret(oturum, tanim=BOS)
    ikinci = transfers.uret(oturum, tanim=BOS)
    assert ilk["kenar"] == ikinci["kenar"] == 2 and ilk["kume"] == ikinci["kume"] == 1
    assert oturum.scalar(select(func.count()).select_from(GtfsTransfer)) == 2
    assert oturum.scalar(select(func.count()).select_from(GtfsStop).where(GtfsStop.location_type == 1)) == 1
    # y beslemesi yeniden yüklenirken (durak + aktarma silme) yabancı anahtar hatası olmamalı
    loader._beslemeyi_sil(oturum, "y")
    oturum.commit()
    assert oturum.scalar(select(func.count()).select_from(GtfsTransfer)) == 0
    assert oturum.get(GtfsStop, b) is None and oturum.get(GtfsStop, a) is not None
    transfers.uret(oturum, tanim=BOS)                                            # yeniden üretim: kenar yok, küme yok
    assert oturum.get(GtfsStop, a).parent_station is None


def test_nokta_raporu(oturum):
    kur(oturum, "metro", "m", "Taksim", "metro", 0, 0)
    kur(oturum, "fun", "f", "Taksim", "funicular", 80, 0)
    kur(oturum, "iett", "o", "Otobüs", "bus", 20, 0)
    lat, lon = yer(40, 0)
    tanim = {"sureler": [], "bilinen_noktalar": [
        {"ad": "Taksim", "enlem": lat, "boylam": lon, "yaricap_m": 300, "beklenen_modlar": ["metro", "funicular"]},
        {"ad": "Eksik", "enlem": lat, "boylam": lon, "yaricap_m": 300, "beklenen_modlar": ["metro", "ferry"]},
        {"ad": "Yok", "enlem": lat + 0.1, "boylam": lon, "yaricap_m": 300, "beklenen_modlar": ["metro"]}]}
    transfers.uret(oturum, tanim=tanim)
    r = transfers.bilinen_noktalar(oturum, tanim)
    assert r[0]["bulunan_modlar"] == ["funicular", "metro"] and len(r[0]["duraklar"]) == 2   # otobüs istasyon sayılmaz
    assert r[0]["grup"] == 1 and r[0]["kume_sayisi"] == 1
    assert r[2]["duraklar"] == [] and r[2]["grup"] == 0
    metin = transfers.nokta_raporu_metni(r)
    assert "OK Taksim" in metin and "EKSİK MOD: ['ferry']" in metin and "DURAK YOK" in metin


def test_nokta_raporu_bagli_olmayan_duraklari_ayri_grup_sayar(oturum):
    kur(oturum, "metro", "m", "A", "metro", 0, 0)
    kur(oturum, "metro", "n", "B", "metro", 400, 0)          # aynı besleme, 400 m: kenar yok
    lat, lon = yer(200, 0)
    tanim = {"sureler": [], "bilinen_noktalar": [{"ad": "N", "enlem": lat, "boylam": lon, "yaricap_m": 400,
                                                   "beklenen_modlar": ["metro"]}]}
    transfers.uret(oturum, tanim=tanim)
    r = transfers.bilinen_noktalar(oturum, tanim)[0]
    assert r["grup"] == 2 and "OK" not in transfers.nokta_raporu_metni([r])


def test_farkli_beslemelerin_istasyonlari_icin_genis_yaricap(oturum):
    # gerçek ölçüm: Marmaray Üsküdar ile iskele 236 m, Sirkeci-Eminönü 542 m
    r = kur(oturum, "marmaray", "u", "Üsküdar", "rail", 0, 0)
    f = kur(oturum, "vapur", "p", "Üsküdar", "ferry", 236, 0)
    uzak = kur(oturum, "vapur", "e", "Eminönü", "ferry", 542, 0)
    cok_uzak = kur(oturum, "vapur", "z", "Uzak", "ferry", 800, 0)
    ozet = transfers.uret(oturum, tanim=BOS)
    assert kenar(oturum, r, f).min_transfer_secs == transfers.yurume_suresi_sn(236)
    assert kenar(oturum, f, r) is not None and kenar(oturum, r, uzak) is not None
    assert kenar(oturum, r, cok_uzak) is None                                  # 800 m > 600 m
    assert ozet["kume"] == 0                                                   # kümeleme hâlâ yalnız ≤120 m


def test_ayni_besleme_farkli_hatlar_genis_yaricapla_baglanir(oturum):
    # M2 Taksim ↔ F1 Taksim: aynı beslemede (ibb) ama ortak hat yok
    m = kur(oturum, "ibb", "m", "Taksim", "metro", 0, 0)
    f = kur(oturum, "ibb", "f", "Taksim", "funicular", 300, 0)
    ozet = transfers.uret(oturum, tanim=BOS)
    assert kenar(oturum, m, f).min_transfer_secs == transfers.yurume_suresi_sn(300) and kenar(oturum, f, m) is not None
    assert ozet["kume"] == 0


def test_ayni_besleme_ayni_hat_ardisik_duraklar_baglanmaz(oturum):
    # aynı hattın iki durağı (ortak hat var): 300 m ötede olsa da aktarma kenarı olmaz
    a = kur(oturum, "ibb", "a", "A", "metro", 0, 0)
    b = kur(oturum, "ibb", "b", "B", "metro", 300, 0)
    transfers.uret(oturum, tanim=BOS)
    assert kenar(oturum, a, b) is None


def test_genis_yaricap_ayni_besleme_ve_otobus_icin_gecerli_degil(oturum):
    a = kur(oturum, "metro", "a", "A", "metro", 0, 0)
    b = kur(oturum, "metro", "b", "B", "metro", 300, 0)                        # aynı besleme ardışık istasyonlar
    o1 = kur(oturum, "iett", "o1", "O1", "bus", 0, 400)
    o2 = kur(oturum, "other", "o2", "O2", "bus", 300, 400)                     # farklı besleme ama otobüs
    transfers.uret(oturum, tanim=BOS)
    assert kenar(oturum, a, b) is None and kenar(oturum, o1, o2) is None
    assert kenar(oturum, a, o1) is None                                        # otobüs istasyon sayılmaz


def test_genis_yaricap_kapatilabilir(oturum):
    r = kur(oturum, "marmaray", "u", "Üsküdar", "rail", 0, 0)
    f = kur(oturum, "vapur", "p", "Üsküdar", "ferry", 236, 0)
    transfers.uret(oturum, istasyon_yaricap_m=150, tanim=BOS)
    assert kenar(oturum, r, f) is None


def test_tanim_dosyasi_gecerli():
    t = transfers.tanim_oku()
    assert len(t["bilinen_noktalar"]) == 10 and {s["ad"] for s in t["sureler"]} >= {"Yenikapı", "Üsküdar"}
    assert all(s["kaynak"] == "varsayım" for s in t["sureler"])


def test_tanim_hatalari_toplanir(tmp_path):
    import json
    yol = tmp_path / "a.json"
    yol.write_text(json.dumps({"sureler": [{"ad": "X", "enlem": 10, "boylam": 29, "yaricap_m": -1, "sure_dk": 5}]}))
    with pytest.raises(ValueError) as e:
        transfers.tanim_oku(str(yol))
    assert "yaricap_m" in str(e.value) and "İstanbul" in str(e.value)

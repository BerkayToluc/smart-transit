"""Vapur beslemesi (data/vapur.json, Şehir Hatları kış tarifesi): doğrulama, üretim, yükleme.

Sayılar tarife kitapçığından elle sayılmıştır (sayfa 4-9); veri dosyası bozulursa testler yakalar.
"""
import copy
import csv
import os

import pytest
from sqlalchemy import select

from app.gtfs import build, loader, vapur
from app.gtfs.feeds import VAPUR
from app.gtfs.models import GtfsRoute, GtfsStopTime


YOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vapur.json")


@pytest.fixture(scope="module")
def tanim():
    return vapur.tanim_oku(YOL)


def _grup(tanim, hat, hizmet=None, yon=None, ilk=None):
    for g in tanim["seferler"]:
        if g["hat"] == hat and (hizmet is None or g["hizmet"] == hizmet) and (yon is None or g["yon"] == yon) \
                and (ilk is None or g["duraklar"][0] == ilk):
            yield g


def test_dosya_gecerli_ve_kitapcik_bilgileri(tanim):
    assert tanim["besleme"]["veri_tarihi"] == "2026-09-07"
    assert {h["kisa_ad"] for h in tanim["hatlar"]} == {
        "KDK-EMN", "USK-EMN", "KDK-BSK", "KDK-BSK-GECE", "KDK-KBT", "KDK-ORT", "ORT-KDK"}


def _sefer_say(tanim, hat, hizmet=None):
    return sum(len(g["saatler"]) for g in _grup(tanim, hat, hizmet))


def test_kadikoy_karakoy_eminonu_kalkis_sayilari(tanim):
    # Sayfa 4: Kadıköy 53, Karaköy 53, Eminönü 42 kalkış
    ilk = lambda iskele: sum(len(g["saatler"]) for g in _grup(tanim, "kdk_emn") if g["duraklar"][0] == iskele)
    assert ilk("kadikoy") == 53
    assert ilk("eminonu") == 42
    karakoy_kalkis = sum(len(g["saatler"]) for g in _grup(tanim, "kdk_emn") if "karakoy" in g["duraklar"][:-1])
    assert karakoy_kalkis == 53


def test_kadikoy_karakoy_eminonu_dipnotlar_ve_aksam(tanim):
    # '*' hafta içi, '**' pazar/tatil hariç; Karaköy 20:55 *** yolcu almaz
    hafta_ici = [g for g in _grup(tanim, "kdk_emn", "hafta_ici")]
    assert sum(len(g["saatler"]) for g in hafta_ici) == 2              # 06:10*, 06:35*->'*' zincirleri
    pzt_cmt = [g for g in _grup(tanim, "kdk_emn", "pzt_cmt")]
    assert sum(len(g["saatler"]) for g in pzt_cmt) == 4
    yok = [g for g in tanim["seferler"] if g.get("binis_yok")]
    assert len(yok) == 1 and yok[0]["hat"] == "kdk_emn" and yok[0]["binis_yok"] == ["karakoy"]
    assert yok[0]["saatler"] == ["20:30 20:55 21:05"]
    # son kalkış 01:00 -> 25:00 olarak yazılır
    assert any(s.startswith("25:00") for g in _grup(tanim, "kdk_emn", ilk="kadikoy") for s in g["saatler"])


def test_uskudar_karakoy_eminonu_sayilari(tanim):
    ilk = lambda iskele: sum(len(g["saatler"]) for g in _grup(tanim, "usk_emn") if g["duraklar"][0] == iskele)
    assert ilk("uskudar") == 46
    assert ilk("eminonu") == 46
    karakoy = sum(len(g["saatler"]) for g in _grup(tanim, "usk_emn") if "karakoy" in g["duraklar"])
    assert karakoy == 25                                                # sayfa 5: Karaköy sütunu


def test_kadikoy_besiktas_ve_gece(tanim):
    assert sum(len(g["saatler"]) for g in _grup(tanim, "kdk_bsk", yon=0)) == 34
    assert sum(len(g["saatler"]) for g in _grup(tanim, "kdk_bsk", yon=1)) == 34
    gece = list(_grup(tanim, "kdk_bsk_gece"))
    assert all(g["hizmet"] == "gece" for g in gece)
    assert tanim["hizmetler"]["gece"]["gunler"] == [0, 0, 0, 0, 1, 1, 0]   # Cuma ve Cumartesi geceleri
    kdk = sum(len(g["saatler"]) for g in gece if g["duraklar"][0] == "kadikoy")
    bsk = sum(len(g["saatler"]) for g in gece if g["duraklar"][0] == "besiktas")
    assert (kdk, bsk) == (8, 8)
    tum = [s for g in gece for s in g["saatler"]]
    assert "23:45 24:15" in tum and "25:30 26:00" not in tum
    assert any(s.startswith("29:30") or s.startswith("29:") for s in tum)   # 05:30 Beşiktaş kalkışı


def test_kadikoy_kabatas(tanim):
    for hizmet, bekle in (("hafta_ici", 28), ("cumartesi", 26), ("pazar_tatil", 17)):
        for yon in (0, 1):
            assert sum(len(g["saatler"]) for g in _grup(tanim, "kdk_kbt", hizmet, yon)) == bekle, (hizmet, yon)


def test_ortakoy_hatlari_satir_satir(tanim):
    assert _sefer_say(tanim, "kdk_ort", "hafta_ici") == 7 and _sefer_say(tanim, "kdk_ort", "hafta_sonu") == 6
    assert _sefer_say(tanim, "ort_kdk", "hafta_ici") == 7 and _sefer_say(tanim, "ort_kdk", "hafta_sonu") == 6
    # 08:20'de Kadıköy kalkışı yok ("-"): yalnızca Üsküdar-Ortaköy
    assert any(g["duraklar"] == ["uskudar", "ortakoy"] and g["saatler"] == ["08:20 08:30"]
               for g in _grup(tanim, "kdk_ort", "hafta_ici"))
    # Ortaköy-Üsküdar 08:05: Kadıköy varışı yok
    assert any(g["duraklar"] == ["ortakoy", "uskudar"] and g["saatler"] == ["08:05 08:15"]
               for g in _grup(tanim, "ort_kdk", "hafta_ici"))


# --- doğrulama ------------------------------------------------------------------------------
def test_dogrula_hatalari_toplar(tanim):
    t = copy.deepcopy(tanim)
    t["seferler"][0]["saatler"][0] = "06:10"                    # eksik saat
    t["seferler"][1]["hizmet"] = "yok"
    t["seferler"][2]["duraklar"][0] = "bilinmeyen"
    t["iskeleler"][0]["enlem"] = 10.0
    with pytest.raises(ValueError) as e:
        vapur.dogrula(t)
    m = str(e.value)
    assert "saat bekleniyordu" in m and "bilinmeyen hizmet" in m and "bilinmeyen iskele" in m and "enlem" in m


@pytest.mark.parametrize("kotu", ["07:00 06:30", "07:00 07:00", "7:aa 08:00"])
def test_dogrula_saat_sirasi_ve_bicimi(tanim, kotu):
    t = copy.deepcopy(tanim)
    g = t["seferler"][0]
    g["duraklar"] = g["duraklar"][:2]
    g["saatler"] = [kotu]
    with pytest.raises(ValueError):
        vapur.dogrula(t)


def test_dogrula_binis_yok_dizide_olmali(tanim):
    t = copy.deepcopy(tanim)
    t["seferler"][0]["binis_yok"] = ["ortakoy"]
    with pytest.raises(ValueError, match="binis_yok"):
        vapur.dogrula(t)


# --- üretim ve yükleme ----------------------------------------------------------------------
def test_gtfs_uret_ve_yukle(tanim, tmp_path, oturum):
    sayim = vapur.gtfs_uret(tanim, str(tmp_path))
    toplam = sum(len(g["saatler"]) for g in tanim["seferler"])
    assert sayim["trips"] == toplam == 450 and sayim["routes"] == 7
    with open(tmp_path / "routes.csv", encoding="utf-8") as f:
        assert {r["route_type"] for r in csv.DictReader(f)} == {"4"}
    ozet = loader.load_feed(oturum, str(tmp_path), VAPUR)
    assert ozet["trip"] == 450 and ozet["frequency"] == 0
    modlar = {r.mode for r in oturum.scalars(select(GtfsRoute).where(GtfsRoute.feed_id == "vapur"))}
    assert modlar == {"ferry"}
    # gece seferi 24:00'ı aşar
    st = oturum.scalars(select(GtfsStopTime).where(GtfsStopTime.trip_id == "vapur:kdk_bsk_gece_gece_1_besiktas_2930")
                        ).all()
    assert st and max(x.arrival_secs for x in st) == 30 * 3600 + 0
    # Karaköy 20:55 yolcu almaz
    kr = oturum.scalars(select(GtfsStopTime).where(GtfsStopTime.stop_id == "vapur:karakoy",
                                                   GtfsStopTime.pickup_type == 1)).all()
    assert len(kr) == 1 and kr[0].departure_secs == 20 * 3600 + 55 * 60


def test_besleme_kayitli_ve_ibb_vapurlari_yuklenmez():
    assert build.BESLEMELER["vapur"].manuel.endswith("vapur.json") and build.BESLEMELER["vapur"].bicim == "sefer"
    from app.gtfs.feeds import IBB_MULTIMODAL
    assert "ferry" in IBB_MULTIMODAL.exclude_modes


def test_manuel_uret_dosyalari_yazar(tmp_path):
    sayim = build.manuel_uret("vapur", str(tmp_path), log=lambda m: None)
    assert sayim["trips"] == 450 and (tmp_path / "stop_times.csv").exists()

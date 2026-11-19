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
        "KDK-EMN", "USK-EMN", "KDK-BSK", "KDK-BSK-GECE", "KDK-KBT", "KDK-ORT", "ORT-KDK",
        "KBT-ADA", "ADA-BSK", "MLT-ADA", "BST-ADA-RING", "BST-KBT", "BYK-SDF",
        "RMK-EMN", "ORT-BSK-EMN", "KCK-BSK-KBT", "KCK-IST", "USK-ASY", "ASY-AHS-KCK-RING", "AKV-RKV-SRY", "AKV-USK",
        "USK-HLC", "BSK-HLC", "CGK-KZG-BSK-KBT", "KDK-HLC", "CGK-IST-RING", "BEB-EMR", "IST-CUB", "BOGAZ"}


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


# --- Adalar ve Bostancı hatları (kitapçık sayfa 12-18) --------------------------------------
def test_kabatas_adalar_satirlar(tanim):
    # Sayfa 12 (hafta içi + Cumartesi) ve 13 (Pazar/tatil): her tabloda 15 sefer
    for hizmet in ("pzt_cmt", "pazar_tatil"):
        for yon in (0, 1):
            assert sum(len(g["saatler"]) for g in _grup(tanim, "kbt_ada", hizmet, yon)) == 15, (hizmet, yon)
    # 06:45 Kabataş: Kadıköy 07:10, Kınalıada 07:45, Burgazada 08:00, Heybeliada 08:15, Büyükada 08:30, Bostancı 09:05
    g = [g for g in _grup(tanim, "kbt_ada", "pzt_cmt", 0)
         if g["duraklar"] == ["kabatas", "kadikoy", "kinaliada", "burgazada", "heybeliada", "buyukada", "bostanci"]][0]
    assert "06:45 07:10 07:45 08:00 08:15 08:30 09:05" in g["saatler"]
    # 18:50 sefer Eminönü'nden de geçer
    assert any(g["duraklar"][:3] == ["kabatas", "eminonu", "kadikoy"] and "18:50 19:05 19:25 20:00 20:15 20:30 20:45"
               in g["saatler"] for g in _grup(tanim, "kbt_ada", "pzt_cmt", 0))


def test_gece_yarisini_asan_adalar_seferleri(tanim):
    tum = [s for g in _grup(tanim, "kbt_ada", "pzt_cmt", 0) for s in g["saatler"]]
    assert "23:30 23:55 24:30 24:45 25:00 25:15" in tum                 # 23:30 Kabataş, Büyükada 01:15
    ring = [s for g in _grup(tanim, "bst_ring", "pzt_cmt", 1) for s in g["saatler"]]
    assert "24:00 24:35 24:50 25:05 25:20 25:45" in ring                # Bostancı 00:00 ... 01:45


def test_adalar_besiktas_ve_maltepe(tanim):
    assert sum(len(g["saatler"]) for g in _grup(tanim, "ada_bsk")) == 16
    assert sum(len(g["saatler"]) for g in _grup(tanim, "mlt_ada")) == 30
    # Maltepe hattında '*' (Pazar/tatil yapılmaz) olan satırlar pzt_cmt, diğerleri her gün
    assert sum(len(g["saatler"]) for g in _grup(tanim, "mlt_ada", "pzt_cmt")) == 4
    assert sum(len(g["saatler"]) for g in _grup(tanim, "mlt_ada", "her_gun")) == 26


def test_bostanci_hatlari_ve_parantezli_saatler(tanim):
    assert sum(len(g["saatler"]) for g in _grup(tanim, "bst_ring")) == 26
    assert sum(len(g["saatler"]) for g in _grup(tanim, "bst_kbt", "hafta_ici")) == 16
    assert sum(len(g["saatler"]) for g in _grup(tanim, "bst_kbt", "hafta_sonu")) == 8
    # Parantezli satır: Bostancı 18:35 -> Kabataş (19:20) -> Karaköy (19:35); durak sırası zamana göre
    assert any(g["duraklar"] == ["bostanci", "kabatas", "karakoy"] and g["saatler"] == ["18:35 19:20 19:35"]
               for g in _grup(tanim, "bst_kbt", "hafta_ici"))
    # Karaköy önce, Kabataş sonra: 07:50 Karaköy, 08:00 Kabataş, 08:45 Bostancı
    assert any(g["duraklar"] == ["karakoy", "kabatas", "bostanci"] and "07:50 08:00 08:45" in g["saatler"]
               for g in _grup(tanim, "bst_kbt", "hafta_ici"))


def test_buyukada_sedef_adasi(tanim):
    assert sum(len(g["saatler"]) for g in _grup(tanim, "byk_sdf")) == 4
    assert any(g["saatler"] == ["07:55 08:10"] and g["hizmet"] == "pazar_tatil" for g in _grup(tanim, "byk_sdf"))


def test_iskele_koordinatlari_kml_den(tanim):
    isk = {i["id"]: i for i in tanim["iskeleler"]}
    assert abs(isk["buyukada"]["enlem"] - 40.874929) < 1e-5 and abs(isk["kabatas"]["boylam"] - 28.994322) < 1e-5
    assert {"maltepe", "bostanci", "moda", "sedef_adasi"} <= set(isk)


# --- Boğaz, Haliç ve diğer hatlar (kitapçık sayfa 20-37) -------------------------------------
def _say(tanim, hat, hizmet=None, yon=None):
    return sum(len(g["saatler"]) for g in _grup(tanim, hat, hizmet, yon))


def test_rumeli_kavagi_eminonu_ve_ortakoy(tanim):
    assert _say(tanim, "rmk_emn", yon=0) == 12 and _say(tanim, "rmk_emn", yon=1) == 12
    assert any(g["duraklar"] == ["rumeli_kavagi", "sariyer", "buyukdere", "istinye", "emirgan", "bebek", "ortakoy",
                                 "besiktas", "eminonu"] and "07:20 07:30 07:35 08:00 08:05 08:20 08:35 08:45 09:00"
               in g["saatler"] for g in _grup(tanim, "rmk_emn", yon=0))
    # Ortaköy-Beşiktaş-Eminönü: kırmızı '*' seferler yalnızca Cumartesi/Pazar/tatil
    assert _say(tanim, "ort_emn", "her_gun") == 14 and _say(tanim, "ort_emn", "hafta_sonu") == 2
    assert any("17:25 17:35 17:50" in g["saatler"] for g in _grup(tanim, "ort_emn", "hafta_sonu"))


def test_haliç_hatlari_ve_dipnotlar(tanim):
    # Üsküdar-Haliç: 14 + 14 sefer; '*' (Pazar/tatil yok) 6, '**' (yalnız Pazar/tatil) 2
    assert _say(tanim, "usk_halic") == 28
    assert (_say(tanim, "usk_halic", "pzt_cmt"), _say(tanim, "usk_halic", "pazar_tatil")) == (6, 2)
    assert (_say(tanim, "kdk_halic", "pzt_cmt"), _say(tanim, "kdk_halic", "pazar_tatil"), _say(tanim, "kdk_halic")) == (6, 4, 24)
    assert _say(tanim, "bsk_halic") == 14 and _say(tanim, "bsk_halic", "pazar_tatil") == 2
    assert any(g["duraklar"][0] == "eyupsultan" and g["duraklar"][-1] == "uskudar" and "20:45 20:50 20:55 21:00 21:05 21:10 21:15 21:25 21:40" in g["saatler"]
               for g in _grup(tanim, "usk_halic", "pazar_tatil"))


def test_anadolu_kavagi_hatlari(tanim):
    assert _say(tanim, "akv_sry", yon=0) == 16 and _say(tanim, "akv_sry", yon=1) == 15
    assert _say(tanim, "akv_sry", "pzt_cmt") == 1 and _say(tanim, "akv_sry", "pazar_tatil") == 1    # 06:40* ve 06:55**
    assert _say(tanim, "akv_usk", yon=0) == 5 and _say(tanim, "akv_usk", yon=1) == 5
    assert any(g["duraklar"][0] == "uskudar" and g["saatler"][0].startswith("11:35 11:50 12:00") for g in _grup(tanim, "akv_usk", yon=1))


def test_rinler_ve_kucuk_hatlar(tanim):
    assert _say(tanim, "asy_ring") == 37
    # (V) = Anadolu Hisarı'nda biter: Aşiyan 20:00, Küçüksu 20:05, Anadolu Hisarı 20:10
    assert any(g["duraklar"] == ["asiyan", "kucuksu", "anadolu_hisari"] and g["saatler"] == ["20:00 20:05 20:10"]
               for g in _grup(tanim, "asy_ring"))
    assert _say(tanim, "cgk_ist_ring") == 12 and _say(tanim, "cgk_ist_ring", "hafta_ici") == 1
    assert _say(tanim, "beb_emr", "pazar_tatil") == 15 and _say(tanim, "beb_emr") == 15
    assert _say(tanim, "cgk_kbt") == 24 and _say(tanim, "cgk_kbt", "pzt_cmt") == 6


def test_bagimsiz_kalkis_listeleri(tanim):
    # Küçüksu-İstinye: 7 + 7 kalkış (süre 20 dk varsayım); Üsküdar-Aşiyan: 15+15 ve 14+14 (30 dk varsayım)
    assert _say(tanim, "kck_ist", yon=0) == 7 and _say(tanim, "kck_ist", yon=1) == 7
    assert _say(tanim, "usk_asy", "pzt_cmt") == 30 and _say(tanim, "usk_asy", "pazar_tatil") == 28
    assert _say(tanim, "kck_bsk") == 4
    # İstinye-Çubuklu araba vapuru iskeleleri: hafta içi 46+46, Cumartesi 28+28, Pazar 24+24
    assert (_say(tanim, "ist_cub", "hafta_ici"), _say(tanim, "ist_cub", "cumartesi"), _say(tanim, "ist_cub", "pazar_tatil")) == (92, 56, 48)
    assert {"cubuklu_arabali", "istinye_arabali"} <= {i["id"] for i in tanim["iskeleler"]}


def test_bogaz_hatti_iki_sayfalik_matris(tanim):
    # Sayfa 20-21: Boğaza gidiş 12 hafta içi + 2 Cumartesi + 1 Pazar; Boğazdan geliş 12 + 3 + 1 (satır arka plan renginden)
    assert (_say(tanim, "bogaz", "hafta_ici", 0), _say(tanim, "bogaz", "cumartesi", 0), _say(tanim, "bogaz", "pazar_tatil", 0)) == (12, 2, 1)
    assert (_say(tanim, "bogaz", "hafta_ici", 1), _say(tanim, "bogaz", "cumartesi", 1), _say(tanim, "bogaz", "pazar_tatil", 1)) == (12, 3, 1)
    # Eminönü 17:55 -> Beşiktaş -> Ortaköy -> Bebek -> Kandilli -> A.Hisarı -> Kanlıca -> Çubuklu -> Paşabahçe -> Beykoz 19:30
    assert any(g["duraklar"] == ["eminonu", "besiktas", "ortakoy", "bebek", "kandilli", "anadolu_hisari", "kanlica",
                                 "cubuklu", "pasabahce", "beykoz"] and "17:55 18:10 18:20 18:35 18:45 18:50 19:00 19:10 19:15 19:30" in g["saatler"]
               for g in _grup(tanim, "bogaz", "hafta_ici", 0))
    assert all("turu" not in h["uzun_ad"].lower() for h in tanim["hatlar"])      # turistik Boğaz turları yok (s.35)


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
    assert sayim["trips"] == toplam == 1148 and sayim["routes"] == 29
    with open(tmp_path / "routes.csv", encoding="utf-8") as f:
        assert {r["route_type"] for r in csv.DictReader(f)} == {"4"}
    ozet = loader.load_feed(oturum, str(tmp_path), VAPUR)
    assert ozet["trip"] == 1148 and ozet["frequency"] == 0
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
    assert sayim["trips"] == 1148 and (tmp_path / "stop_times.csv").exists()

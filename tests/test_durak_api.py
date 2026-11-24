"""#23: GET /api/stops/{stop_id}/departures"""
from datetime import datetime

import pytest

from app import durak_api
from app.live import _otobus_gecmisi, iett_cache
from app.routing import servis
from tests.conftest import IETT_ARACLARI, IETT_COKUK
from tests.test_routing import Ag, ag, hm, yer  # noqa: F401  (ag: fixture)

PAZARTESI_0800 = datetime(2026, 11, 23, 8, 0, tzinfo=durak_api.TR)


def arac(kapi, kuzey_m, yon):
    lat, lon = yer(kuzey_m, 0)
    return {"kapino": kapi, "enlem": str(lat), "boylam": str(lon), "yon": yon}


@pytest.fixture
def agi(ag, monkeypatch):  # noqa: F811
    """D20 durağı (4000 m): otobüs YK1 (08:30, 09:20, 10:20), YK2, metro M9 (08:30), akşam GEC ve bugünkü seferi bitmiş BITTI."""
    iett_cache.clear()
    _otobus_gecmisi.clear()
    IETT_COKUK["acik"] = False
    monkeypatch.setattr(durak_api, "_simdi", lambda: PAZARTESI_0800)
    for i in range(31):
        ag.durak(f"D{i:02d}", i * 200, 0)
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"08:{10 + i:02d}") for i in range(31)], kimlik="y1", baslik="D30 SON")
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"09:{i:02d}") for i in range(31)], kimlik="y2", baslik="D30 SON")
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"10:{i:02d}") for i in range(31)], kimlik="y3", baslik="D30 SON")
    ag.sefer("YK2", "bus", [(f"D{i:02d}", f"09:{i:02d}") for i in range(20, 26)], kimlik="z1")
    ag.sefer("M9", "metro", [("D20", "08:30"), ("D30", "08:40")], kimlik="m1")
    ag.sefer("GEC", "bus", [("D20", "23:00"), ("D30", "23:20")], kimlik="g1")        # bugün hâlâ kalkacak
    ag.sefer("BITTI", "bus", [("D20", "05:00"), ("D30", "05:20")], kimlik="b1")      # bugünkü seferi bitti: listelenmez
    servis.graf_ayarla(ag.graf())
    yield ag
    servis.graf_ayarla(None)


def al(client, stop="t:D20", **kw):
    return client.get(f"/api/stops/{stop}/departures", params=kw)


def test_planli_kalkislar_siralama_ve_bitmis_hat(client, agi):
    r = al(client)
    assert r.status_code == 200, r.text
    d = r.json()
    hatlar = [x["hat"] for x in d["departures"]]
    assert "BITTI" not in hatlar                                    # bugünkü tüm seferleri geçmiş
    assert d["stop"]["name"] == "D20" and "bus" in d["stop"]["modes"] and "metro" in d["stop"]["modes"]
    yk1 = next(x for x in d["departures"] if x["hat"] == "YK1")
    assert yk1["yon"] == "D30"                                      # yön = hattın son durağı
    # YK1 D20'ye 08:30 (08:10+20), 09:20, 10:20 ... planlı
    assert [t["saat"] for t in yk1["planli"][:3]] == ["08:30", "09:20", "10:20"]
    assert yk1["planli"][0]["dk"] == 30
    # sıralama: en yakın kalkış önde (M9 08:30 ve YK1 08:30 aynı; ad sırası), GEC en sonda
    assert hatlar[-1] == "GEC" and set(hatlar[:2]) == {"M9", "YK1"}


def test_metro_icin_canli_denenmez_otobus_icin_denenir(client, agi):
    IETT_ARACLARI["YK1"] = []
    d = al(client).json()["departures"]
    m9 = next(x for x in d if x["hat"] == "M9")
    yk1 = next(x for x in d if x["hat"] == "YK1")
    assert m9["canli_denendi"] is False and m9["canli"] == []
    assert yk1["canli_denendi"] is True and yk1["canli_erisilemiyor"] is False


def test_canli_arac_dakikasi(client, agi):
    IETT_ARACLARI["YK1"] = [arac("A-1", 3000, "D30 SON"), arac("A-2", 2500, "D30 SON")]   # durağın 1000 m / 1500 m gerisinde
    yk1 = next(x for x in al(client).json()["departures"] if x["hat"] == "YK1")
    assert [a["kapi_no"] for a in yk1["canli"]] == ["A-1", "A-2"]
    assert [a["dakika"] for a in yk1["canli"]] == [2, 4]
    # canlı aracı olan hat, planlıdan önce gelir (2 dk < 30 dk)
    assert al(client).json()["departures"][0]["hat"] == "YK1"


def test_iett_erisilemiyorsa_isaretlenir_planli_kalir(client, agi, monkeypatch):
    from app import live
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    IETT_COKUK["acik"] = True
    d = al(client).json()
    assert d["canli_erisilemiyor"] is True
    yk1 = next(x for x in d["departures"] if x["hat"] == "YK1")
    assert yk1["canli_erisilemiyor"] is True and yk1["canli"] == [] and yk1["planli"]


def test_ayni_istasyonun_diger_duraklari_birlesir(client, ag, monkeypatch):  # noqa: F811
    iett_cache.clear()
    monkeypatch.setattr(durak_api, "_simdi", lambda: PAZARTESI_0800)
    ag.durak("Kabataş", 0, 0)
    ag.durak("KABATAŞ", 80, 0)                     # aynı istasyon, 80 m yan
    ag.durak("Uzak", 5000, 0)
    ag.durak("Başka", 100, 50)                     # farklı ad, yakın: birleşmez
    ag.sefer("F1", "funicular", [("Kabataş", "08:10"), ("Uzak", "08:20")], kimlik="f1")
    ag.sefer("T1", "tram", [("KABATAŞ", "08:15"), ("Uzak", "08:30")], kimlik="t1")
    ag.sefer("X", "bus", [("Başka", "08:12"), ("Uzak", "08:40")], kimlik="x1")
    servis.graf_ayarla(ag.graf())
    d = client.get("/api/stops/t:Kabataş/departures").json()
    assert sorted(x["hat"] for x in d["departures"]) == ["F1", "T1"]
    assert d["stop"]["stop_ids"] == ["t:Kabataş", "t:KABATAŞ"] and set(d["stop"]["modes"]) == {"funicular", "tram"}
    servis.graf_ayarla(None)


def test_son_durak_ve_binilmeyen_dislanir_limit_ve_hatalar(client, agi):
    # D30 yalnızca iniş (son durak): hiçbir hat oradan kalkmaz
    assert al(client, stop="t:D30").json()["departures"] == []
    assert len(al(client, limit=2).json()["departures"]) == 2
    assert al(client, stop="t:YOKTUR").status_code == 404
    assert al(client, limit=0).status_code == 422
    servis.graf_ayarla(None)
    assert al(client).status_code == 503

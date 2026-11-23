"""GET /api/yaklasan: biniş→iniş arası hatlar ve canlı araçların biniş durağına varış tahmini."""
import pytest

from app.live import _otobus_gecmisi, iett_cache
from app.routing import servis
from tests.conftest import IETT_ARACLARI
from tests.test_routing import Ag, ag, hm, yer  # noqa: F401  (ag: fixture)


def arac(kapi, kuzey_m, yon):
    lat, lon = yer(kuzey_m, 0)
    return {"kapino": kapi, "enlem": str(lat), "boylam": str(lon), "yon": yon}


@pytest.fixture
def hat_agi(ag):  # noqa: F811
    """YK1: 31 durak (D00..D30), 200 m arayla kuzeye; D20 (4000 m) biniş, D30 (6000 m) iniş. İkinci hat YK2 yalnızca D20→D25."""
    iett_cache.clear()                     # İETT yanıtı 15 sn önbellekli; testler birbirinin verisini görmesin
    _otobus_gecmisi.clear()
    for i in range(31):
        ag.durak(f"D{i:02d}", i * 200, 0)
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"08:{i:02d}") for i in range(31)], kimlik="y1", baslik="D30 SON")
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"09:{i:02d}") for i in range(31)], kimlik="y2", baslik="D30 SON")
    ag.sefer("YK2", "bus", [(f"D{i:02d}", f"08:{(i - 20) * 2 + 10:02d}") for i in range(20, 26)], kimlik="z1")
    ag.sefer("M9", "metro", [("D20", "08:00"), ("D30", "08:10")], kimlik="m1")           # canlı takip yalnız otobüs
    servis.graf_ayarla(ag.graf())
    yield
    servis.graf_ayarla(None)


def test_hatlar_ve_canli_eta(client, hat_agi):
    IETT_ARACLARI["YK1"] = [
        arac("A-1", 3000, "D30 SON"),      # biniş durağının 1000 m gerisinde: 1 km / 25 km/s = ~2 dk
        arac("A-2", 2500, "D30 SON"),      # 1500 m geride: ~4 dk
        arac("A-3", 4500, "D30 SON"),      # durağı geçmiş: listede yok ama haritada
        arac("A-4", 3000, "D00 ILK"),      # ters yön (ilk duraklara gidiyor): listede yok
    ]
    r = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D30"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["binis"]["name"] == "D20" and d["inis"]["name"] == "D30"
    assert d["hat_adlari"] == ["YK1"]                      # YK2 D30'a gitmiyor, M9 otobüs değil
    h = d["hatlar"][0]
    assert (h["hat"], h["mod"], h["yon"]) == ("YK1", "bus", "D30")
    assert [a["kapi_no"] for a in h["araclar"]] == ["A-1", "A-2"]
    assert [a["dakika"] for a in h["araclar"]] == [2, 4]
    assert h["araclar"][0]["mesafe_km"] == pytest.approx(1.0, abs=0.05)
    assert {a["kapi_no"] for a in h["tum_araclar"]} == {"A-1", "A-2", "A-3", "A-4"}
    assert h["sure_dk"] == 10 and len(h["planli"]) <= 3


def test_hat_filtresi_oncelik_ve_ayni_duraklar(client, hat_agi):
    IETT_ARACLARI["YK1"] = [arac("B-1", 3000, "D30 SON")]
    IETT_ARACLARI["YK2"] = [arac("C-1", 3400, "D25")]
    # D20 -> D25: iki hat da gider; yalnız YK2 istenirse yalnız o gelir
    r = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D25"}).json()
    assert set(r["hat_adlari"]) == {"YK1", "YK2"}
    sadece = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D25", "hatlar": "YK2"}).json()
    assert [h["hat"] for h in sadece["hatlar"]] == ["YK2"]
    # öncelik: rotadaki hat listede başa alınır
    ilk = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D25", "oncelik": "YK2"}).json()
    assert ilk["hat_adlari"][0] == "YK2"


def test_canli_arac_yok_planli_kalkislar(client, hat_agi):
    IETT_ARACLARI["YK1"] = []
    h = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D30"}).json()["hatlar"][0]
    assert h["araclar"] == [] and h["tum_araclar"] == []
    # planlı kalkışlar HH:MM biçiminde (şimdiye göre; en az bir sefer günün ilerisinde olmayabilir)
    assert all(len(x) == 5 and x[2] == ":" for x in h["planli"])


def test_hatalar(client, ag):  # noqa: F811
    servis.graf_ayarla(None)
    assert client.get("/api/yaklasan", params={"bas": "x", "bit": "y"}).status_code == 503
    ag.durak("A", 0, 0)
    ag.durak("B", 500, 0)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:05")], kimlik="a1")
    servis.graf_ayarla(ag.graf())
    try:
        assert client.get("/api/yaklasan", params={"bas": "t:A", "bit": "t:YOK"}).status_code == 404
        assert client.get("/api/yaklasan", params={"bas": "t:A"}).status_code == 422
        assert client.get("/api/yaklasan", params={"bas": "t:B", "bit": "t:A"}).json()["hatlar"] == []   # ters yön hat yok
    finally:
        servis.graf_ayarla(None)


def test_iett_erisilemiyorsa_hat_bunu_isaretler(client, hat_agi, monkeypatch):
    from app import live
    from tests.conftest import IETT_COKUK
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    IETT_COKUK["acik"] = True
    h = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D30"}).json()["hatlar"][0]
    assert h["canli_erisilemiyor"] is True and h["araclar"] == []
    iett_cache.clear()
    IETT_COKUK["acik"] = False
    IETT_ARACLARI["YK1"] = []
    h = client.get("/api/yaklasan", params={"bas": "t:D20", "bit": "t:D30"}).json()["hatlar"][0]
    assert h["canli_erisilemiyor"] is False        # "araç yok" ile "servis yok" ayrı

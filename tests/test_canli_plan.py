"""#22: /api/plan canlı otobüs bilgisi (ilk otobüs bacağı)."""
from datetime import datetime

import pytest
import requests

from app import live, plan_api
from app.live import _otobus_gecmisi, iett_cache
from app.routing import servis
from tests.conftest import IETT_ARACLARI, IETT_COKUK
from tests.test_routing import Ag, ag, hm, yer  # noqa: F401  (ag: fixture)

SIMDI = datetime(2026, 11, 23, 8, 0, tzinfo=plan_api.TR)       # Pazartesi 08:00


def arac(kapi, kuzey_m, yon="D30 SON"):
    lat, lon = yer(kuzey_m, 0)
    return {"kapino": kapi, "enlem": str(lat), "boylam": str(lon), "yon": yon}


def istek(**kw):
    la0, lo0 = yer(4000, 0)          # D20'nin üstünde (durakta)
    la1, lo1 = yer(6000, 0)          # D30
    govde = {"origin": {"lat": la0, "lng": lo0}, "dest": {"lat": la1, "lng": lo1}, "max_results": 3}
    govde.update(kw)
    return govde


@pytest.fixture
def agi(ag, monkeypatch):  # noqa: F811
    """YK1: D20'de 08:02, D30'da 08:12. ALT: D20'de 08:04, D30'da 08:13 (aynı duraklar, ikinci hat)."""
    iett_cache.clear()
    _otobus_gecmisi.clear()
    IETT_COKUK["acik"] = False
    gercek = plan_api._yerel
    monkeypatch.setattr(plan_api, "_yerel", lambda dt: SIMDI if dt is None else gercek(dt))
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    for i in range(31):
        ag.durak(f"D{i:02d}", i * 200, 0)
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"{7:02d}:{42 + i:02d}") for i in range(31)], kimlik="y1", baslik="D30 SON")
    ag.sefer("YK1", "bus", [(f"D{i:02d}", f"08:{12 + i:02d}") for i in range(31)], kimlik="y2", baslik="D30 SON")   # D20'de 08:32
    ag.sefer("ALT", "bus", [("D20", "08:04"), ("D30", "08:13")], kimlik="a1")
    servis.graf_ayarla(ag.graf())
    plan_api._plan_onbellek.clear()
    yield ag
    servis.graf_ayarla(None)
    plan_api._plan_onbellek.clear()


def plan(client, **kw):
    r = client.post("/api/plan", json=istek(**kw))
    assert r.status_code == 200, r.text
    return r.json()["itineraries"]


def yolculuk_hat(y):
    return next(e["route_short_name"] for e in y["legs"] if e["type"] == "transit")


def test_canli_arac_bekleme_ve_gecikme(client, agi):
    IETT_ARACLARI["YK1"] = [arac("A-1", 500, "D30 SON")]           # durağın 3,5 km gerisinde: ~8 dk
    y = next(x for x in plan(client) if yolculuk_hat(x) == "YK1")
    l = y["live"]
    assert l["source"] == "canli" and l["route"] == "YK1" and l["gate"] == "A-1"
    assert l["arrives_in_min"] == 8 and l["wait_min"] == 8          # durakta 0 dk yürüme: bekleme = geliş süresi
    assert l["delay_min"] == 6                                      # 08:08 canlı - 08:02 tarife
    assert y["adjusted_arrival_time"].startswith("2026-11-23T08:18")  # 08:12 + 6 dk


def test_zamaninda_arac_gecikme_yok_guncel_varis_yok(client, agi):
    IETT_ARACLARI["YK1"] = [arac("A-1", 3000, "D30 SON")]          # 1 km: ~2 dk -> 08:02 = tarife
    y = next(x for x in plan(client) if yolculuk_hat(x) == "YK1")
    assert y["live"]["source"] == "canli" and y["live"]["delay_min"] == 0
    assert "adjusted_arrival_time" not in y


def test_arac_yok_tarifeye_doner(client, agi):
    IETT_ARACLARI["YK1"] = []
    y = next(x for x in plan(client) if yolculuk_hat(x) == "YK1")
    assert y["live"]["source"] == "tarife" and y["live"]["no_vehicle"] is True and y["live"]["service_down"] is False


def test_iett_erisilemiyor_tarife_ve_servis_yok_bayragi(client, agi):
    IETT_COKUK["acik"] = True
    y = next(x for x in plan(client) if yolculuk_hat(x) == "YK1")
    assert y["live"]["source"] == "tarife" and y["live"]["service_down"] is True


def test_yetisilemeyen_arac_atlanir(client, agi):
    # Kullanıcı durağa ~5 dk yürüyerek varır (300 m doğuda); 2 dk'da gelecek araç yakalanamaz, 8 dk'daki araç seçilir ve bekleme
    # durağa varıştan sayılır (8 - ~5 = ~3 dk).
    la, lo = yer(4000, 300)
    IETT_ARACLARI["YK1"] = [arac("A-1", 3000, "D30 SON"), arac("A-2", 500, "D30 SON")]
    y = next(x for x in plan(client, origin={"lat": la, "lng": lo}) if yolculuk_hat(x) == "YK1")
    l = y["live"]
    assert l["source"] == "canli" and l["gate"] == "A-2" and l["arrives_in_min"] in (8, 9)
    assert 2 <= l["wait_min"] <= 5
    assert [v["gate"] for v in l["vehicles"]][:2] == ["A-1", "A-2"]       # yetişilemeyen araç da listede görünür


def test_daha_iyi_alternatif_uyarisi(client, agi):
    IETT_ARACLARI["YK1"] = [arac("A-1", 500, "D30 SON")]           # YK1 +6 dk gecikmeli (08:18); ALT tarifeyle 08:13
    ys = plan(client)
    yk1 = next(i for i, x in enumerate(ys) if yolculuk_hat(x) == "YK1")
    alt = next(i for i, x in enumerate(ys) if yolculuk_hat(x) == "ALT")
    l = ys[yk1]["live"]
    assert l["better_option"] == alt and l["better_gain_min"] == 5
    assert "better_option" not in ys[alt].get("live", {})


def test_sirala_degismez_canli_olmadan_ayni_sira(client, agi):
    IETT_ARACLARI["YK1"] = [arac("A-1", 500, "D30 SON")]
    canli = [yolculuk_hat(x) for x in plan(client)]
    IETT_COKUK["acik"] = True
    iett_cache.clear()
    assert [yolculuk_hat(x) for x in plan(client)] == canli          # canlı gecikme sıralamayı değiştirmez (zıplama yok)


def test_planli_zamanli_sorguda_canli_yok(client, agi):
    IETT_ARACLARI["YK1"] = [arac("A-1", 500, "D30 SON")]
    ys = plan(client, depart_at="2026-11-23T08:00:00+03:00")
    assert all("live" not in y for y in ys)


def test_ilk_bacak_metro_ise_canli_yok(client, ag, monkeypatch):  # noqa: F811
    gercek = plan_api._yerel
    monkeypatch.setattr(plan_api, "_yerel", lambda dt: SIMDI if dt is None else gercek(dt))
    for i in range(31):
        ag.durak(f"D{i:02d}", i * 200, 0)
    ag.sefer("M9", "metro", [("D20", "08:05"), ("D30", "08:15")], kimlik="m1")
    servis.graf_ayarla(ag.graf())
    plan_api._plan_onbellek.clear()
    ys = plan(client)
    assert ys and all("live" not in y for y in ys)
    servis.graf_ayarla(None)


def test_iett_hizli_mod_tek_deneme(monkeypatch):
    cagri = []

    def post(*a, **k):
        cagri.append(k.get("timeout"))
        raise requests.ConnectionError("yok")

    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    monkeypatch.setattr(live.requests, "post", post)
    iett_cache.clear()
    assert live.iett_durum("HZ1", hizli=True)["erisilemiyor"] is True
    assert cagri == [live.HIZLI_ZAMAN_ASIMI]                         # tek deneme, kısa zaman aşımı
    iett_cache.clear()
    cagri.clear()
    live.iett_durum("HZ2")
    assert len(cagri) == live.SOAP_DENEME                            # normal mod: yeniden denemeli

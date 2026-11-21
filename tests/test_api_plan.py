"""POST /api/plan ve GET /api/plan/durum: sentetik ağ üzerinde uçtan uca (istek doğrulama, yanıt biçimi, hatalar)."""
import pytest

from app.routing import servis
from tests.test_routing import HAFTA_ICI, Ag, ag, hm, yer  # noqa: F401  (ag: fixture)

PAZARTESI = "2026-11-23"          # 2026-11-23 Pazartesi
CUMARTESI = "2026-11-21"


@pytest.fixture
def ag_kur(ag):  # noqa: F811
    """A --bus(L1)--> B  ~yürüme 300 m~  C --metro(M1)--> D ; hepsi hafta içi."""
    ag.durak("A", 0, 0)
    ag.durak("B", 4000, 0)
    ag.durak("C", 4300, 0)
    ag.durak("D", 9000, 0)
    ag.sefer("L1", "bus", [("A", "08:10"), ("B", "08:30")], hizmet="hi", gunler=HAFTA_ICI, kimlik="a1", baslik="Merkez")
    ag.sefer("M1", "metro", [("C", "08:40"), ("D", "08:55")], hizmet="hi", gunler=HAFTA_ICI, kimlik="m1", baslik="Sonduraq")
    ag.yurume("B", "C", 294)
    g = ag.graf()
    servis.graf_ayarla(g)
    yield g
    servis.graf_ayarla(None)


def istek(**kw):
    la0, lo0 = yer(-100, 0)
    la1, lo1 = yer(9100, 0)
    govde = {"origin": {"lat": la0, "lng": lo0}, "dest": {"lat": la1, "lng": lo1},
             "depart_at": f"{PAZARTESI}T08:00:00+03:00"}
    govde.update(kw)
    return govde


def test_cok_modlu_aktarmali_rota(client, ag_kur):
    r = client.post("/api/plan", json=istek())
    assert r.status_code == 200, r.text
    veri = r.json()
    y = veri["itineraries"][0]
    assert y["transfers"] == 1 and y["departure_time"] == f"{PAZARTESI}T08:00:00+03:00"
    assert y["arrival_time"].startswith(f"{PAZARTESI}T08:5") and y["total_duration"] > 0
    assert [e["type"] for e in y["legs"]] == ["walk", "transit", "walk", "transit", "walk"]
    otobus, metro = y["legs"][1], y["legs"][3]
    assert (otobus["mode"], otobus["route_short_name"], otobus["headsign"], otobus["num_stops"]) == ("bus", "L1", "Merkez", 1)
    assert (metro["mode"], metro["route_short_name"], metro["from"]["name"], metro["to"]["name"]) == ("metro", "M1", "C", "D")
    assert otobus["from"]["time"] == f"{PAZARTESI}T08:10:00+03:00" and metro["to"]["time"] == f"{PAZARTESI}T08:55:00+03:00"
    assert len(otobus["polyline"]) == 2 and all(len(n) == 2 for n in otobus["polyline"])
    assert otobus["trip_id"] == "t:a1" and otobus["route_id"] == "t:L1"
    yuruyus = y["legs"][2]                                              # B -> C aktarma yürüyüşü
    assert yuruyus["mode"] == "walk" and yuruyus["from"]["name"] == "B" and yuruyus["duration"] == 294
    assert y["walk_distance"] > 100 and all(e["duration"] >= 0 for e in y["legs"])
    assert "route_short_name" not in y["legs"][0]                       # yürüme etabında transit alanları yok


def test_mod_filtresi_ve_ulasilamaz(client, ag_kur):
    r = client.post("/api/plan", json=istek(modes=["bus"]))               # metro yasak: D'ye varılamaz
    assert r.status_code == 200 and r.json()["itineraries"] == []
    assert r.json()["neden"] == "baglanti_yok" and "rota bulunamadı" in r.json()["mesaj"]
    assert client.post("/api/plan", json=istek(modes=["metro", "bus"])).json()["itineraries"]


def test_maks_aktarma_sinirlar(client, ag_kur):
    assert client.post("/api/plan", json=istek(max_transfers=0)).json()["itineraries"] == []


def test_hizmet_gunu_cumartesi_sefer_yok(client, ag_kur):
    r = client.post("/api/plan", json=istek(depart_at=f"{CUMARTESI}T08:00:00+03:00"))
    assert r.json()["itineraries"] == []


def test_zaman_dilimleri(client, ag_kur):
    # UTC 05:00 = İstanbul 08:00; saat dilimsiz değer İstanbul saati sayılır
    utc = client.post("/api/plan", json=istek(depart_at=f"{PAZARTESI}T05:00:00Z")).json()["itineraries"][0]
    yerel = client.post("/api/plan", json=istek(depart_at=f"{PAZARTESI}T08:00:00")).json()["itineraries"][0]
    assert utc["departure_time"] == yerel["departure_time"] == f"{PAZARTESI}T08:00:00+03:00"
    # 08:45 sonrası bu hatlarda sefer yok (metro 08:40'ta kalkmıştı)
    gec = client.post("/api/plan", json=istek(depart_at=f"{PAZARTESI}T09:30:00+03:00")).json()
    assert gec["itineraries"] == []


def test_baslangic_ve_varis_durak_yok_mesajlari(client, ag_kur):
    uzak = {"lat": 41.3, "lng": 29.5}
    r = client.post("/api/plan", json=istek(origin=uzak)).json()
    assert r["neden"] == "baslangicta_durak_yok" and "800 m" in r["mesaj"]
    r = client.post("/api/plan", json=istek(dest=uzak, max_walk_m=300)).json()
    assert r["neden"] == "varista_durak_yok" and "300 m" in r["mesaj"]


@pytest.fixture
def ag_iki_secenek(ag):  # noqa: F811
    """Hızlı ama aktarmalı (bus + metro) ve yavaş ama aktarmasız (YAVAS) iki seçenek."""
    ag.durak("A", 0, 0); ag.durak("B", 4000, 0); ag.durak("C", 4300, 0); ag.durak("D", 9000, 0)
    ag.sefer("L1", "bus", [("A", "08:10"), ("B", "08:30")], hizmet="hi", gunler=HAFTA_ICI, kimlik="a1")
    ag.sefer("M1", "metro", [("C", "08:40"), ("D", "08:55")], hizmet="hi", gunler=HAFTA_ICI, kimlik="m1")
    ag.sefer("YAVAS", "bus", [("A", "08:10"), ("D", "10:00")], hizmet="hi", gunler=HAFTA_ICI, kimlik="y1")
    ag.yurume("B", "C", 294)
    servis.graf_ayarla(ag.graf())
    yield
    servis.graf_ayarla(None)


def test_tercihe_gore_siralama(client, ag_iki_secenek):
    hizli = client.post("/api/plan", json=istek(preference="fastest")).json()["itineraries"]
    az = client.post("/api/plan", json=istek(preference="fewest_transfers")).json()["itineraries"]
    assert [y["transfers"] for y in hizli] == [1, 0] and [y["transfers"] for y in az] == [0, 1]
    assert hizli[0]["total_duration"] < hizli[1]["total_duration"]


def test_gecersiz_girdiler_422(client, ag_kur):
    # yalnız enlem ya da yalnız boylam İstanbul dışında
    assert client.post("/api/plan", json=istek(origin={"lat": 42.5, "lng": 29.0})).status_code == 422
    assert client.post("/api/plan", json=istek(dest={"lat": 41.0, "lng": 31.5})).status_code == 422
    istanbul_disi = {"lat": 39.9, "lng": 32.8}                              # Ankara
    cevap = client.post("/api/plan", json=istek(origin=istanbul_disi))
    assert cevap.status_code == 422 and "origin" in str(cevap.json()["detail"])
    assert client.post("/api/plan", json=istek(modes=["helikopter"])).status_code == 422
    assert client.post("/api/plan", json=istek(max_transfers=9)).status_code == 422
    assert client.post("/api/plan", json=istek(max_walk_m=10)).status_code == 422
    assert client.post("/api/plan", json=istek(preference="en_ucuz")).status_code == 422
    assert client.post("/api/plan", json={"origin": istek()["origin"]}).status_code == 422
    assert client.post("/api/plan", json=istek(depart_at="dun")).status_code == 422
    cakisma = client.post("/api/plan", json=istek(arrive_by=f"{PAZARTESI}T09:00:00+03:00"))
    assert cakisma.status_code == 422 and "birlikte" in str(cakisma.json()["detail"])


def test_varisa_gore_en_gec_kalkis(client, ag_kur):
    govde = istek()
    govde.pop("depart_at")
    govde["arrive_by"] = f"{PAZARTESI}T09:30:00+03:00"
    r = client.post("/api/plan", json=govde)
    assert r.status_code == 200, r.text
    y = r.json()["itineraries"][0]
    # tek sefer var (otobüs 08:10, metro 08:55): en geç kalkış 08:10 otobüsüne yetişecek andır (~08:08)
    assert f"{PAZARTESI}T08:0" in y["departure_time"]
    assert y["arrival_time"] <= f"{PAZARTESI}T09:30:00+03:00" and y["arrival_time"] >= f"{PAZARTESI}T08:55"
    assert y["legs"][-1]["to"]["time"] == y["arrival_time"]


def test_varisa_gore_yetisen_rota_yok(client, ag_kur):
    govde = istek()
    govde.pop("depart_at")
    govde["arrive_by"] = f"{PAZARTESI}T08:30:00+03:00"                    # metro 08:55'te varıyor
    r = client.post("/api/plan", json=govde).json()
    assert r["itineraries"] == [] and r["neden"] == "yetismiyor" and "yetişen" in r["mesaj"]


def test_tercih_ve_sonuc_sayisi(client, ag_kur):
    for tercih in ("fastest", "fewest_transfers", "least_walking"):
        r = client.post("/api/plan", json=istek(preference=tercih, max_results=1))
        assert r.status_code == 200 and len(r.json()["itineraries"]) == 1


def test_graf_yoksa_503_ve_durum(client, ag):  # noqa: F811
    servis.graf_ayarla(None)
    r = client.post("/api/plan", json=istek())
    assert r.status_code == 503 and "yüklü değil" in r.json()["detail"]
    assert client.get("/api/plan/durum").json() == {"hazir": False, "yukleniyor": False, "hata": None, "durak": 0,
                                                    "ornek": 0, "sefer": 0, "guzergah_hat": 0}


def test_durum_graf_hazirken(client, ag_kur):
    d = client.get("/api/plan/durum").json()
    assert d["hazir"] is True and d["durak"] == 4 and d["sefer"] == 2


def test_openapi_plan_uc_noktalari(client):
    yollar = client.get("/openapi.json").json()["paths"]
    assert "post" in yollar["/api/plan"] and "get" in yollar["/api/plan/durum"]
    for eski in ("/api/en-yakin-durak", "/api/hatlar"):
        assert eski in yollar                                              # mevcut uç noktalar değişmeden duruyor


def test_gtfs_veritabani_ayri_adresten_okunur(ag, monkeypatch, tmp_path):  # noqa: F811
    """GTFS_DATABASE_URL tanımlıysa rota grafı oradan kurulur (canlı takip DATABASE_URL'de kalır)."""
    import os
    ag.durak("A", 0, 0)
    ag.durak("B", 1000, 0)
    ag.sefer("L1", "bus", [("A", "08:10"), ("B", "08:20")], kimlik="a1")
    ag.o.commit()
    monkeypatch.setenv("GTFS_DATABASE_URL", os.environ["DATABASE_URL"])    # test veritabanı dosyası
    monkeypatch.setattr(servis, "ONBELLEK_YOLU", str(tmp_path / "g.pkl"))
    servis.graf_ayarla(None)
    servis.yukle()
    d = servis.durum()
    assert d["hazir"] is True and d["hata"] is None and d["sefer"] == 1
    assert (tmp_path / "g.pkl").exists()
    servis.graf_ayarla(None)
    # geçersiz adres: hata durumda görünür, API çökmez
    monkeypatch.setenv("GTFS_DATABASE_URL", "sqlite:////yok/yok/yok.db")
    servis.yukle()
    assert servis.durum()["hazir"] is False and servis.durum()["hata"]

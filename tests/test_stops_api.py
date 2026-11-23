"""#14: durak arama ve yakındaki duraklar."""
import pytest

from app.routing import servis
from tests.test_routing import Ag, ag, hm, yer  # noqa: F401  (ag: fixture)


@pytest.fixture
def durak_agi(ag):  # noqa: F811
    # Kabataş: füniküler, tramvay, vapur (aynı ad, birbirine yakın) | Kadıköy metro | otobüs durakları
    ag.durak("Kabataş", 0, 0)
    ag.durak("KABATAŞ", 150, 0)                 # farklı yazım (büyük harf), aynı istasyon
    ag.durak("Kabataş İskele", 300, 0)
    ag.durak("Kadıköy", 5000, 0)
    for i in range(8):
        ag.durak(f"Kabaçam Sokak {i}", 8000 + i * 1000, 0)        # yalnızca otobüs, ad "kaba" ile başlar ve 3 harf eşleşir
    ag.durak("Uzak", 20000, 0)
    ag.sefer("F1", "funicular", [("Kabataş", "08:00"), ("Kadıköy", "08:10")], kimlik="f1")
    ag.sefer("T1", "tram", [("KABATAŞ", "08:00"), ("Kadıköy", "08:12")], kimlik="t1")
    ag.sefer("VP", "ferry", [("Kabataş İskele", "08:00"), ("Kadıköy", "08:20")], kimlik="v1")
    for i in range(8):
        ag.sefer(f"B{i}", "bus", [(f"Kabaçam Sokak {i}", "08:00"), ("Uzak", "08:30")], kimlik=f"b{i}")
    servis.graf_ayarla(ag.graf())
    yield
    servis.graf_ayarla(None)


def test_arama_turkce_karakterden_bagimsiz_ve_gruplu(client, durak_agi):
    r = client.get("/api/stops/search", params={"q": "kabatas"})
    assert r.status_code == 200
    s = r.json()["stops"]
    # Kabataş + KABATAŞ tek grup (füniküler+tramvay), "Kabataş İskele" (vapur) ayrı ad -> ayrı satır
    adlar = [x["name"] for x in s]
    assert adlar.count("Kabataş") + adlar.count("KABATAŞ") == 1 and "Kabataş İskele" in adlar
    grup = next(x for x in s if x["name"] in ("Kabataş", "KABATAŞ"))
    assert set(grup["modes"]) == {"funicular", "tram"} and len(grup["stop_ids"]) == 2
    assert grup["routes"][:2] == ["F1", "T1"] and grup["stop_id"] == grup["stop_ids"][0]


def test_arama_kisa_sorgu_422_ve_bos_sonuc(client, durak_agi):
    assert client.get("/api/stops/search", params={"q": "ka"}).status_code == 422
    assert client.get("/api/stops/search", params={"q": "yokboyleyer"}).json() == {"stops": []}


def test_arama_istasyon_turleri_onde_otobus_sinirli(client, durak_agi):
    s = client.get("/api/stops/search", params={"q": "kaba", "limit": 30}).json()["stops"]
    modlar = [x["modes"] for x in s]
    assert modlar[0] != ["bus"]                                   # istasyon türleri önde
    assert sum(1 for m in modlar if m == ["bus"]) == 5            # otobüs durakları en çok 5 satır


def test_yakin_duraklar_mesafe_sirali_gruplu(client, durak_agi):
    la, lo = yer(10, 0)
    r = client.get("/api/stops/nearby", params={"lat": la, "lng": lo, "radius_m": 500})
    assert r.status_code == 200
    s = r.json()["stops"]
    mesafeler = [x["distance_m"] for x in s]
    assert mesafeler == sorted(mesafeler) and mesafeler[0] <= 20
    assert len(s) == 2                                            # Kabataş grubu + Kabataş İskele (Kadıköy 5 km uzakta)
    assert all(x["distance_m"] <= 500 for x in s)


def test_yakin_duraklar_dogrulama_ve_graf_yok(client, durak_agi):
    assert client.get("/api/stops/nearby", params={"lat": 10, "lng": 29}).status_code == 422     # İstanbul dışı
    la, lo = yer(0, 0)
    assert client.get("/api/stops/nearby", params={"lat": la, "lng": lo, "radius_m": 50}).status_code == 422
    servis.graf_ayarla(None)
    assert client.get("/api/stops/search", params={"q": "kabatas"}).status_code == 503

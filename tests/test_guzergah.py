"""Resmî hat güzergah çizgileri: GeoJSON dizini, biniş→iniş kesiti, API'de `geometry: resmi`, indirme."""
import json
import math
import os

import pytest

from app.gtfs import build
from app.routing import guzergah, servis
from tests.test_api_plan import PAZARTESI
from tests.test_gtfs_build import SahteYanit
from tests.test_routing import HAFTA_ICI, Ag, ag, hm, yer  # noqa: F401

LAT0, LON0 = 41.0, 29.0


def kx():
    return 111_195.0 * math.cos(math.radians(LAT0))


def nokta(kuzey_m, dogu_m):
    return (LAT0 + kuzey_m / 111_195.0, LON0 + dogu_m / kx())


def geojson_yaz(yol):
    """Hat 34X: G yönü batıdan doğuya bir tümsekle (viraj), D yönü tersi. Hat 500: uzak başka bir yer."""
    g = [(0, 0), (1000, 0), (2000, 800), (3000, 800), (4000, 0), (5000, 0)]          # (doğu m, kuzey m)
    ozellikler = []

    def f(hat, kod, koord):
        ozellikler.append({"type": "Feature", "properties": {"HAT_KODU": hat, "GUZERGAH_KODU": kod},
                           "geometry": {"type": "LineString", "coordinates": [[LON0 + d / kx(), LAT0 + k / 111_195.0] for d, k in koord]}})

    f("34X", "34X_G_D0", g)
    f("34X", "34X_D_D0", g[::-1])
    f("500", "500_G_D0", [(0, 20000), (5000, 20000)])
    ozellikler.append({"type": "Feature", "properties": {"HAT_KODU": "NOKTA"}, "geometry": {"type": "Point", "coordinates": [29, 41]}})
    with open(yol, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": ozellikler}, fh)


@pytest.fixture
def guz(tmp_path):
    yol = tmp_path / "g.geojson"
    geojson_yaz(str(yol))
    return guzergah.indeks_kur(str(yol))


def test_indeks_hat_ve_cizgi_sayilari(guz):
    assert guz.ozet() == {"hat": 2, "cizgi": 3, "nokta": 6 + 6 + 2}                  # Point özelliği atlanır
    assert {p.kod for p in guz.hatlar["34X"]} == {"34X_G_D0", "34X_D_D0"}


def test_kesit_ileri_yon_secilir_ve_virajı_izler(guz):
    bas, bit = nokta(30, 1000), nokta(30, 4000)             # çizgiye 30 m uzakta, G yönünde ileri
    kes = guz.dilimle("34X", bas, bit)
    assert kes is not None and kes[0] == bas and kes[-1] == bit
    # viraj tepeleri (2000,800) ve (3000,800) kesitte bulunmalı: düz çizgi (durak sırası) olsaydı yok
    kuzey = [(la - LAT0) * 111_195.0 for la, lo in kes]
    assert max(kuzey) > 700
    ters = guz.dilimle("34X", bit, bas)                     # ters yönde: D çizgisi seçilir
    assert ters is not None and max((la - LAT0) * 111_195.0 for la, lo in ters) > 700


def test_uygun_cizgi_yoksa_none(guz):
    assert guz.dilimle("YOK", nokta(0, 0), nokta(0, 3000)) is None                      # bilinmeyen hat
    assert guz.dilimle("34X", nokta(0, 500), nokta(1500, 4000)) is None               # biniş çizgiden 1500 m uzak... (sapma)
    assert guz.dilimle("34X", nokta(0, 1000), nokta(0, 1010)) is None                 # ileri mesafe < 30 m
    assert guz.dilimle(None, nokta(0, 0), nokta(0, 1000)) is None
    assert guz.dilimle("500", nokta(0, 1000), nokta(0, 4000)) is None                 # 500 hattı başka yerde


def test_pickle_gidis_donus(guz, tmp_path):
    yol = str(tmp_path / "g.pkl")
    guzergah.kaydet(guz, yol)
    g2 = guzergah.oku(yol)
    assert g2 is not None and g2.ozet() == guz.ozet()
    assert g2.dilimle("34X", nokta(30, 1000), nokta(30, 4000)) is not None
    assert guzergah.oku(str(tmp_path / "yok.pkl")) is None


def test_api_resmi_cizgi_kullanir(client, ag, guz):  # noqa: F811
    # duraklar çizgiye ~30 m; otobüs hattı adı 34X: bacağın polyline'ı resmi çizgiden gelir
    ag.durak("A", 30, 1000)
    ag.durak("B", 30, 4000)
    ag.sefer("34X", "bus", [("A", "08:10"), ("B", "08:20")], hizmet="hi", gunler=HAFTA_ICI, kimlik="a1")
    servis.graf_ayarla(ag.graf())
    try:
        body = {"origin": {"lat": nokta(30, 900)[0], "lng": nokta(30, 900)[1]}, "dest": {"lat": nokta(30, 4100)[0], "lng": nokta(30, 4100)[1]},
                "depart_at": f"{PAZARTESI}T08:00:00+03:00"}
        servis.guzergah_ayarla(None)
        bacak = [e for e in client.post("/api/plan", json=body).json()["itineraries"][0]["legs"] if e["type"] == "transit"][0]
        assert bacak["geometry"] == "durak" and len(bacak["polyline"]) == 2
        servis.guzergah_ayarla(guz)
        bacak = [e for e in client.post("/api/plan", json=body).json()["itineraries"][0]["legs"] if e["type"] == "transit"][0]
        assert bacak["geometry"] == "resmi" and len(bacak["polyline"]) > 2
        assert max((la - LAT0) * 111_195.0 for la, lo in bacak["polyline"]) > 700          # viraj izlenir
        assert client.get("/api/plan/durum").json()["guzergah_hat"] == 2
    finally:
        servis.guzergah_ayarla(None)
        servis.graf_ayarla(None)


def test_geojson_indir_ve_dizinle(tmp_path):
    icerik = open(__file__, "rb").read()          # içerik önemsiz; indirme akışı sınanır

    def http_get(url, **kw):
        if url.endswith("package_show"):
            assert kw["params"] == {"id": "iett-hat-guzergahlari"}
            return SahteYanit({"success": True, "result": {"resources": [
                {"name": "Kılavuz", "format": "PDF", "url": "https://x.test/k.pdf"},
                {"name": "Hat Güzergahları", "format": "GeoJSON", "url": "https://x.test/hat.geojson"}]}})
        assert url == "https://x.test/hat.geojson"
        return SahteYanit(icerik=icerik)

    hedef = str(tmp_path / "alt" / "g.geojson")
    assert build.geojson_indir("iett-hat-guzergahlari", hedef, http_get=http_get, log=lambda m: None) == hedef
    assert os.path.getsize(hedef) == len(icerik)

    def yok(url, **kw):
        return SahteYanit({"success": True, "result": {"resources": [{"name": "x", "format": "CSV", "url": "https://x/y.csv"}]}})

    with pytest.raises(RuntimeError, match="GeoJSON"):
        build.geojson_indir("iett-hat-guzergahlari", hedef, http_get=yok, log=lambda m: None)


def test_birden_cok_ileri_varyantta_duraklara_en_yakin_secilir(tmp_path):
    # Aynı yönde iki varyant: ana yol ve 150 m kuzeyindeki paralel yol. Duraklar hangisine yakınsa o seçilmeli.
    yol = tmp_path / "v.geojson"
    f = []
    for kod, k in (("H_G_D0", 0), ("H_G_D1", 150)):
        f.append({"type": "Feature", "properties": {"HAT_KODU": "H", "GUZERGAH_KODU": kod},
                  "geometry": {"type": "LineString", "coordinates": [[LON0 + d / kx(), LAT0 + (k + (60 if 1500 < d < 2500 else 0)) / 111_195.0] for d in range(0, 5001, 500)]}})
    yol.write_text(json.dumps({"type": "FeatureCollection", "features": f}))
    g = guzergah.indeks_kur(str(yol))
    ana = g.dilimle("H", nokta(10, 500), nokta(10, 4000))
    paralel = g.dilimle("H", nokta(160, 500), nokta(160, 4000))
    assert max((la - LAT0) * 111_195.0 for la, lo in ana) < 100        # ana yol (0 m) izlendi
    assert min((la - LAT0) * 111_195.0 for la, lo in paralel[1:-1]) > 100  # paralel yol (150 m) izlendi


def test_cizgi_duragin_yakininden_iki_kez_geciyorsa_kisa_gecis_secilir(tmp_path):
    # Doğuya giden yol, 4 km'de U dönüşü yapıp 60 m kuzeyden geri dönüyor (hat tek çizgi). Duraklar dönüş yoluna daha yakın
    # (15 m; gidişe 45 m) ve 1 km - 3 km'de. En kısa kesit gidişteki 2 km'dir; dönüş yolunu seçmek
    # 4 km'lik U dönüşünü çizdirirdi (haritadaki dolanbaç).
    yol = tmp_path / "u.geojson"
    koord = [[LON0 + d / kx(), LAT0 + 0 / 111_195.0] for d in range(0, 4001, 500)]
    koord += [[LON0 + d / kx(), LAT0 + 60 / 111_195.0] for d in range(4000, -1, -500)]
    yol.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"HAT_KODU": "U", "GUZERGAH_KODU": "U_G_D0"},
         "geometry": {"type": "LineString", "coordinates": koord}}]}))
    g = guzergah.indeks_kur(str(yol))
    kes = g.dilimle("U", nokta(45, 1000), nokta(45, 3000))      # dönüş yoluna 15 m, gidişe 45 m: salt yakınlık dönüşü seçerdi
    assert kes is not None
    doguler = [(lo - LON0) * kx() for la, lo in kes]
    assert max(doguler) < 3100 and min(doguler) > 900                   # 4 km'ye uzanıp dönmedi
    assert len(kes) <= 8


def test_durak_cizgiden_uzaksa_uca_durak_eklenmez(guz):
    # durak çizgiye ~148 m uzakta (≤200 m kabul, >120 m bağlama): kesitin ucuna durak konumu eklenmez (sivri çıkıntı olmasın)
    bas, bit = nokta(190, 1000), nokta(30, 4000)
    kes = guz.dilimle("34X", bas, bit)
    assert kes is not None and kes[0] != bas and kes[-1] == bit


def test_cok_dolambacli_kesit_reddedilir(tmp_path):
    # Hat 1 km'lik düz mesafeyi 13 km'lik bir dolambaçla gidiyor (kuzeye 6 km, doğuya 1 km, güneye 6 km): kesit reddedilir
    yol = tmp_path / "d.geojson"
    pts = [(0, 0), (0, 6000), (1000, 6000), (1000, 0)]
    yol.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"HAT_KODU": "D", "GUZERGAH_KODU": "D_G_D0"},
         "geometry": {"type": "LineString", "coordinates": [[LON0 + d / kx(), LAT0 + k / 111_195.0] for d, k in pts]}}]}))
    g = guzergah.indeks_kur(str(yol))
    assert g.dilimle("D", nokta(0, 10), nokta(0, 990)) is None


def test_teshis_metni(guz):
    metin = "\n".join(guz.teshis("34X", nokta(30, 1000), nokta(30, 4000)))
    assert "34X: 2 çizgi" in metin and "OK " in metin and "seçilen kesit:" in metin and "yedeğe" not in metin
    assert "yedeğe düşer" in "\n".join(guz.teshis("34X", nokta(0, 500), nokta(1500, 4000)))

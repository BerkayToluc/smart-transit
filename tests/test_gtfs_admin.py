"""GTFS yönetici uç noktaları: sahte (küçük) GTFS dosyalarıyla uçtan uca.

GTFS klasörü main.py'de "./gtfs_data" olarak çalışma dizinine göre çözülüyor; testler
çalışma dizinini geçici klasöre alarak gerçek veriye dokunmaz.
"""
import csv

import pytest

# Gerçek dosyalardaki gibi: ';' ayraçlı, utf-8-sig, bozuk karakter (mojibake) ve
# noktalarla bozulmuş koordinatlar.
ROUTES = [
    ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type", "route_desc", "route_code"],
    ["1", "1", "T200", "KADIKÃ–Y - KÄ°RAZLITEPE", "3", "", "T200_D_D0"],
    ["2", "1", "T200", "KÄ°RAZLITEPE - KADIKÃ–Y", "3", "", "T200_G_D0"],
    ["3", "1", "T201", "BAÅžKA HAT", "3", "", "T201_D_D0"],
    ["4", "1", "T200", "VARYANT", "3", "", "T200_D_D5"],  # ana varyant (D0) tercih edilmeli
]
TRIPS = [
    ["trip_id", "route_id", "service_id", "trip_headsign", "direction_id"],
    ["100", "1", "6", "KÄ°RAZLITEPE", "0"],
    ["200", "2", "6", "KADIKÃ–Y", "1"],
    ["300", "4", "6", "VARYANT BASLIK", "0"],
]
STOP_TIMES = [
    ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
    ["100", "08:00:00", "08:00:00", "s1", "1"],
    ["100", "08:05:00", "08:05:00", "s2", "2"],
    ["100", "08:10:00", "08:10:00", "s3", "3"],
    ["200", "09:00:00", "09:00:00", "s3", "1"],
    ["200", "09:05:00", "09:05:00", "s2", "2"],
    ["200", "09:10:00", "09:10:00", "s1", "3"],
    ["300", "10:00:00", "10:00:00", "s1", "1"],
]
STOPS = [
    ["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon", "location_type"],
    ["s1", "1", "Ã‡AMLICA", "", "410.191.700.005.564", "286.843.529.999.755", "0"],
    ["s2", "2", "ORTA DURAK", "", "410.200.000.000.000", "286.900.000.000.000", "0"],
    ["s3", "3", "ÅžÄ°RÄ°NEVLER", "", "410.210.000.000.000", "286.950.000.000.000", "0"],
]


def _yaz(yol, satirlar):
    with open(yol, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=";").writerows(satirlar)


@pytest.fixture
def gtfs_klasoru(tmp_path, monkeypatch):
    klasor = tmp_path / "gtfs_data"
    klasor.mkdir()
    _yaz(klasor / "routes.csv", ROUTES)
    _yaz(klasor / "trips.csv", TRIPS)
    _yaz(klasor / "stop_times.csv", STOP_TIMES)
    _yaz(klasor / "stops.csv", STOPS)
    monkeypatch.chdir(tmp_path)
    return klasor


def test_tum_hatlari_listele(client, gtfs_klasoru):
    r = client.get("/api/admin/tum-hatlari-listele")
    assert r.status_code == 200
    assert r.json() == {"toplam_hat_sayisi": 2, "hatlar": ["T200", "T201"]}


def test_gtfs_aktar_uctan_uca(client, db, gtfs_klasoru):
    import main

    r = client.get("/api/admin/gtfs-aktar/T200")
    assert r.status_code == 200
    g = r.json()
    assert "hata" not in g, g
    assert "6 durak" in g["mesaj"]
    assert g["yonler"] == {"D": "KİRAZLITEPE", "G": "KADIKÖY"}   # mojibake düzeltilmiş

    db.expire_all()
    hat = db.query(main.Hat).filter(main.Hat.hat_kodu == "T200").one()
    assert hat.hat_adi == "KADIKÖY - KİRAZLITEPE"

    duraklar = (db.query(main.Durak).filter(main.Durak.hat_id == hat.id)
                .order_by(main.Durak.yon, main.Durak.sira_no).all())
    assert len(duraklar) == 6
    gidis = [d for d in duraklar if d.yon == "KİRAZLITEPE"]
    donus = [d for d in duraklar if d.yon == "KADIKÖY"]
    assert [d.durak_adi for d in gidis] == ["ÇAMLICA", "ORTA DURAK", "ŞİRİNEVLER"]
    assert [d.durak_adi for d in donus] == ["ŞİRİNEVLER", "ORTA DURAK", "ÇAMLICA"]
    assert [d.sira_no for d in gidis] == [1, 2, 3]
    # Bozuk koordinatlar düzeltilmiş
    assert gidis[0].latitude == pytest.approx(41.0191700005564)
    assert gidis[0].longitude == pytest.approx(28.6843529999755)


def test_gtfs_aktar_tekrar_calisinca_cogaltmaz(client, db, gtfs_klasoru):
    import main

    client.get("/api/admin/gtfs-aktar/T200")
    r = client.get("/api/admin/gtfs-aktar/T200")
    assert "hata" not in r.json()
    db.expire_all()
    hat = db.query(main.Hat).filter(main.Hat.hat_kodu == "T200").one()
    assert db.query(main.Durak).filter(main.Durak.hat_id == hat.id).count() == 6


def test_gtfs_aktar_bilinmeyen_hat(client, gtfs_klasoru):
    r = client.get("/api/admin/gtfs-aktar/YOKTUR")
    assert r.status_code == 200
    assert r.json() == {"hata": "routes.csv içinde 'YOKTUR' kodlu hat bulunamadı."}


def test_gtfs_aktar_dosya_yoksa_anlamli_hata(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # içinde gtfs_data yok
    r = client.get("/api/admin/gtfs-aktar/T200")
    assert r.status_code == 200
    assert "GTFS dosyası bulunamadı" in r.json()["hata"]

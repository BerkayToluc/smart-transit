"""#32: /health, istek süresi günlüğü, yavaş istek uyarısı, plan önbelleği."""
import logging

from app import saglik
from app.routing import servis
from tests.test_api_plan import ag_kur, istek  # noqa: F401  (ag_kur: fixture)
from tests.test_routing import ag  # noqa: F401  (ag_kur ona bağlı)


def test_health_bilesen_bazli_ok(client, ag_kur):  # noqa: F811
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["durum"] in ("ok", "degraded")
    assert d["bilesenler"]["veritabani"]["durum"] == "ok"
    assert d["bilesenler"]["rota_grafi"]["durum"] == "ok" and d["bilesenler"]["rota_grafi"]["durak"] == 4
    assert d["bilesenler"]["iett"]["durum"] in ("bilinmiyor", "ok", "erisilemiyor")
    assert set(d["bilesenler"]["plan_onbellegi"]) >= {"isabet", "iskalama", "isabet_orani"}


def test_health_graf_yoksa_degraded_ve_veritabani_yoksa_503(client, monkeypatch):
    servis.graf_ayarla(None)
    d = client.get("/health").json()
    assert d["durum"] == "degraded" and d["bilesenler"]["rota_grafi"]["durum"] == "hata"

    class Bozuk:
        def __enter__(self):
            raise RuntimeError("bağlanamadı")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("app.db.SessionLocal", lambda: Bozuk())
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["durum"] == "down"
    assert r.json()["bilesenler"]["veritabani"]["durum"] == "hata"


def test_istek_suresi_loglanir_ve_basliga_yazilir(client, caplog):
    with caplog.at_level(logging.INFO, logger="smarttransit.istek"):
        r = client.get("/health")
    assert "X-Response-Time-ms" in r.headers
    assert any("GET /health -> " in m and " ms" in m for m in caplog.messages)


def test_yavas_istek_uyari_olarak_loglanir(client, caplog, monkeypatch):
    monkeypatch.setattr(saglik, "YAVAS_ESIK_SN", -1)
    with caplog.at_level(logging.INFO, logger="smarttransit.istek"):
        client.get("/health")
    kayit = [k for k in caplog.records if "GET /health" in k.getMessage()][0]
    assert kayit.levelno == logging.WARNING and "YAVAS" in kayit.getMessage()


def test_plan_onbellegi_isabet_sayar_ve_graf_degisince_gecersiz(client, ag_kur):  # noqa: F811
    saglik.plan_onbellek.update(isabet=0, iskalama=0)
    a = client.post("/api/plan", json=istek())
    b = client.post("/api/plan", json=istek())
    assert a.json() == b.json() and (saglik.plan_onbellek["isabet"], saglik.plan_onbellek["iskalama"]) == (1, 1)
    client.post("/api/plan", json=istek(max_results=2))            # farklı istek -> ıskalama
    assert saglik.plan_onbellek["iskalama"] == 2
    servis.graf_ayarla(ag_kur)                                       # graf yeniden yüklendi -> eski sonuç geçersiz
    client.post("/api/plan", json=istek())
    assert saglik.plan_onbellek["iskalama"] == 3
    assert client.get("/health").json()["bilesenler"]["plan_onbellegi"]["isabet_orani"] == 0.25


def test_plan_hatalari_onbellege_girmez(client):
    servis.graf_ayarla(None)
    saglik.plan_onbellek.update(isabet=0, iskalama=0)
    assert client.post("/api/plan", json=istek()).status_code == 503
    assert client.post("/api/plan", json=istek()).status_code == 503
    assert saglik.plan_onbellek["isabet"] == 0

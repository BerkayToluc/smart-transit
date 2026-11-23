"""#29: yönetici anahtarı, CORS ve hız sınırı."""
import pytest

from app import guvenlik


def test_admin_anahtarsiz_istek_401(client):
    assert client.get("/api/admin/tum-hatlari-listele").status_code == 401


def test_admin_yanlis_anahtar_401(client):
    assert client.get("/api/admin/tum-hatlari-listele", headers={"X-Admin-Key": "yanlis"}).status_code == 401


def test_admin_anahtar_tanimli_degilse_403(client, monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY")
    r = client.get("/api/admin/tum-hatlari-listele", headers={"X-Admin-Key": "herhangi"})
    assert r.status_code == 403


def test_cors_varsayilan_yerel_originler(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    originler, kimlik = guvenlik.cors_ayarlari()
    assert "http://localhost:3000" in originler and "*" not in originler and kimlik is False


def test_cors_liste_ve_yildiz(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example/")
    assert guvenlik.cors_ayarlari() == (["https://a.example", "https://b.example"], False)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    assert guvenlik.cors_ayarlari() == (["*"], False)


def test_cors_izinsiz_origin_basligi_donmez(client):
    ok = client.get("/", headers={"Origin": "http://localhost:3000"})
    kotu = client.get("/", headers={"Origin": "https://kotu.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in kotu.headers


def test_hiz_siniri_asilinca_429(client, monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_DEVRE_DISI")
    guvenlik._ZAMANLAR.clear()
    govde = {"hat_kodu": "T200", "baslangic_lat": 41.0, "baslangic_lng": 29.0, "hedef_lat": 41.01, "hedef_lng": 29.01}
    kodlar = [client.post("/api/en-yakin-durak", json=govde).status_code for _ in range(61)]
    assert kodlar[:60] == [200] * 60 and kodlar[60] == 429
    guvenlik._ZAMANLAR.clear()


def test_en_yakin_durak_koordinat_dogrulamasi(client):
    govde = {"hat_kodu": "T200", "baslangic_lat": 999, "baslangic_lng": 29.0, "hedef_lat": 41.01, "hedef_lng": 29.01}
    assert client.post("/api/en-yakin-durak", json=govde).status_code == 422

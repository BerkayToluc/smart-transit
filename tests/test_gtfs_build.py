"""app/gtfs/build.py (indirme, rapor) ve scripts/build_gtfs.py (komut satırı) testleri.

Portala GERÇEK istek atılmaz: http_get sahte bir CKAN/dosya sunucusudur."""
import os
import subprocess
import sys

import pytest
import requests

from app.gtfs import build, loader
from app.gtfs.feeds import IETT

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SahteYanit:
    def __init__(self, json_veri=None, icerik=b"", hata=None):
        self._json, self._icerik, self._hata = json_veri, icerik, hata

    def raise_for_status(self):
        if self._hata:
            raise self._hata

    def json(self):
        return self._json

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._icerik), 4):
            yield self._icerik[i:i + 4]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def zip_yap(ad, icerik, *, uye=None):
    """İçinde tek dosya olan bellek içi ZIP üretir."""
    import io
    import zipfile
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(uye or f"{ad}.csv", icerik)
    return tampon.getvalue()


def sahte_portal(dosyalar, *, zip_dosyalar=None, ilk_denemede_hata=None):
    """CKAN package_show + dosya indirme taklidi.
    dosyalar: ad -> CSV bayt içerik; zip_dosyalar: ad -> ZIP bayt içerik."""
    cagrilar = []
    zip_dosyalar = zip_dosyalar or {}
    kaynaklar = [{"name": ad, "format": "CSV", "url": f"https://x.test/{ad}.csv", "size": len(v)}
                 for ad, v in dosyalar.items()]
    kaynaklar += [{"name": ad, "format": "ZIP", "url": f"https://x.test/{ad}.zip", "size": len(v)}
                  for ad, v in zip_dosyalar.items()]
    kaynaklar += [{"name": "Kullanım Dokümanı", "format": "PDF", "url": "https://x.test/doc.pdf", "size": 9},
                  {"name": "bilinmeyen", "format": "CSV", "url": "https://x.test/b.csv", "size": 1}]
    sayac = {"n": 0}

    def http_get(url, **kw):
        cagrilar.append(url)
        if url.endswith("package_show"):
            assert kw["params"] == {"id": "iett-gtfs-verisi"}
            return SahteYanit({"success": True, "result": {"resources": kaynaklar}})
        if ilk_denemede_hata and sayac["n"] == 0:
            sayac["n"] += 1
            raise ilk_denemede_hata
        ad, uzanti = os.path.basename(url).rsplit(".", 1)
        return SahteYanit(icerik=(zip_dosyalar if uzanti == "zip" else dosyalar)[ad])
    return http_get, cagrilar


DOSYALAR = {"routes": b"route_id;route_type\n1;3\n", "stops": b"stop_id\n1\n", "trips": b"trip_id\n1\n"}


def test_kaynak_listesi_yalnizca_gtfs_csv():
    http_get, _ = sahte_portal(DOSYALAR)
    liste = build.kaynak_listesi("iett-gtfs-verisi", http_get=http_get)
    assert [k["ad"] for k in liste] == ["routes", "stops", "trips"]    # PDF ve bilinmeyen ad yok
    assert all(k["url"].endswith(".csv") and k["bicim"] == "csv" for k in liste)


def test_kaynak_listesi_zip_csvye_tercih_edilir():
    # İETT: stop_times hem CSV (Excel'de kırpılmış) hem ZIP (eksiksiz) olarak var
    http_get, _ = sahte_portal({**DOSYALAR, "stop_times": b"KIRPILMIS"},
                               zip_dosyalar={"stop_times": zip_yap("stop_times", b"TAM")})
    secim = {k["ad"]: k for k in build.kaynak_listesi("iett-gtfs-verisi", http_get=http_get)}
    assert secim["stop_times"]["bicim"] == "zip" and secim["stop_times"]["url"].endswith(".zip")
    assert secim["routes"]["bicim"] == "csv"


def test_kaynak_listesi_basarisiz_yanit():
    def http_get(url, **kw):
        return SahteYanit({"success": False, "error": {"message": "Not found"}})
    with pytest.raises(RuntimeError, match="döndürmedi"):
        build.kaynak_listesi("yok", http_get=http_get)


def test_indir_dosyalari_yazar_ve_tekrarda_atlar(tmp_path):
    http_get, cagrilar = sahte_portal(DOSYALAR)
    mesajlar = []
    yollar = build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append)
    assert sorted(os.path.basename(y) for y in yollar) == ["routes.csv", "stops.csv", "trips.csv"]
    assert (tmp_path / "routes.csv").read_bytes() == DOSYALAR["routes"]
    assert not list(tmp_path.glob("*.part"))                           # geçici dosya kalmadı
    # ikinci çalıştırma: boyutlar aynı -> hiç dosya indirilmez
    onceki = len(cagrilar)
    assert build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append) == []
    assert all(c.endswith("package_show") for c in cagrilar[onceki:])


def test_indir_zipten_acar_ve_kirpilmis_csvyi_degistirir(tmp_path):
    tam = b"trip_id,stop_id\n" + b"1,2\n" * 50
    http_get, cagrilar = sahte_portal({**DOSYALAR, "stop_times": b"KIRPILMIS"},
                                      zip_dosyalar={"stop_times": zip_yap("stop_times", tam)})
    (tmp_path / "stop_times.csv").write_bytes(b"ESKI KIRPILMIS DOSYA")        # önceki (hatalı) indirme
    mesajlar = []
    build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append)
    assert (tmp_path / "stop_times.csv").read_bytes() == tam                  # ZIP'teki tam dosya
    assert (tmp_path / "stop_times.zip").exists() and not list(tmp_path.glob("*.part"))
    assert any("içinden stop_times.csv açılıyor" in m for m in mesajlar)
    assert not any(c.endswith("stop_times.csv") for c in cagrilar)            # CSV hiç indirilmedi
    # ikinci çalıştırma: ZIP boyutu aynı ve CSV var -> yeniden indirilmez
    onceki = len(cagrilar)
    build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append)
    assert all(c.endswith("package_show") for c in cagrilar[onceki:])


@pytest.mark.parametrize("uye", ["stop_times.txt", "klasor/StopTimes/stop_times.csv", "tek_dosya.dat"])
def test_zipten_acma_uye_adi_varyantlari(tmp_path, uye):
    http_get, _ = sahte_portal(DOSYALAR, zip_dosyalar={"stop_times": zip_yap("stop_times", b"a,b\n1,2\n", uye=uye)})
    build.indir("iett", str(tmp_path), http_get=http_get, log=lambda _m: None)
    assert (tmp_path / "stop_times.csv").read_bytes() == b"a,b\n1,2\n"


def test_zipte_beklenen_dosya_yoksa_hata(tmp_path):
    import io
    import zipfile
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("a.csv", b"1")
        z.writestr("b.csv", b"2")                                             # birden çok, hiçbiri stop_times değil
    http_get, _ = sahte_portal(DOSYALAR, zip_dosyalar={"stop_times": tampon.getvalue()})
    with pytest.raises(RuntimeError, match="bulunamadı"):
        build.indir("iett", str(tmp_path), http_get=http_get, log=lambda _m: None, deneme=1)


def test_bozuk_zip_tekrar_denenir_sonra_hata_verir(tmp_path, monkeypatch):
    import zipfile
    monkeypatch.setattr(build.time, "sleep", lambda _s: None)
    http_get, _ = sahte_portal(DOSYALAR, zip_dosyalar={"stop_times": b"BU BIR ZIP DEGIL"})
    mesajlar = []
    with pytest.raises(zipfile.BadZipFile):
        build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append, deneme=2)
    assert any("tekrar deneniyor" in m for m in mesajlar)
    assert not (tmp_path / "stop_times.csv").exists()


def test_indir_excel_sinirinda_dosya_uyarir(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "EXCEL_SATIR_SINIRI", 3)
    icerik = b"trip_id\n1\n2\n3\n"                                        # 3 veri satırı = sınır
    http_get, _ = sahte_portal({**DOSYALAR, "stop_times": icerik})
    mesajlar = []
    build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append)
    assert any("UYARI" in m and "Excel" in m for m in mesajlar)


def test_indir_hata_olunca_tekrar_dener(tmp_path, monkeypatch):
    monkeypatch.setattr(build.time, "sleep", lambda _s: None)
    http_get, _ = sahte_portal(DOSYALAR, ilk_denemede_hata=requests.ConnectionError("koptu"))
    mesajlar = []
    build.indir("iett", str(tmp_path), http_get=http_get, log=mesajlar.append)
    assert any("tekrar deneniyor" in m for m in mesajlar)
    assert (tmp_path / "routes.csv").exists()


def test_indir_kalici_hatada_firlatir(tmp_path, monkeypatch):
    monkeypatch.setattr(build.time, "sleep", lambda _s: None)

    def http_get(url, **kw):
        if url.endswith("package_show"):
            return SahteYanit({"success": True, "result": {"resources": [
                {"name": "routes", "format": "CSV", "url": "https://x.test/routes.csv", "size": 3}]}})
        raise requests.ConnectionError("hep kopuyor")
    with pytest.raises(requests.ConnectionError):
        build.indir("iett", str(tmp_path), http_get=http_get, log=lambda _m: None, deneme=2)
    assert not (tmp_path / "routes.csv").exists()


def test_indir_bos_paket(tmp_path):
    def http_get(url, **kw):
        return SahteYanit({"success": True, "result": {"resources": []}})
    with pytest.raises(RuntimeError, match="bulunamadı"):
        build.indir("iett", str(tmp_path), http_get=http_get, log=lambda _m: None)


# --- rapor ----------------------------------------------------------------------------------
def test_rapor(oturum, iett_kusurlu):
    loader.load_feed(oturum, iett_kusurlu, IETT)
    r = build.rapor(oturum, "iett")
    assert r["yuklu"] and r["route"] == 2 and r["trip"] == 2 and r["stop"] == 2
    assert r["hat_modlari"] == {"metrobus": 1, "bus": 1}
    assert r["sefer_modlari"] == {"metrobus": 1, "bus": 1}
    assert r["stop_time"] == 3
    assert r["uyarilar"]["gunsuz_hizmet"] == 0 and r["uyarilar"]["saatsiz_sefer"] == 0
    metin = build.rapor_metni(r)
    assert "metrobus=1" in metin and "veri tarihi: 2026-04-21" in metin


def test_rapor_yuklu_degil(oturum):
    assert build.rapor(oturum, "olmayan") == {"feed_id": "olmayan", "yuklu": False}
    assert "yüklü değil" in build.rapor_metni(build.rapor(oturum, "olmayan"))


# --- komut satırı (gerçek süreç, yalıtılmış SQLite) -----------------------------------------------
def calistir(*args, env_ekle=None):
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update(env_ekle or {})
    return subprocess.run([sys.executable, os.path.join(KOK, "scripts", "build_gtfs.py"), *args],
                          cwd=KOK, capture_output=True, text=True, env=env, timeout=120)


def test_komut_satiri_yukle_ve_rapor(iett_kusurlu, tmp_path):
    hedef = f"sqlite:///{tmp_path / 'alt' / 'gtfs.db'}"
    c = calistir("yukle", "iett", "--klasor", iett_kusurlu, "--hedef", hedef)
    assert c.returncode == 0, c.stderr
    assert "özet:" in c.stdout and "metrobus=1" in c.stdout and "Boyut:" in c.stdout
    r = calistir("rapor", "iett", "--hedef", hedef)                       # ayrı süreç: veri kalıcı
    assert r.returncode == 0 and "hat 2, sefer 2, durak 2" in r.stdout, r.stdout + r.stderr


def test_komut_satiri_hedefsiz_yukleme_onay_ister(iett_kusurlu):
    # --hedef de --evet de yok: canlı veritabanına dokunmadan durur
    c = calistir("yukle", "iett", "--klasor", iett_kusurlu,
                 env_ekle={"DATABASE_URL": "postgresql://kullanici:gizli@ornek.host/db"})
    assert c.returncode == 2
    assert "--evet" in c.stdout and "gizli" not in c.stdout + c.stderr     # parola asla yazdırılmaz
    assert "kullanici:****@ornek.host" in c.stdout


def test_komut_satiri_hatalari():
    assert calistir("yukle", "yok", "--hedef", "sqlite://").returncode == 2
    assert calistir("yukle", "iett", "ibb", "--klasor", "x", "--hedef", "sqlite://").returncode == 2


# --- rapor: isim kalitesi kontrolü ----------------------------------------------------------------
def test_rapor_temiz_isimlerde_sorun_bildirmez(oturum, iett_kusurlu):
    loader.load_feed(oturum, iett_kusurlu, IETT)                  # bozuk kodlama düzeltilerek yüklenir
    u = build.rapor(oturum, "iett")["uyarilar"]
    assert (u["supheli_karakter_durak"], u["supheli_karakter_hat"], u["adsiz_durak"]) == (0, 0, 0)
    assert "bozuk karakter şüphesi yok" in build.rapor_metni(build.rapor(oturum, "iett"))


def test_rapor_duzeltilmemis_bozuk_karakteri_yakalar(oturum, iett_kusurlu):
    from app.gtfs.feeds import FeedConfig
    # aynı veri, ama bozuk kodlama düzeltmesi KAPALI: "SÖĞÜTLÜÇEÅ\x9eME" düzeltilmeden yüklenir
    loader.load_feed(oturum, iett_kusurlu, FeedConfig(feed_id="kontrol", name="x", fix_mojibake=False))
    r = build.rapor(oturum, "kontrol")
    assert r["uyarilar"]["supheli_karakter_durak"] == 1
    assert "SÖĞÜTLÜÇEÅ" in r["uyarilar"]["supheli_ornekler"][0]
    assert "bozuk karakter şüphesi: 1 durak" in build.rapor_metni(r)

"""app/gtfs/build.py (indirme, rapor) ve scripts/build_gtfs.py (komut satırı) testleri.

Portala GERÇEK istek atılmaz: http_get sahte bir CKAN/dosya sunucusudur."""
import os
import subprocess
import sys

import pytest
import requests

from app.gtfs import build, loader
from app.gtfs.feeds import IETT
from tests.conftest import yaz

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


# --- rapor: saatsiz seferlerin hatları; komut satırı mesajları ---------------------------------------
def test_rapor_saatsiz_seferlerin_hatlarini_gosterir(oturum, tmp_path):
    d = tmp_path / "saatsiz"
    d.mkdir()
    yaz(d / "calendar.csv", [["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                              "sunday", "start_date", "end_date"], ["6", 1, 1, 1, 1, 1, 1, 1, "20260101", "20261231"]])
    yaz(d / "routes.csv", [["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
                           ["r1", "1", "M99", "ÇIKMAZ - SOKAK", 1], ["r2", "1", "M98", "NORMAL - HAT", 1]])
    yaz(d / "trips.csv", [["trip_id", "route_id", "service_id", "trip_headsign", "direction_id"],
                          ["t1", "r1", "6", "X", 0], ["t2", "r2", "6", "Y", 0]])
    yaz(d / "stop_times.csv", [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
                               ["t2", "07:00:00", "07:00:00", "s1", 1]])                    # t1'in hiç saati yok
    yaz(d / "stops.csv", [["stop_id", "stop_name", "stop_lat", "stop_lon"], ["s1", "A", "41.0", "29.0"]])
    from app.gtfs.feeds import FeedConfig
    loader.load_feed(oturum, str(d), FeedConfig(feed_id="saatsiz", name="x"))
    r = build.rapor(oturum, "saatsiz")
    assert r["uyarilar"]["saatsiz_sefer"] == 1
    assert r["uyarilar"]["saatsiz_sefer_hatlari"] == ["M99 (ÇIKMAZ - SOKAK)"]
    assert "hatlar: M99 (ÇIKMAZ - SOKAK)" in build.rapor_metni(r)


def test_komut_satiri_hepsi_elle_tanimliyi_bir_kez_uretir(tmp_path):
    hedef = f"sqlite:///{tmp_path / 'gtfs.db'}"
    c = calistir("hepsi", "marmaray", "--klasor", str(tmp_path / "m"), "--hedef", hedef)
    assert c.returncode == 0, c.stderr
    assert c.stdout.count("kurallardan GTFS dosyaları üretiliyor") == 1       # çift üretim yok
    assert "portaldan indiriliyor" not in c.stdout                            # Marmaray indirilmez
    assert "hat 2, sefer 7, durak 43" in c.stdout


# --- sefer saatleri analizi (`saatler`) -----------------------------------------------------------------
@pytest.mark.parametrize("gunler, etiket", [
    ([1, 1, 1, 1, 1, 1, 1], "Her gün"), ([1, 1, 1, 1, 1, 0, 0], "Pzt-Cum"), ([0, 0, 0, 0, 0, 1, 0], "Cts"),
    ([0, 0, 0, 0, 0, 1, 1], "Cts-Paz"), ([0, 0, 0, 0, 1, 1, 0], "Cum-Cts"), ([1, 0, 1, 0, 0, 0, 1], "Pzt,Çar,Paz"),
    ([1, 1, 0, 0, 0, 0, 1], "Pzt-Sal,Paz"), ([0, 0, 0, 0, 0, 0, 0], "(günsüz)"),
])
def test_gun_etiketi(gunler, etiket):
    assert build.gun_etiketi(gunler) == etiket


@pytest.fixture
def vapur_klasoru(tmp_path):
    """Tek vapur hattı: hafta içi 20 dk aralık (5 açık sefer + aralıklı şablon), hafta sonu 40 dk, ters yön tek sefer."""
    d = tmp_path / "vapur"
    d.mkdir()
    yaz(d / "calendar.csv", [["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                              "sunday", "start_date", "end_date"],
                             ["100", 1, 1, 1, 1, 1, 0, 0, "20220101", "20221231"],
                             ["101", 0, 0, 0, 0, 0, 1, 1, "20220101", "20221231"]])
    yaz(d / "routes.csv", [["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
                           ["r1", "1", "KDK-EMN", "KADIKÖY - EMİNÖNÜ", 4]])
    seferler = [["t1", "100", 7 * 3600], ["t2", "100", 7 * 3600 + 1200], ["t3", "100", 7 * 3600 + 2400],
                ["t4", "100", 8 * 3600], ["t5", "100", 8 * 3600 + 1200],
                ["w1", "101", 9 * 3600], ["w2", "101", 9 * 3600 + 2400], ["w3", "101", 10 * 3600 + 1200]]
    hms = lambda sn: f"{sn // 3600:02d}:{sn % 3600 // 60:02d}:{sn % 60:02d}"
    satir = [["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"]]
    st = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
    for tid, srv, b in seferler:
        satir.append(["r1", srv, tid, "Eminönü", 0])
        st += [[tid, hms(b), hms(b), "s1", 1], [tid, hms(b + 1200), hms(b + 1200), "s2", 2]]
    satir.append(["r1", "100", "tf", "Eminönü", 0])                     # aralıklı şablon: 08:40, 09:00, 09:20
    st += [["tf", "00:00:00", "00:00:00", "s1", 1], ["tf", "00:20:00", "00:20:00", "s2", 2]]
    satir.append(["r1", "100", "ters", "Kadıköy", 1])                    # ters yön, tek sefer
    st += [["ters", "07:10:00", "07:10:00", "s2", 1], ["ters", "07:30:00", "07:30:00", "s1", 2]]
    yaz(d / "trips.csv", satir)
    yaz(d / "stop_times.csv", st)
    yaz(d / "stops.csv", [["stop_id", "stop_name", "stop_lat", "stop_lon"], ["s1", "Kadıköy", "40.99", "29.02"],
                          ["s2", "Eminönü", "41.01", "28.97"]])
    yaz(d / "frequencies.csv", [["trip_id", "start_time", "end_time", "headway_secs", "exact_times"],
                                ["tf", "08:40:00", "09:30:00", 1200, 0]])
    return str(d)


def test_sefer_saatleri_gruplari(oturum, vapur_klasoru):
    from app.gtfs.feeds import FeedConfig
    loader.load_feed(oturum, vapur_klasoru, FeedConfig(feed_id="vapur", name="x"))
    grup = {(k["gun"], k["yon"]): k for k in build.sefer_saatleri(oturum, "vapur")}
    hafta_ici = grup[("Pzt-Cum", 0)]
    assert (hafta_ici["ilk_durak"], hafta_ici["son_durak"]) == ("Kadıköy", "Eminönü")
    assert hafta_ici["sefer"] == 8                                      # 5 açık + aralıklı şablondan 3 sefer
    assert (hafta_ici["ilk"], hafta_ici["son"]) == (7 * 3600, 9 * 3600 + 1200)    # 07:00 ... 09:20
    assert (hafta_ici["aralik_dk"], hafta_ici["aralik_payi"]) == (20, 1.0)
    assert (hafta_ici["sure_dk"], hafta_ici["sure_en_az"], hafta_ici["sure_en_cok"]) == (20.0, 20.0, 20.0)
    hafta_sonu = grup[("Cts-Paz", 0)]
    assert (hafta_sonu["sefer"], hafta_sonu["aralik_dk"]) == (3, 40)
    ters = grup[("Pzt-Cum", 1)]
    assert (ters["ilk_durak"], ters["son_durak"], ters["sefer"], ters["aralik_dk"]) == ("Eminönü", "Kadıköy", 1, None)
    metin = build.sefer_saatleri_metni(build.sefer_saatleri(oturum, "vapur"))
    assert "KDK-EMN  [ferry]" in metin
    assert "Pzt-Cum   Kadıköy -> Eminönü | 8 sefer | 07:00 - 09:20 | en sık aralık 20 dk (%100) | süre 20 dk" in metin
    assert "tek sefer" in metin


def test_sefer_saatleri_suzgecler(oturum, vapur_klasoru):
    from app.gtfs.feeds import FeedConfig
    loader.load_feed(oturum, vapur_klasoru, FeedConfig(feed_id="vapur", name="x"))
    assert build.sefer_saatleri(oturum, "vapur", hatlar=["kdk-emn"])                  # büyük/küçük harf ve ASCII duyarsız
    assert build.sefer_saatleri(oturum, "vapur", hatlar=["YOK"]) == []
    assert build.sefer_saatleri(oturum, "vapur", en_az_sefer=100) == []
    assert build.sefer_saatleri(oturum, "vapur", modlar=["metro"]) == []
    assert build.sefer_saatleri(oturum, "vapur", modlar=["ferry"], en_az_sefer=10)      # 10 sefer satırı yüklü (5 + 3 + şablon + ters)
    assert build.sefer_saatleri(oturum, "vapur", en_az_sefer=11) == []
    assert "eşleşen hat/sefer yok" in build.sefer_saatleri_metni([])


def test_sefer_saatleri_degisen_aralik_en_sik_olani_secer(oturum, tmp_path):
    from app.gtfs.feeds import FeedConfig
    d = tmp_path / "v2"
    d.mkdir()
    yaz(d / "calendar.csv", [["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
                              "sunday", "start_date", "end_date"], ["1", 1, 1, 1, 1, 1, 1, 1, "20220101", "20221231"]])
    yaz(d / "routes.csv", [["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"], ["r", "1", "X", "Y", 4]])
    saatler = [6 * 60, 6 * 60 + 15, 6 * 60 + 30, 6 * 60 + 45, 7 * 60 + 30]          # 15,15,15 sonra 45 dk
    yaz(d / "trips.csv", [["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"]] +
        [["r", "1", f"t{i}", "Y", 0] for i in range(len(saatler))])
    st = [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]]
    for i, dk in enumerate(saatler):
        st += [[f"t{i}", f"{dk // 60:02d}:{dk % 60:02d}:00", f"{dk // 60:02d}:{dk % 60:02d}:00", "a", 1],
               [f"t{i}", f"{(dk + 10) // 60:02d}:{(dk + 10) % 60:02d}:00", f"{(dk + 10) // 60:02d}:{(dk + 10) % 60:02d}:00", "b", 2]]
    yaz(d / "stop_times.csv", st)
    yaz(d / "stops.csv", [["stop_id", "stop_name", "stop_lat", "stop_lon"], ["a", "A", "41.0", "29.0"], ["b", "B", "41.1", "29.1"]])
    loader.load_feed(oturum, str(d), FeedConfig(feed_id="v2", name="x"))
    k = build.sefer_saatleri(oturum, "v2")[0]
    assert (k["aralik_dk"], round(k["aralik_payi"], 2)) == (15, 0.75)            # 3 / 4 aralık 15 dk


def test_komut_satiri_saatler_marmaray(tmp_path):
    hedef = f"sqlite:///{tmp_path / 'gtfs.db'}"
    assert calistir("yukle", "marmaray", "--klasor", str(tmp_path / "m"), "--hedef", hedef).returncode == 0
    c = calistir("saatler", "marmaray", "--modlar", "rail", "--hedef", hedef)
    assert c.returncode == 0, c.stderr
    assert "Her gün   Halkalı -> Gebze | 70 sefer | 05:58 - 23:28 | en sık aralık 15 dk" in c.stdout
    assert "Cum-Cts   Halkalı -> Gebze | 4 sefer | 23:58 - 25:28 | en sık aralık 30 dk (%100)" in c.stdout
    assert "Her gün   Ataköy -> Pendik | 119 sefer | 06:09 - 21:54 | en sık aralık 8 dk" in c.stdout
    h = calistir("saatler", "marmaray", "--hat", "marmaray", "--en-az-sefer", "1000", "--hedef", hedef)
    assert h.returncode == 0 and "eşleşen hat/sefer yok" in h.stdout

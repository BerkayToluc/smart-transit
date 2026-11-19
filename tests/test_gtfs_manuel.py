"""Elle tanımlı besleme (Marmaray): kural doğrulama, GTFS üretimi, resmi tarifeyle tutarlılık,
yükleme ve komut satırı. Gerçek tanım: data/marmaray.json."""
import copy
import csv
import os
import subprocess
import sys

import pytest
from sqlalchemy import func, select

from app.gtfs import build, loader, manual
from app.gtfs.feeds import MARMARAY
from app.gtfs.models import (
    GtfsCalendar, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTrip,
)
from app.gtfs.reader import parse_time
from app.gtfs.rules import expand_frequency_starts, service_runs_on_weekday

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TANIM_YOLU = os.path.join(KOK, "data", "marmaray.json")


def sa(h, d=0):
    return h * 3600 + d * 60


@pytest.fixture(scope="module")
def tanim():
    return manual.tanim_oku(TANIM_YOLU)


@pytest.fixture
def uretilen(tmp_path, tanim):
    klasor = tmp_path / "marmaray"
    manual.gtfs_uret(tanim, str(klasor))
    return str(klasor)


def oku(klasor, ad):
    with open(os.path.join(klasor, f"{ad}.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def baslangiclar(klasor, trip_id):
    """Bir şablon seferin frequency pencerelerinden çıkan tüm kalkış saatleri (saniye)."""
    s = set()
    for r in oku(klasor, "frequencies"):
        if r["trip_id"] == trip_id:
            s.update(expand_frequency_starts(parse_time(r["start_time"]), parse_time(r["end_time"]), int(r["headway_secs"])))
    return sorted(s)


# --- kalkış pencereleri ------------------------------------------------------------------------
def test_pencere_izgara_son_seferle_ortusur():
    assert manual.kalkis_pencereleri(sa(5, 58), sa(22, 58), 900) == [(sa(5, 58), sa(22, 58) + 1, 900)]


def test_pencere_son_izgara_sona_cok_yakinsa_degistirilir():
    # 06:09'dan her 8 dk, son tren 21:54: ızgara 21:53'e denk gelir; art arda iki tren olmasın
    p = manual.kalkis_pencereleri(sa(6, 9), sa(21, 54), 480)
    assert p == [(sa(6, 9), sa(21, 53), 480), (sa(21, 54), sa(21, 54) + 1, 480)]


def test_pencere_son_sefer_izgaradan_uzaksa_eklenir():
    p = manual.kalkis_pencereleri(sa(6, 9), sa(20, 39), 480)       # ızgara 20:33'e kadar, son tren 20:39
    assert p == [(sa(6, 9), sa(20, 33) + 1, 480), (sa(20, 39), sa(20, 39) + 1, 480)]


def test_pencere_tek_sefer():
    assert manual.kalkis_pencereleri(sa(23, 28), sa(23, 28), 1800) == [(sa(23, 28), sa(23, 28) + 1, 1800)]


def test_pencere_aralik_toplam_surenin_icinden_uzunsa_ilk_ve_son_korunur():
    assert manual.kalkis_pencereleri(100, 103, 600) == [(100, 101, 600), (103, 104, 600)]


def test_pencere_gecersiz():
    with pytest.raises(ValueError):
        manual.kalkis_pencereleri(100, 50, 60)
    with pytest.raises(ValueError):
        manual.kalkis_pencereleri(100, 200, 0)


@pytest.mark.parametrize("ilk, son, ar", [(sa(5, 58), sa(22, 58), 900), (sa(6, 9), sa(21, 54), 480),
                                          (sa(6, 9), sa(20, 39), 480), (sa(20, 50), sa(22, 39), 480),
                                          (sa(6, 5), sa(22, 50), 900), (sa(23, 58), sa(25, 28), 1800)])
def test_pencereler_ilk_ve_son_seferi_tam_verir(ilk, son, ar):
    starts = sorted({s for b, e, h in manual.kalkis_pencereleri(ilk, son, ar) for s in expand_frequency_starts(b, e, h)})
    assert starts[0] == ilk and starts[-1] == son
    araliklar = [b - a for a, b in zip(starts, starts[1:])]
    assert all(ar // 2 <= x <= ar * 1.5 for x in araliklar)       # art arda çok yakın ya da çok uzak tren yok


# --- tanım doğrulama ---------------------------------------------------------------------------
def test_gercek_tanim_gecerli(tanim):
    manual.dogrula(tanim)
    assert len(tanim["istasyonlar"]) == 43
    assert tanim["besleme"]["veri_tarihi"] == "2026-05-05"


def degistir(fn):
    def uygula(t):
        t = copy.deepcopy(t)
        fn(t)
        return t
    return uygula


@pytest.mark.parametrize("bozucu, beklenen", [
    (lambda t: t.pop("kaliplar"), "'kaliplar' bölümü yok"),
    (lambda t: t["istasyonlar"][5].update(id=t["istasyonlar"][4]["id"]), "tekrarlanan id"),
    (lambda t: t["istasyonlar"][5].update(id="Büyük Harf"), "id küçük harf"),
    (lambda t: t["istasyonlar"][5].update(enlem=10.0), "enlem İstanbul bölgesinde değil"),
    (lambda t: t["istasyonlar"][5].update(boylam=99.0), "boylam İstanbul bölgesinde değil"),
    (lambda t: t["istasyonlar"][5].update(ofset_sn=t["istasyonlar"][4]["ofset_sn"]), "ofset_sn artmalı"),
    (lambda t: t["istasyonlar"][5].update(ofset_sn=-3), "ofset_sn"),
    (lambda t: t["hizmetler"]["her_gun"].update(gunler=[0] * 7), "en az bir 1"),
    (lambda t: t["hizmetler"]["her_gun"].update(gunler=[1, 1]), "7 elemanlı"),
    (lambda t: t["kaliplar"][0].update(hat="yok"), "bilinmeyen hat"),
    (lambda t: t["kaliplar"][0].update(yon=2), "yon 0 ya da 1"),
    (lambda t: t["kaliplar"][0].update(nereden="yok"), "bilinmeyen istasyon"),
    (lambda t: t["kaliplar"][0].update(nereye=t["kaliplar"][0]["nereden"]), "nereden ve nereye aynı"),
    (lambda t: t["kaliplar"][0]["seferler"][0].update(hizmet="yok"), "bilinmeyen hizmet"),
    (lambda t: t["kaliplar"][0]["seferler"][0]["araliklar"][0].update(ilk="25:99"), "geçersiz saat"),
    (lambda t: t["kaliplar"][0]["seferler"][0]["araliklar"][0].update(ilk="23:00", son="22:00"), "önce"),
    (lambda t: t["kaliplar"][0]["seferler"][0]["araliklar"][0].update(aralik_dk=0), "aralik_dk"),
    (lambda t: t["kaliplar"].append(copy.deepcopy(t["kaliplar"][0])), "tekrarlanan id"),
])
def test_dogrulama_hatalari(tanim, bozucu, beklenen):
    t = copy.deepcopy(tanim)
    bozucu(t)
    with pytest.raises(ValueError, match=beklenen):
        manual.dogrula(t)


def test_dogrulama_tum_sorunlari_birlikte_bildirir(tanim):
    t = copy.deepcopy(tanim)
    t["istasyonlar"][5]["enlem"] = 10.0
    t["kaliplar"][0]["yon"] = 2
    with pytest.raises(ValueError) as e:
        manual.dogrula(t)
    assert "enlem" in str(e.value) and "yon 0 ya da 1" in str(e.value)


def test_gtfs_uret_gecersiz_tanimda_dosya_yazmaz(tmp_path, tanim):
    t = copy.deepcopy(tanim)
    t["kaliplar"][0]["yon"] = 5
    with pytest.raises(ValueError):
        manual.gtfs_uret(t, str(tmp_path / "x"))
    assert not (tmp_path / "x").exists()


# --- üretilen GTFS ---------------------------------------------------------------------------------
def test_uretilen_dosyalar_ve_sayilar(tmp_path, tanim):
    sayim = manual.gtfs_uret(tanim, str(tmp_path / "m"))
    assert sayim == {"agency": 1, "calendar": 2, "routes": 2, "trips": 7, "stop_times": 244,
                     "frequencies": 12, "stops": 43}


def test_uretilen_seferler_ve_istasyon_sayilari(uretilen):
    sayi = {}
    for r in oku(uretilen, "stop_times"):
        sayi[r["trip_id"]] = sayi.get(r["trip_id"], 0) + 1
    assert sayi == {
        "halkali_gebze_her_gun": 43, "halkali_gebze_cuma_cumartesi_gecesi": 43,
        "gebze_halkali_her_gun": 43, "gebze_halkali_cuma_cumartesi_gecesi": 43,
        "atakoy_pendik_her_gun": 25, "pendik_atakoy_her_gun": 25, "pendik_zeytinburnu_her_gun": 22}
    trips = {r["trip_id"]: r for r in oku(uretilen, "trips")}
    assert trips["halkali_gebze_her_gun"]["trip_headsign"] == "Gebze"
    assert trips["pendik_zeytinburnu_her_gun"]["trip_headsign"] == "Zeytinburnu"
    assert trips["pendik_zeytinburnu_her_gun"]["direction_id"] == "1"


def test_ana_hat_kalkislari(uretilen):
    hg = baslangiclar(uretilen, "halkali_gebze_her_gun")
    assert (hg[0], hg[-1], len(hg)) == (sa(5, 58), sa(23, 28), 70)       # 05:58 ... 22:58 (69) + 23:28
    assert hg[-2] == sa(22, 58) and hg[-1] - hg[-2] == 1800              # son 15 dk'lık tren 22:58, ardından 30 dk
    assert all(b - a == 900 for a, b in zip(hg[:68], hg[1:69]))
    gh = baslangiclar(uretilen, "gebze_halkali_her_gun")
    assert (gh[0], gh[-1], len(gh)) == (sa(6, 5), sa(23, 20), 69)        # 06:05 ... 22:50 (68) + 23:20
    assert gh[-2] == sa(22, 50)


def test_cuma_cumartesi_gecesi_24_saati_asar(uretilen):
    assert baslangiclar(uretilen, "halkali_gebze_cuma_cumartesi_gecesi") == [sa(23, 58), sa(24, 28), sa(24, 58), sa(25, 28)]
    assert baslangiclar(uretilen, "gebze_halkali_cuma_cumartesi_gecesi") == [sa(23, 50), sa(24, 20), sa(24, 50), sa(25, 20)]
    # resmi tarifedeki "hafta sonu son tren" 01:28 ve 01:20 ile örtüşür
    assert sa(25, 28) == sa(1, 28) + 86400 and sa(25, 20) == sa(1, 20) + 86400


def test_kisa_hat_kalkislari(uretilen):
    ap = baslangiclar(uretilen, "atakoy_pendik_her_gun")
    assert (ap[0], ap[-1], len(ap)) == (sa(6, 9), sa(21, 54), 119)
    pa = baslangiclar(uretilen, "pendik_atakoy_her_gun")
    assert (pa[0], pa[-1], len(pa)) == (sa(6, 9), sa(20, 39), 110)
    pz = baslangiclar(uretilen, "pendik_zeytinburnu_her_gun")
    assert (pz[0], pz[-1], len(pz)) == (sa(20, 50), sa(22, 39), 15)
    assert pz[0] >= sa(20, 50)                                             # "20:50'den sonra kalkan trenler"


def test_takvim_cuma_cumartesi_gecesi_yalniz_cuma_ve_cumartesi(uretilen):
    takvim = {r["service_id"]: r for r in oku(uretilen, "calendar")}
    gece = takvim["cuma_cumartesi_gecesi"]
    assert [int(gece[g]) for g in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")] \
        == [0, 0, 0, 0, 1, 1, 0]
    assert all(takvim["her_gun"][g] == "1" for g in ("monday", "sunday"))
    assert takvim["her_gun"]["end_date"] == "20991231"                      # süresi dolmuş tarih göstermesin


# --- resmi tarifeyle tutarlılık -------------------------------------------------------------------
# TCDD 5 Mayıs 2026 tarifesi, "son tren" sütunu: her istasyondaki saat (dakikaya yuvarlanmış).
RESMI = {
    "gebze_halkali_her_gun": "23:20 23:22 23:24 23:26 23:28".split(),
    "halkali_gebze_her_gun": "23:28 23:31 23:33 23:36 23:38".split(),
    "atakoy_pendik_her_gun": ("21:54 21:57 21:59 22:02 22:04 22:08 22:11 22:15 22:19 22:22 22:24 22:26 22:28 22:31 "
                              "22:33 22:36 22:38 22:40 22:42 22:45 22:47 22:49 22:51 22:54").split(),
    "pendik_atakoy_her_gun": ("20:39 20:42 20:45 20:47 20:49 20:51 20:54 20:56 20:58 21:00 21:03 21:05 21:08 21:10 "
                              "21:12 21:15 21:18 21:22 21:26 21:29 21:33 21:35 21:38 21:40").split(),
}


@pytest.mark.parametrize("trip_id", sorted(RESMI))
def test_istasyon_sureleri_resmi_tarifeyle_tutarli(uretilen, trip_id):
    resmi = [parse_time(s) for s in RESMI[trip_id]]
    satirlar = sorted((r for r in oku(uretilen, "stop_times") if r["trip_id"] == trip_id), key=lambda r: int(r["stop_sequence"]))
    bizim = [parse_time(r["arrival_time"]) for r in satirlar][:len(resmi)]
    farklar = [abs((bizim[i] - bizim[0]) - (resmi[i] - resmi[0])) for i in range(len(resmi))]
    assert max(farklar) <= 210, f"en büyük fark {max(farklar) / 60:.1f} dk"       # ≤ 3,5 dk (resmi saatler dakikaya yuvarlı)
    assert sum(farklar) / len(farklar) <= 75                                       # ortalama ≤ 1,25 dk


def test_ters_yon_sureleri_simetrik(uretilen):
    ileri = {r["stop_id"]: parse_time(r["arrival_time"]) for r in oku(uretilen, "stop_times") if r["trip_id"] == "halkali_gebze_her_gun"}
    geri = {r["stop_id"]: parse_time(r["arrival_time"]) for r in oku(uretilen, "stop_times") if r["trip_id"] == "gebze_halkali_her_gun"}
    toplam = ileri["gebze"]
    assert toplam == 6693                                                          # Halkalı -> Gebze 111,5 dk
    assert all(geri[k] == toplam - ileri[k] for k in ileri)


# --- veritabanına yükleme ----------------------------------------------------------------------------
def test_marmaray_yukleme(oturum, uretilen):
    ozet = loader.load_feed(oturum, uretilen, MARMARAY)
    assert (ozet["route"], ozet["trip"], ozet["stop"], ozet["stop_time"], ozet["frequency"], ozet["calendar"]) \
        == (2, 7, 43, 244, 12, 2)
    assert ozet["stop_invalid_coordinates"] == 0 and ozet["stop_time_duplicate"] == 0
    rotalar = {r.id: r for r in oturum.scalars(select(GtfsRoute).where(GtfsRoute.feed_id == "marmaray"))}
    assert set(rotalar) == {"marmaray:ana", "marmaray:kisa"}
    assert all(r.mode == "rail" and r.short_name == "Marmaray" for r in rotalar.values())
    assert oturum.get(GtfsFeed, "marmaray").data_date.isoformat() == "2026-05-05"
    assert oturum.get(GtfsStop, "marmaray:uskudar").name == "Üsküdar"
    assert oturum.get(GtfsTrip, "marmaray:pendik_zeytinburnu_her_gun").headsign == "Zeytinburnu"
    gece = oturum.get(GtfsCalendar, "marmaray:cuma_cumartesi_gecesi")
    assert service_runs_on_weekday(gece, 4) and service_runs_on_weekday(gece, 5)
    assert not service_runs_on_weekday(gece, 0) and not service_runs_on_weekday(gece, 6)
    # gece yarısını aşan frekans penceresi saniye olarak saklanır (25:28 = 91680)
    en_gec = oturum.execute(select(func.max(GtfsFrequency.end_secs)).where(GtfsFrequency.feed_id == "marmaray")).scalar_one()
    assert en_gec == sa(25, 28) + 1
    assert oturum.execute(select(func.count()).select_from(GtfsStopTime)
                          .where(GtfsStopTime.trip_id.like("marmaray:%"))).scalar_one() == 244


def test_hat_ozeti(oturum, uretilen):
    loader.load_feed(oturum, uretilen, MARMARAY)
    ozet = {k["uzun_ad"]: k for k in build.hat_ozeti(oturum, "marmaray")}
    ana, kisa = ozet["Halkalı - Gebze"], ozet["Ataköy - Pendik"]
    assert (ana["ilk_durak"], ana["son_durak"], ana["durak_sayisi"], ana["sure_dk"]) == ("Halkalı", "Gebze", 43, 111.5)
    assert (kisa["ilk_durak"], kisa["son_durak"], kisa["durak_sayisi"]) == ("Ataköy", "Pendik", 25)
    assert kisa["sure_dk"] == pytest.approx(63.2, abs=0.05)
    assert ana["sefer"] == 4 and ana["aralikli"] == 4 and ana["mod"] == "rail"
    assert build.hat_ozeti(oturum, "marmaray", modlar=["metro"]) == []
    metin = build.hat_ozeti_metni(build.hat_ozeti(oturum, "marmaray"))
    assert "Halkalı -> Gebze | 43 durak | 111.5 dk | 4 sefer (4 aralıklı)" in metin


# --- build.py / komut satırı ---------------------------------------------------------------------------
def test_kayit_ve_indir_elle_tanimli_icin_dosya_uretir(tmp_path):
    kaynak = build.BESLEMELER["marmaray"]
    assert kaynak.manuel and os.path.exists(kaynak.manuel) and kaynak.config is MARMARAY
    mesajlar = []
    assert build.indir("marmaray", str(tmp_path / "m"), log=mesajlar.append) == []   # indirilen dosya yok
    assert (tmp_path / "m" / "stop_times.csv").exists() and any("data" in m and "marmaray.json" in m for m in mesajlar)
    with pytest.raises(ValueError, match="elle tanımlı"):
        build.manuel_uret("iett")


def calistir(*args):
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    return subprocess.run([sys.executable, os.path.join(KOK, "scripts", "build_gtfs.py"), *args],
                          cwd=KOK, capture_output=True, text=True, env=env, timeout=120)


def test_komut_satiri_marmaray(tmp_path):
    hedef = f"sqlite:///{tmp_path / 'gtfs.db'}"
    klasor = str(tmp_path / "m")
    c = calistir("yukle", "marmaray", "--klasor", klasor, "--hedef", hedef)
    assert c.returncode == 0, c.stderr
    assert "kurallardan GTFS dosyaları üretiliyor" in c.stdout and "trip=7" not in c.stdout
    assert "hat 2, sefer 7, durak 43, durak saati 244" in c.stdout
    h = calistir("hatlar", "marmaray", "--hedef", hedef)
    assert h.returncode == 0, h.stderr
    assert "Halkalı -> Gebze | 43 durak | 111.5 dk" in h.stdout and "Ataköy -> Pendik | 25 durak" in h.stdout
    assert "rail" in h.stdout
    assert calistir("hatlar", "marmaray", "--modlar", "metro", "--hedef", hedef).stdout.strip().endswith("(seçilen modlarda hat yok)")

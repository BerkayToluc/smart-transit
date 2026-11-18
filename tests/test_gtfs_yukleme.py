"""app/gtfs.loader: sahte beslemelerle veritabanına yükleme (SQLite, yabancı anahtarlar AÇIK).

İki sahte besleme gerçek verideki sorunları taklit eder ve KİMLİKLERİ bilerek çakışır:
  * "ibb": Windows-1254, virgüllü, Marmaray (agency 4, route_type 1), turistik vapur, minibüs,
    gece yarısını aşan sefer, aralıklı seferler, geçersiz koordinatlı durak, üst istasyon;
  * "iett": UTF-8, ';' ayraçlı, isimlerde çift kodlama bozulması, bozuk koordinatlar.
"""
from datetime import date

import pytest
from sqlalchemy import func, inspect, select

import main
from app.gtfs import loader
from app.gtfs.feeds import IBB_MULTIMODAL, IETT, FeedConfig
from tests.conftest import yaz
from app.gtfs.models import (
    GtfsAgency, GtfsCalendar, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTrip,
)


@pytest.fixture
def ibb_klasoru(tmp_path):
    d = tmp_path / "ibb"
    d.mkdir()
    k = "cp1254"
    yaz(d / "agency.csv", [
        ["agency_id", "agency_name", "agency_url", "agency_timezone"],
        ["4", "TCDD", "http://tcdd", "Europe/Istanbul"], ["11", "Metro İstanbul", "", ""],
        ["6", "Şehirhatları A.Ş.", "", ""], ["37", "Minibus", "", ""],
    ], kodlama=k)
    yaz(d / "calendar.csv", [
        ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
         "start_date", "end_date"],
        ["100", 1, 1, 1, 1, 1, 0, 0, "20221231", "20241231"],
        ["101", 0, 0, 0, 0, 0, 0, 0, "20190506", "20190603"],     # günsüz (2019 Ramazan)
    ], kodlama=k)
    yaz(d / "routes.csv", [
        ["route_id", "agency_id", "route_short_name", "route_long_name", "route_desc", "route_type"],
        ["r1", "4", "Marmaray", "GEBZE-HALKALI", "", 1],
        ["r2", "11", "M2", "YENİKAPI - HACIOSMAN", "", 1],
        ["r3", "6", "KDK-EMN", "KADIKÖY - EMİNÖNÜ", "", 4],
        ["r4", "6", "BÖZ-1", "BOĞAZA GİDİŞ", "", 4],              # turistik -> elenir
        ["r5", "37", "MB1", "ŞİŞLİ MİNİBÜS", "", 9],              # minibüs -> elenir
        ["r6", "11", "T1", "BAĞCILAR - KABATAŞ", "", 0],
        ["r7", "11", "XX", "TİPSİZ HAT", "", ""],                  # tipi bilinmeyen -> elenir
    ], kodlama=k)
    yaz(d / "trips.csv", [
        ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id", "shape_id"],
        ["r2", "100", "t1", "HACIOSMAN", 0, "sh1"], ["r2", "100", "t2", "HACIOSMAN", 0, ""],
        ["r1", "100", "t3", "GEBZE", 0, ""], ["r3", "100", "t4", "EMİNÖNÜ", 0, ""],
        ["r4", "100", "t5", "TUR", 0, ""], ["r5", "100", "t6", "ŞİŞLİ", 0, ""],
    ], kodlama=k)
    yaz(d / "stop_times.csv", [
        ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
        ["t1", "06:00:00", "06:00:00", "s1", 1], ["t1", "06:05:00", "06:05:00", "s2", 2],
        ["t1", "06:10:00", "06:10:00", "s3", 3],
        ["t2", "00:00:00", "00:00:00", "s1", 1], ["t2", "00:03:00", "00:03:00", "s2", 2],   # frekans şablonu
        ["t3", "25:20:00", "25:20:00", "s2", 1], ["t3", "25:40:00", "25:40:00", "s4", 2],   # gece yarısını aşar
        ["t4", "08:00:00", "08:00:00", "s5", 1], ["t4", "08:20:00", "08:20:00", "s6", 2],   # s6 geçersiz koordinat
        ["t5", "09:00:00", "09:00:00", "s7", 1], ["t6", "09:00:00", "09:00:00", "s8", 1],
    ], kodlama=k)
    yaz(d / "stops.csv", [
        ["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon", "location_type",
         "parent_station", "wheelchair_boarding"],
        ["s1", "1", "Yenikapı", "", "41.0048", "28.9496", 0, "", 1],
        ["s2", "2", "Üsküdar", "", "41.0257", "29.0138", 0, "", 0],
        ["s3", "3", "Taksim", "", "41.0370", "28.9850", 0, "P1", 2],
        ["P1", "", "Taksim İstasyonu", "", "41.0371", "28.9851", 1, "", ""],
        ["s4", "4", "Gebze", "", "40.7842", "29.4096", 0, "", ""],
        ["s5", "5", "Kadıköy İskele", "", "40.9918", "29.0227", 0, "", ""],
        ["s6", "6", "Eminönü İskele", "", "abc", "def", 0, "", ""],          # geçersiz koordinat
        ["s7", "7", "Tur İskelesi", "", "41.0", "29.0", 0, "", ""],
        ["s8", "8", "Minibüs Durağı", "", "41.1", "29.1", 0, "", ""],
        ["s9", "9", "Kullanılmayan", "", "41.2", "29.2", 0, "", ""],
    ], kodlama=k)
    yaz(d / "frequencies.csv", [
        ["trip_id", "start_time", "end_time", "headway_secs", "exact_times"],
        ["t2", "06:00:00", "07:00:00", 900, 0], ["t2", "07:00:00", "08:00:00", 7200, 0],
        ["t5", "09:00:00", "10:00:00", 600, 0],                                  # elenen sefer -> yüklenmez
    ], kodlama=k)
    return str(d)


@pytest.fixture
def iett_klasoru(tmp_path):
    d = tmp_path / "iett"
    d.mkdir()
    yaz(d / "agency.csv", [["agency_id", "agency_name"], ["1", "İETT"]], ayrac=";")
    yaz(d / "calendar.csv", [["service_id", "monday", "tuesday", "wednesday", "thursday", "friday",
                              "saturday", "sunday", "start_date", "end_date"],
                             ["6", 1, 1, 1, 1, 1, 1, 1, "20260101", "20261231"]], ayrac=";")
    yaz(d / "routes.csv", [["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
                           ["r1", "1", "1", "KADIKÃ–Y - KÄ°RAZLITEPE", 3]], ayrac=";")        # bozuk kodlama
    yaz(d / "trips.csv", [["trip_id", "route_id", "service_id", "trip_headsign", "direction_id"],
                          ["t1", "r1", "6", "KÄ°RAZLITEPE", 1]], ayrac=";")
    yaz(d / "stop_times.csv", [["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
                               ["t1", "07:00:00", "07:00:00", "s1", 1], ["t1", "07:10:00", "07:10:00", "s2", 2]],
        ayrac=";")
    yaz(d / "stops.csv", [["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon", "location_type"],
                          ["s1", "100001", "RIFAT ILGAZ CADDESİ", "", "410.191.700.005.564", "286.843.529.999.755", 0],
                          ["s2", "100002", "AVCILAR", "", "410.190.470.005.563", "286.846.599.999.755", 0]],
        ayrac=";")
    return str(d)


def say(oturum, model, **filtre):
    sorgu = select(func.count()).select_from(model)
    for ad, deger in filtre.items():
        sorgu = sorgu.where(getattr(model, ad) == deger)
    return oturum.execute(sorgu).scalar_one()


# --- şema ---------------------------------------------------------------------------
def test_tablolar_olusur_ve_mevcut_tablolar_durur():
    adlar = set(inspect(main.engine).get_table_names())
    yeni = {"gtfs_feed", "gtfs_agency", "gtfs_stop", "gtfs_route", "gtfs_calendar", "gtfs_calendar_date",
            "gtfs_trip", "gtfs_stop_time", "gtfs_frequency", "gtfs_transfer"}
    assert yeni <= adlar
    assert {"hatlar", "duraklar", "otobusler", "guzergah_noktalari"} <= adlar   # canlı takip tabloları aynen


# --- yükleme: ibb -----------------------------------------------------------------------
def test_ibb_yukleme_sayilari(oturum, ibb_klasoru):
    ozet = loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    assert ozet["agency"] == 4
    assert ozet["calendar"] == 2
    assert ozet["route"] == 4                      # Marmaray, M2, KDK-EMN, T1
    assert ozet["route_excluded"] == 3             # turistik vapur, minibüs, tipsiz
    assert ozet["trip"] == 4                       # t1..t4 (t5, t6 elenen hatların)
    assert ozet["stop"] == 6                       # s1 s2 s3 P1 s4 s5 (s6 geçersiz, s7-s9 kullanılmıyor)
    assert ozet["stop_invalid_coordinates"] == 1
    assert ozet["stop_time"] == 8                  # 3 + 2 + 2 + 1 (t4'ün s6 durağı atlanır)
    assert ozet["stop_time_unknown_stop"] == 1
    assert ozet["frequency"] == 2                  # t5'in aralığı yüklenmez
    feed = oturum.get(GtfsFeed, "ibb")
    assert feed.name == IBB_MULTIMODAL.name and "Metro İstanbul 09.07.2020" in feed.source_note


def test_ibb_modlar_ve_onekli_kimlikler(oturum, ibb_klasoru):
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    modlar = {r.id: r.mode for r in oturum.scalars(select(GtfsRoute).where(GtfsRoute.feed_id == "ibb"))}
    assert modlar == {"ibb:r1": "rail", "ibb:r2": "metro", "ibb:r3": "ferry", "ibb:r6": "tram"}
    assert oturum.get(GtfsRoute, "ibb:r1").route_type == 1     # ham tip korunur (Marmaray "metro" geliyordu)
    assert oturum.get(GtfsRoute, "ibb:r2").agency_id == "ibb:11"
    assert oturum.get(GtfsRoute, "ibb:r4") is None             # turistik vapur yok
    assert oturum.get(GtfsRoute, "ibb:r5") is None             # minibüs yok


def test_ibb_cp1254_isimler_dogru(oturum, ibb_klasoru):
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    assert oturum.get(GtfsStop, "ibb:s2").name == "Üsküdar"
    assert oturum.get(GtfsRoute, "ibb:r3").long_name == "KADIKÖY - EMİNÖNÜ"
    assert oturum.get(GtfsAgency, "ibb:6").name == "Şehirhatları A.Ş."


def test_ibb_duraklar_ust_istasyon_ve_erisilebilirlik(oturum, ibb_klasoru):
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    s3, p1 = oturum.get(GtfsStop, "ibb:s3"), oturum.get(GtfsStop, "ibb:P1")
    assert s3.parent_station == "ibb:P1" and p1.location_type == 1 and p1.parent_station is None
    assert (s3.wheelchair_boarding, oturum.get(GtfsStop, "ibb:s1").wheelchair_boarding) == (2, 1)
    assert oturum.get(GtfsStop, "ibb:s6") is None              # geçersiz koordinat
    assert oturum.get(GtfsStop, "ibb:s9") is None              # hiçbir sefer kullanmıyor
    assert oturum.get(GtfsStop, "ibb:s8") is None              # yalnızca elenen minibüs hattı kullanıyor


def test_ibb_saatler_gece_yarisini_asar(oturum, ibb_klasoru):
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    t3 = oturum.scalars(select(GtfsStopTime).where(GtfsStopTime.trip_id == "ibb:t3")
                        .order_by(GtfsStopTime.stop_sequence)).all()
    assert [(x.arrival_secs, x.departure_secs) for x in t3] == [(91200, 91200), (92400, 92400)]   # 25:20, 25:40
    t4 = oturum.scalars(select(GtfsStopTime).where(GtfsStopTime.trip_id == "ibb:t4")).all()
    assert [x.stop_id for x in t4] == ["ibb:s5"]


def test_ibb_takvim_ve_frekanslar(oturum, ibb_klasoru):
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    hafta_ici = oturum.get(GtfsCalendar, "ibb:100")
    assert (hafta_ici.monday, hafta_ici.friday, hafta_ici.saturday) == (True, True, False)
    assert hafta_ici.end_date == date(2024, 12, 31)            # ham tarih saklanır (planlama yok sayar)
    gunsuz = oturum.get(GtfsCalendar, "ibb:101")
    assert not any([gunsuz.monday, gunsuz.tuesday, gunsuz.saturday, gunsuz.sunday])
    f = oturum.scalars(select(GtfsFrequency).where(GtfsFrequency.feed_id == "ibb")
                       .order_by(GtfsFrequency.start_secs)).all()
    assert [(x.trip_id, x.start_secs, x.end_secs, x.headway_secs) for x in f] == [
        ("ibb:t2", 21600, 25200, 900), ("ibb:t2", 25200, 28800, 7200)]


# --- yükleme: iett + çakışan kimlikler ------------------------------------------------------
def test_iett_bozuk_kodlama_ve_koordinatlar_duzelir(oturum, iett_klasoru):
    ozet = loader.load_feed(oturum, iett_klasoru, IETT)
    assert (ozet["route"], ozet["stop"], ozet["stop_time"]) == (1, 2, 2)
    assert oturum.get(GtfsRoute, "iett:r1").long_name == "KADIKÖY - KİRAZLITEPE"
    assert oturum.get(GtfsRoute, "iett:r1").mode == "bus"
    assert oturum.get(GtfsTrip, "iett:t1").headsign == "KİRAZLITEPE"
    s1 = oturum.get(GtfsStop, "iett:s1")
    assert s1.lat == pytest.approx(41.0191700005564) and s1.lon == pytest.approx(28.6843529999755)
    assert s1.name == "RIFAT ILGAZ CADDESİ"
    assert oturum.get(GtfsFeed, "iett").data_date == date(2026, 4, 21)


def test_cakisan_kimlikler_iki_besleme_birlikte(oturum, ibb_klasoru, iett_klasoru):
    # İki beslemede de "r1", "s1", "t1" ham kimlikleri var; önek sayesinde karışmaz.
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    loader.load_feed(oturum, iett_klasoru, IETT)
    assert oturum.get(GtfsRoute, "ibb:r1").long_name == "GEBZE-HALKALI"
    assert oturum.get(GtfsRoute, "iett:r1").long_name == "KADIKÖY - KİRAZLITEPE"
    assert oturum.get(GtfsStop, "ibb:s1").name == "Yenikapı"
    assert oturum.get(GtfsStop, "iett:s1").name == "RIFAT ILGAZ CADDESİ"
    assert say(oturum, GtfsStop, feed_id="ibb") == 6 and say(oturum, GtfsStop, feed_id="iett") == 2


# --- tekrar yükleme, geri alma, hatalar -----------------------------------------------------------
def test_tekrar_yukleme_cogaltmaz(oturum, ibb_klasoru):
    ilk = loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    ikinci = loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    assert ilk == ikinci
    assert say(oturum, GtfsStop, feed_id="ibb") == 6
    assert say(oturum, GtfsTrip, feed_id="ibb") == 4
    assert say(oturum, GtfsFeed, id="ibb") == 1


def test_tekrar_yukleme_digeri_besleme_etkilenmez(oturum, ibb_klasoru, iett_klasoru):
    loader.load_feed(oturum, iett_klasoru, IETT)
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    assert say(oturum, GtfsStop, feed_id="iett") == 2
    assert say(oturum, GtfsRoute, feed_id="iett") == 1


def test_hata_olursa_geri_alinir(oturum, ibb_klasoru, monkeypatch):
    loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    once = say(oturum, GtfsStopTime)

    def patla(_deger):
        raise RuntimeError("yükleme sırasında hata")
    monkeypatch.setattr(loader.reader, "parse_time", patla)
    with pytest.raises(RuntimeError, match="yükleme sırasında hata"):
        loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)
    monkeypatch.undo()
    oturum.expire_all()
    assert say(oturum, GtfsStopTime) == once            # eski veri korunmuş (silme geri alındı)
    assert say(oturum, GtfsFeed, id="ibb") == 1


def test_eksik_dosya_ve_klasor(oturum, ibb_klasoru, tmp_path):
    with pytest.raises(FileNotFoundError):
        loader.load_feed(oturum, str(tmp_path / "yok"), IBB_MULTIMODAL)
    import os
    os.remove(os.path.join(ibb_klasoru, "stop_times.csv"))
    with pytest.raises(FileNotFoundError, match="stop_times"):
        loader.load_feed(oturum, ibb_klasoru, IBB_MULTIMODAL)


def test_isteğe_bagli_dosyalar_olmadan_yuklenir(oturum, iett_klasoru):
    import os
    os.remove(os.path.join(iett_klasoru, "calendar.csv"))     # calendar/frequencies/transfers isteğe bağlı
    ozet = loader.load_feed(oturum, iett_klasoru, FeedConfig(feed_id="iett2", name="x", fix_mojibake=True))
    assert ozet["calendar"] == 0 and ozet["frequency"] == 0 and ozet["route"] == 1


# --- gerçek verideki kusurlar ---------------------------------------------------------------
def test_kusurlu_iett_yukleme(oturum, iett_kusurlu):
    ozet = loader.load_feed(oturum, iett_kusurlu, IETT)
    assert ozet["route"] == 2 and ozet["route_excluded"] == 1       # KM41 elenir, boş route_id atlanır
    assert ozet["trip"] == 2
    assert oturum.get(GtfsRoute, "iett:r1").mode == "metrobus"
    assert oturum.get(GtfsRoute, "iett:r2").mode == "bus"
    assert oturum.get(GtfsRoute, "iett:r3") is None
    assert (ozet["stop"], ozet["stop_invalid_coordinates"], ozet["stop_not_found"]) == (2, 1, 1)
    assert oturum.get(GtfsStop, "iett:s2").name == "SÖĞÜTLÜÇEŞME"
    assert oturum.get(GtfsStop, "iett:s2").lat == pytest.approx(41.0)
    assert oturum.get(GtfsStop, "iett:s3") is None                   # kaymış satır yüklenmez
    # t1: 2 satır (tekrar atlandı), t2: yalnızca s1 (s3 bozuk, s9 yok)
    assert ozet["stop_time"] == 3
    assert ozet["stop_time_duplicate"] == 1
    assert ozet["stop_time_unknown_stop"] == 2


def test_excel_kirpmasi_tespit_edilir(oturum, iett_kusurlu, monkeypatch):
    # dosya tam Excel sınırı kadar veri satırı içeriyorsa (burada sınırı 7'ye indirdik) reddedilir
    monkeypatch.setattr(loader, "EXCEL_SATIR_SINIRI", 7)
    with pytest.raises(ValueError, match="Excel"):
        loader.load_feed(oturum, iett_kusurlu, IETT)


def test_excel_siniri_altinda_sorun_yok(oturum, iett_kusurlu):
    assert loader.EXCEL_SATIR_SINIRI == 1_048_575
    loader.load_feed(oturum, iett_kusurlu, IETT)

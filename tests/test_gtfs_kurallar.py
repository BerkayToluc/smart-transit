"""app/gtfs: okuyucu, mod eşleme, aralıklı seferler ve takvim kuralları (veritabanı gerekmez)."""
from datetime import date

import pytest

from app.gtfs import reader
from app.gtfs.feeds import IBB_MULTIMODAL, IETT, FeedConfig, _turistik_vapur
from app.gtfs.modes import ModeRules, classify_mode, mode_from_route_type
from app.gtfs.rules import (
    expand_frequency_starts, expand_frequency_trips, has_any_weekday, instantiate_trip_times,
    service_runs_on_weekday,
)
from app.gtfs.textfix import ascii_katla


def sa(s, d=0, sn=0):
    return s * 3600 + d * 60 + sn


# --- saat / tarih / sayı çözümleme --------------------------------------------
@pytest.mark.parametrize("ham, beklenen", [
    ("06:00:00", sa(6)), ("6:05:30", sa(6, 5, 30)), ("23:59:59", sa(23, 59, 59)),
    ("25:20:00", sa(25, 20)),             # gece yarısını aşan sefer
    ("08:15", sa(8, 15)),
    ("", None), (None, None), ("abc", None), ("12:99:00", None), ("-1:00:00", None),
])
def test_parse_time(ham, beklenen):
    assert reader.parse_time(ham) == beklenen


def test_parse_date():
    assert reader.parse_date("20221231") == date(2022, 12, 31)
    assert reader.parse_date("") is None
    assert reader.parse_date("2022123") is None
    assert reader.parse_date("20221399") is None


def test_parse_int():
    assert reader.parse_int("7") == 7
    assert reader.parse_int("", 5) == 5
    assert reader.parse_int(None) is None
    assert reader.parse_int("x", 0) == 0


@pytest.mark.parametrize("ham, lat", [
    ("40.7842492519915", 40.7842492519915),    # normal
    ("41,015", 41.015),                          # virgüllü ondalık
    ("410.191.700.005.564", 41.0191700005564),   # İETT bozuk biçimi
    ("410191700005564", 41.0191700005564),       # noktaları kaybolmuş
])
def test_parse_lat(ham, lat):
    assert reader.parse_lat(ham) == pytest.approx(lat)


def test_parse_lon_bozuk():
    assert reader.parse_lon("286.843.529.999.755") == pytest.approx(28.6843529999755)


@pytest.mark.parametrize("ham", [None, "", "  ", "abc", "99999"])
def test_parse_lat_gecersiz(ham):
    assert reader.parse_lat(ham) is None


def test_parse_lat_kisa_ama_gecerli_sayi_aynen_alinir():
    # "4" bozuk değil, geçerli bir sayı (4.0 derece); yalnızca aralık dışı/çözülemeyenler elenir
    assert reader.parse_lat("4") == 4.0


# --- kodlama ve ayraç ----------------------------------------------------------
def test_detect_encoding_utf8(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("ad\nKADIKÖY\n", encoding="utf-8")
    assert reader.detect_encoding(str(f)) == "utf-8-sig"


def test_detect_encoding_cp1254(tmp_path):
    f = tmp_path / "b.csv"
    f.write_bytes("ad\nBOĞAZ İSTİNYE ŞİŞLİ\n".encode("cp1254"))
    assert reader.detect_encoding(str(f)) == "cp1254"


def test_iter_rows_cp1254_virgul(tmp_path):
    f = tmp_path / "stops.csv"
    f.write_bytes("stop_id,stop_name\n1,Üsküdar\n2,Ayrılıkçeşmesi\n".encode("cp1254"))
    satirlar = list(reader.iter_rows(str(f)))
    assert [s["stop_name"] for s in satirlar] == ["Üsküdar", "Ayrılıkçeşmesi"]


def test_iter_rows_utf8_bom_noktalivirgul(tmp_path):
    f = tmp_path / "routes.csv"
    f.write_text("route_id;route_short_name\n1; 500T \n", encoding="utf-8-sig")
    assert list(reader.iter_rows(str(f))) == [{"route_id": "1", "route_short_name": "500T"}]


def test_iter_rows_dosya_yoksa_bos(tmp_path):
    assert list(reader.iter_rows(str(tmp_path / "yok.csv"))) == []


# --- mod eşleme ----------------------------------------------------------------
@pytest.mark.parametrize("tip, mod", [
    (0, "tram"), (1, "metro"), (2, "rail"), (3, "bus"), (4, "ferry"), (6, "cable_car"),
    (7, "funicular"), (9, "minibus"), (10, "taxi"),
    (109, "rail"), (401, "metro"), (700, "bus"), (900, "tram"), (1000, "ferry"), (1400, "funicular"),
    (None, "other"), (999999, "other"),
])
def test_mode_from_route_type(tip, mod):
    assert mode_from_route_type(tip) == mod


def test_marmaray_kurum_kuraliyla_rail():
    kurallar = ModeRules(agency_modes={"4": "rail"})
    assert classify_mode(1, agency_id="4", rules=kurallar) == "rail"
    assert classify_mode(1, agency_id="11", rules=kurallar) == "metro"


def test_hat_adi_kurali_kuraldan_once_gelir():
    kurallar = ModeRules(agency_modes={"1": "bus"}, name_modes=((r"^34[A-Z]*$", "metrobus"),))
    assert classify_mode(3, agency_id="1", short_name="34", rules=kurallar) == "metrobus"
    assert classify_mode(3, agency_id="1", short_name="34Z", rules=kurallar) == "metrobus"
    assert classify_mode(3, agency_id="1", short_name="500T", rules=kurallar) == "bus"


# --- besleme ayarları -----------------------------------------------------------
def test_feed_config_kimlik_dogrulama():
    with pytest.raises(ValueError):
        FeedConfig(feed_id="Büyük Harf", name="x")
    with pytest.raises(ValueError):
        FeedConfig(feed_id="x", name="x", exclude_modes=frozenset({"uzay"}))
    assert FeedConfig(feed_id="ibb", name="x").prefixed("123") == "ibb:123"


def test_onceden_tanimli_ayarlar_gecerli():
    assert IETT.fix_mojibake is True and IETT.feed_id == "iett"
    assert IBB_MULTIMODAL.mode_rules.agency_modes == {"4": "rail"}
    assert {"minibus", "taxi", "other"} <= IBB_MULTIMODAL.exclude_modes


@pytest.mark.parametrize("ad, turistik", [
    ("BOĞAZA GİDİŞ", True), ("BOĞAZDAN GELİŞ", True), ("Boğaza Gidiş", True),
    ("KISA BOĞAZ TURU", True), ("UZUN BOĞAZ TURU", True), ("ERGUVAN TURU", True),
    ("LALE FESTİVALİ (Kadıköy-Üsküdar-Emirgan)", True),
    ("KADIKÖY - EMİNÖNÜ", False), ("BOSTANCI - KARAKÖY - KABATAŞ", False), ("ÜSKÜDAR - EMİNÖNÜ", False),
])
def test_turistik_vapur_filtresi(ad, turistik):
    assert _turistik_vapur({"mode": "ferry", "short_name": "", "long_name": ad}) is turistik


def test_turistik_filtre_yalnizca_vapura_uygulanir():
    assert _turistik_vapur({"mode": "bus", "short_name": "", "long_name": "KISA BOĞAZ TURU"}) is False


def test_ascii_katla():
    assert ascii_katla("Boğaza Gidiş") == "BOGAZA GIDIS"
    assert ascii_katla("İÇMELER ışık") == "ICMELER ISIK"


# --- aralıklı seferler ------------------------------------------------------------
def test_frekans_normal_pencere():
    # 06:00-07:00, 15 dk -> 06:00, 06:15, 06:30, 06:45 (07:00 dahil değil)
    assert expand_frequency_starts(sa(6), sa(7), 900) == [sa(6), sa(6, 15), sa(6, 30), sa(6, 45)]


def test_frekans_aralik_pencereden_uzunsa_tek_sefer():
    # gerçek veriden: 08:30-19:00, 37800 sn -> yalnızca pencere başı
    assert expand_frequency_starts(sa(8, 30), sa(19), 37800) == [sa(8, 30)]
    assert expand_frequency_starts(sa(7, 55), sa(18, 30), 38100) == [sa(7, 55)]


def test_frekans_gecersiz():
    assert expand_frequency_starts(sa(7), sa(6), 900) == []
    with pytest.raises(ValueError):
        expand_frequency_starts(sa(6), sa(7), 0)


def test_sablon_seferi_kaydirma():
    sablon = [(sa(6), sa(6)), (sa(6, 5), sa(6, 6)), (sa(6, 10), None)]
    assert instantiate_trip_times(sablon, sa(8)) == [(sa(8), sa(8)), (sa(8, 5), sa(8, 6)), (sa(8, 10), None)]


def test_sablon_bos():
    assert instantiate_trip_times([], sa(8)) == []
    with pytest.raises(ValueError):
        instantiate_trip_times([(None, None)], sa(8))


def test_frekans_pencere_uclarinda_cift_sefer_olmaz():
    sablon = [(0, 0), (300, 300)]
    # 06:00-07:00 ve 07:00-08:00 pencereleri, 30 dk -> 06:00, 06:30, 07:00, 07:30 (07:00 bir kez)
    seferler = expand_frequency_trips(sablon, [(sa(6), sa(7), 1800), (sa(7), sa(8), 1800)])
    assert [s[0][1] for s in seferler] == [sa(6), sa(6, 30), sa(7), sa(7, 30)]
    assert seferler[0][1] == (300 + sa(6), 300 + sa(6))


def test_frekans_gece_yarisi_asimi():
    sablon = [(0, 0), (600, 600)]
    seferler = expand_frequency_trips(sablon, [(sa(23, 30), sa(25), 1800)])
    assert [s[0][1] for s in seferler] == [sa(23, 30), sa(24), sa(24, 30)]


# --- takvim ---------------------------------------------------------------------
HAFTA_ICI = {"monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1, "friday": 1,
             "saturday": 0, "sunday": 0}
GUNSUZ = {g: 0 for g in HAFTA_ICI}


def test_takvim_haftanin_gunleri():
    assert service_runs_on_weekday(HAFTA_ICI, 0) is True    # Pazartesi
    assert service_runs_on_weekday(HAFTA_ICI, 4) is True    # Cuma
    assert service_runs_on_weekday(HAFTA_ICI, 5) is False   # Cumartesi
    assert service_runs_on_weekday(HAFTA_ICI, 6) is False   # Pazar


def test_takvim_tarih_araligi_dikkate_alinmaz():
    eski = dict(HAFTA_ICI, start_date=date(2022, 12, 31), end_date=date(2024, 12, 31))
    assert service_runs_on_weekday(eski, 1) is True


def test_gunsuz_hizmet_hic_calismaz():
    assert has_any_weekday(GUNSUZ) is False
    assert all(not service_runs_on_weekday(GUNSUZ, g) for g in range(7))


def test_takvim_nesne_ve_gecersiz_gun():
    from types import SimpleNamespace
    assert service_runs_on_weekday(SimpleNamespace(**HAFTA_ICI), 2) is True
    with pytest.raises(ValueError):
        service_runs_on_weekday(HAFTA_ICI, 7)


# --- gerçek verideki bozulma kalıpları (docs/veri-kaynaklari.md) -----------------------
@pytest.mark.parametrize("bozuk, dogru", [
    ("SÃ–ÄžÃœTLÃœÃ‡EÅžME", "SÖĞÜTLÜÇEŞME"),          # Windows-1252 okuması
    ("SÖĞÜTLÜÇEÅ\x9eME", "SÖĞÜTLÜÇEŞME"),             # Latin-1 okuması (0x9E kontrol karakteri)
    ("ÇAĞDAÅ\x9eKENT", "ÇAĞDAŞKENT"),
    ("ERGÃœVAN", "ERGÜVAN"),
    ("EÄ\x9eÄ°TÄ°M", "EĞİTİM"),                         # Ğ de aynı biçimde bozulmuş
    ("GÜMÜÅYAKA", "GÜMÜŞYAKA"),                        # partneri kaybolmuş yetim "Å" -> Ş
    ("KARAÄ", "KARAĞ"),                                # yetim "Ä" -> Ğ
    ("ÅEHİT Â\xa0İBRAHİM", "ŞEHİT  İBRAHİM"),    # bozuk bölünmez boşluk
])
def test_mojibake_gercek_bozulmalar(bozuk, dogru):
    from app.gtfs.textfix import _mojibake_duzelt
    assert _mojibake_duzelt(bozuk) == dogru


def test_temizle_metin_bosluklari_sadelestirir():
    assert reader.temizle_metin("ŞEHİT Â\xa0İBRAHİM  YILMAZ", fix_mojibake=True) == "ŞEHİT İBRAHİM YILMAZ"
    assert reader.temizle_metin("  A   B ", fix_mojibake=False) == "A B"


@pytest.mark.parametrize("ham", ["4,12E+14", "4.10E+13", "2,83E+14"])
def test_bilimsel_gosterim_koordinat_degildir(ham):
    # Excel bozulması: hassasiyet kaybolmuş; "41.214" gibi sahte bir değere ÇEVRİLMEMELİ
    assert reader.parse_lat(ham) is None and reader.parse_lon(ham) is None


@pytest.mark.parametrize("ad, mod", [
    ("34", "metrobus"), ("34A", "metrobus"), ("34AS", "metrobus"), ("34BZ", "metrobus"),
    ("34Z", "metrobus"), ("34T", "metrobus"),
    ("340", "bus"), ("500T", "bus"), ("11", "bus"), ("134", "bus"), ("M34", "bus"),
])
def test_iett_metrobus_kurali(ad, mod):
    assert classify_mode(3, agency_id="1", short_name=ad, rules=IETT.mode_rules) == mod


def test_iett_tipsiz_hatlar_elenir():
    assert "other" in IETT.exclude_modes

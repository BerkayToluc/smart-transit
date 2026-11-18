"""Yardımcı fonksiyonların birim testleri (veritabanı / ağ gerekmez)."""
from types import SimpleNamespace

import pytest

import main


# --- mesafe_hesapla_km --------------------------------------------------------
def test_mesafe_ayni_nokta_sifir():
    assert main.mesafe_hesapla_km(41.0, 29.0, 41.0, 29.0) == 0


def test_mesafe_bir_derece_enlem():
    # 1 derece enlem ~ 111.19 km
    assert main.mesafe_hesapla_km(41.0, 29.0, 42.0, 29.0) == pytest.approx(111.19, abs=0.1)


def test_mesafe_kadikoy_taksim_makul():
    # Kadıköy iskelesi -> Taksim Meydanı kuş uçuşu yaklaşık 7-9 km
    km = main.mesafe_hesapla_km(40.9918, 29.0227, 41.0370, 28.9850)
    assert 5 < km < 10


def test_mesafe_simetrik():
    a = main.mesafe_hesapla_km(41.0, 28.5, 41.1, 29.2)
    b = main.mesafe_hesapla_km(41.1, 29.2, 41.0, 28.5)
    assert a == pytest.approx(b)


# --- _koordinat_duzelt --------------------------------------------------------
@pytest.mark.parametrize("ham, beklenen", [
    ("410.191.700.005.564", 41.0191700005564),   # stops.csv'deki bozuk biçim
    ("286.843.529.999.755", 28.6843529999755),
    ("41,015", 41.015),                           # virgüllü ondalık
    ("41.015", 41.015),
])
def test_koordinat_duzelt(ham, beklenen):
    assert main._koordinat_duzelt(ham) == pytest.approx(beklenen)


@pytest.mark.parametrize("ham", [None, "", "  ", "ab", "4"])
def test_koordinat_duzelt_gecersiz_none(ham):
    assert main._koordinat_duzelt(ham) is None


# --- _mojibake_duzelt ---------------------------------------------------------
def test_mojibake_duzelt_hat_adi():
    assert main._mojibake_duzelt("KADIKÃ–Y - KÄ°RAZLITEPE") == "KADIKÖY - KİRAZLITEPE"


def test_mojibake_duzelt_tum_karakterler():
    assert main._mojibake_duzelt("Ã‡ Ã§ ÄŸ Ä± Ã¶ ÅŸ Ã¼") == "Ç ç ğ ı ö ş ü"


def test_mojibake_duzelt_yetim_a_nokta():
    # Partneri kaybolmuş "Ä" -> "Ğ"
    assert main._mojibake_duzelt("KARAÄ") == "KARAĞ"


def test_mojibake_duzelt_bos_ve_temiz_metin():
    assert main._mojibake_duzelt("") == ""
    assert main._mojibake_duzelt(None) is None
    assert main._mojibake_duzelt("TAKSİM") == "TAKSİM"


# --- _route_kodu_parcala ------------------------------------------------------
def test_route_kodu_parcala():
    assert main._route_kodu_parcala("401_D_D0") == ("D", "D0")
    assert main._route_kodu_parcala("500T_G_G12") == ("G", "G12")


@pytest.mark.parametrize("kod", ["", None, "401", "401_D"])
def test_route_kodu_parcala_gecersiz(kod):
    assert main._route_kodu_parcala(kod) == (None, None)


# --- _ayrac_tespit_et ---------------------------------------------------------
def test_ayrac_tespit_noktalivirgul(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("a;b;c\n1;2;3\n", encoding="utf-8-sig")
    assert main._ayrac_tespit_et(str(f)) == ";"


def test_ayrac_tespit_virgul(tmp_path):
    f = tmp_path / "b.csv"
    f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert main._ayrac_tespit_et(str(f)) == ","


# --- _noktayi_segmente_izdusur ------------------------------------------------
A = (41.00, 29.0)
B = (41.01, 29.0)


def test_izdusum_dogru_uzerindeki_nokta():
    sapma, t = main._noktayi_segmente_izdusur(41.005, 29.0, *A, *B)
    assert sapma == pytest.approx(0, abs=1e-6)
    assert t == pytest.approx(0.5, abs=0.01)


def test_izdusum_segment_sonrasi_t_bire_kenetlenir():
    sapma, t = main._noktayi_segmente_izdusur(41.02, 29.0, *A, *B)
    assert t == 1.0
    assert sapma == pytest.approx(1.1054, abs=0.01)   # B'ye ~1.1 km


def test_izdusum_segment_oncesi_t_sifira_kenetlenir():
    _, t = main._noktayi_segmente_izdusur(40.99, 29.0, *A, *B)
    assert t == 0.0


def test_izdusum_yandan_sapma():
    # 0.001 derece doğuya: ~ 0.001 * 111.32 * cos(41°) ~ 0.084 km
    sapma, t = main._noktayi_segmente_izdusur(41.005, 29.001, *A, *B)
    assert sapma == pytest.approx(0.084, abs=0.005)
    assert t == pytest.approx(0.5, abs=0.01)


def test_izdusum_sifir_uzunluklu_segment():
    sapma, t = main._noktayi_segmente_izdusur(41.001, 29.0, 41.0, 29.0, 41.0, 29.0)
    assert t == 0.0
    assert sapma > 0


# --- _rota_kumulatif_mesafe ---------------------------------------------------
def _durak(lat, lon):
    return SimpleNamespace(latitude=lat, longitude=lon)


def test_kumulatif_mesafe():
    duraklar = [_durak(41.00, 29.0), _durak(41.01, 29.0), _durak(41.02, 29.0)]
    kum = main._rota_kumulatif_mesafe(duraklar)
    assert kum[0] == 0
    assert kum[1] == pytest.approx(1.112, abs=0.01)
    assert kum[2] == pytest.approx(2 * kum[1], abs=0.001)


def test_kumulatif_mesafe_tek_durak():
    assert main._rota_kumulatif_mesafe([_durak(41.0, 29.0)]) == [0.0]

"""data/m11.json gerçek tanımı: TCDD tablosuyla tutarlılık (istasyon sırası, ilk/son tren, günlük 145 sefer, süreler)."""
import csv
import os

from app.gtfs import manual

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TANIM = os.path.join(KOK, "data", "m11.json")


def test_tanim_gecerli_ve_istasyon_sirasi():
    t = manual.tanim_oku(TANIM)
    ad = [s["ad"] for s in t["istasyonlar"]]
    assert ad[0] == "Gayrettepe" and ad[6] == "İstanbul Havalimanı" and ad[-1] == "Halkalı" and len(ad) == 15
    assert t["istasyonlar"][-1]["ofset_sn"] == 64 * 60                      # son tren: Gayrettepe 23:58 -> Halkalı 01:02


def test_gunluk_sefer_sayisi_tcdd_ile_145():
    t = manual.tanim_oku(TANIM)
    toplam = 0
    for k in t["kaliplar"]:
        for sf in k["seferler"]:
            for a in sf["araliklar"]:
                for bas, bit, ar in manual.kalkis_pencereleri(manual.parse_time(a["ilk"]), manual.parse_time(a["son"]), a["aralik_dk"] * 60):
                    toplam += len(range(bas, bit, ar))
    assert toplam == 145                                                       # TCDD: "Günlük Sefer Sayısı: 145"


def test_ilk_son_tren_ve_siklik():
    k = {x["id"]: x["seferler"][0]["araliklar"][0] for x in manual.tanim_oku(TANIM)["kaliplar"]}
    assert k["gayrettepe_halkali"] == {"ilk": "05:58", "son": "23:58", "aralik_dk": 15}
    assert k["halkali_gayrettepe"] == {"ilk": "06:03", "son": "23:48", "aralik_dk": 15}


def test_koordinatlar_istanbul_kuzeybatisinda_ve_csv_ile_ayni():
    t = manual.tanim_oku(TANIM)
    with open(os.path.join(KOK, "data", "m11_koordinat.csv"), encoding="utf-8") as f:
        csv_k = {r[0]: (float(r[1]), float(r[2])) for r in csv.reader(f, delimiter=";") if r[0] != "id"}
    for s in t["istasyonlar"]:
        assert (s["enlem"], s["boylam"]) == csv_k[s["id"]]
        assert 41.0 < s["enlem"] < 41.3 and 28.7 < s["boylam"] < 29.05


def test_gtfs_uretimi(tmp_path):
    sayim = manual.gtfs_uret(manual.tanim_oku(TANIM), str(tmp_path))
    assert sayim["routes"] == 1 and sayim["stops"] == 15 and sayim["frequencies"] >= 2

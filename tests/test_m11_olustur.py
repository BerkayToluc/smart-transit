"""M11 tanım üreticisi (scripts/m11_olustur.py): konum seçimi, hız denetimi, tanım doğrulaması, GTFS üretimi."""
import csv
import importlib.util
import json
import os

import pytest

from app.gtfs import manual

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("m11_olustur", os.path.join(KOK, "scripts", "m11_olustur.py"))
m11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m11)


def hat_koordinatlari(hiz_kmh=60.0):
    """Tablodaki dakika farklarına uyan, kuzeybatıya düz giden yapay koordinatlar (hız = hiz_kmh)."""
    ilk_lat, ilk_lon = 41.067, 28.990
    sonuc = {}
    for i, _, _, _, dk in m11.ISTASYONLAR:
        km = hiz_kmh * dk / 60
        sonuc[i] = (ilk_lat + km * 0.7 / 111, ilk_lon - km * 0.7 / (111 * 0.755))
    return sonuc


def sahte_overpass(koordinat):
    ogeler = []
    for n, (kimlik, ad, *_) in enumerate(m11.ISTASYONLAR, 1):
        lat, lon = koordinat[kimlik]
        ogeler.append({"type": "node", "id": n, "lat": lat, "lon": lon, "tags": {"name": ad, "railway": "station"}})
    ogeler.append({"type": "node", "id": 999, "lat": 41.0, "lon": 28.9, "tags": {"name": "Gayrettepe Otobüs", "highway": "bus_stop"}})
    return {"elements": ogeler}


def test_tablo_ofsetleri_artar_ve_halkali_64_dk():
    dk = [x[4] for x in m11.ISTASYONLAR]
    assert dk == sorted(dk) and len(set(dk)) == len(dk) and dk[-1] == 64 and len(dk) == 15


def test_adaylari_ayikla_halkali_stadi_halkaliyla_karismaz():
    k = hat_koordinatlari()
    a = m11.adaylari_ayikla(sahte_overpass(k))
    assert [c["ad"] for c in a["halkali_stadi"]] == ["Halkalı Stadı"]
    assert [c["ad"] for c in a["halkali"]] == ["Halkalı"]


def test_konum_sec_tek_konum_belirsiz_ve_m11_etiketi():
    yakin = [{"ad": "G", "lat": 41.0, "lon": 29.0, "etiketler": {}}, {"ad": "G", "lat": 41.001, "lon": 29.0, "etiketler": {}}]
    assert m11.konum_sec("x", yakin)[0] == pytest.approx(41.0005)
    uzak = [{"ad": "G", "lat": 41.0, "lon": 29.0, "etiketler": {"line": "M2"}},
            {"ad": "G", "lat": 41.05, "lon": 29.0, "etiketler": {"line": "M11"}}]
    assert m11.konum_sec("x", uzak) == (41.05, 29.0)                # M11 etiketli aday seçilir
    belirsiz = [{"ad": "G", "lat": 41.0, "lon": 29.0, "etiketler": {}}, {"ad": "G", "lat": 41.05, "lon": 29.0, "etiketler": {}}]
    assert m11.konum_sec("x", belirsiz) is None and m11.konum_sec("x", []) is None


def test_hiz_kontrolu_makul_gecer_yanlis_eslesme_yakalanir():
    k = hat_koordinatlari()
    assert m11.hiz_kontrolu(k) == []
    k["tasoluk"] = (41.30, 28.50)                                    # yanlış düğüm: onlarca km uzakta
    assert any("Taşoluk" in s for s in m11.hiz_kontrolu(k))


def test_tanim_dogrulanir_ve_saatler_tablodan():
    t = m11.tanim_uret(hat_koordinatlari(), 10, "2026-11-24")
    manual.dogrula(t)
    k = {x["id"]: x for x in t["kaliplar"]}
    assert (k["gayrettepe_halkali"]["seferler"][0]["araliklar"][0]) == {"ilk": "05:58", "son": "23:58", "aralik_dk": 10}
    assert (k["halkali_gayrettepe"]["seferler"][0]["araliklar"][0]) == {"ilk": "06:03", "son": "23:48", "aralik_dk": 10}
    assert [s["id"] for s in t["istasyonlar"]][0] == "gayrettepe" and t["istasyonlar"][-1]["ofset_sn"] == 64 * 60
    assert "10 dk" in t["besleme"]["kaynak"]


def test_gtfs_uretimi_son_tren_gece_yarisindan_sonra(tmp_path):
    t = m11.tanim_uret(hat_koordinatlari(), 10, "2026-11-24")
    manual.gtfs_uret(t, str(tmp_path))
    with open(tmp_path / "stop_times.csv", encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    # Halkalı'ya varış ofseti 64 dk: son tren (23:58 kalkış) 01:02'de varır -> şablonda 64:00 dk uzunluk
    assert max(int(s["arrival_time"].split(":")[0]) * 60 + int(s["arrival_time"].split(":")[1]) for s in satirlar) == 64


def test_main_uctan_uca_sahte_ag(tmp_path):
    k = hat_koordinatlari()

    class Yanit:
        def raise_for_status(self):
            pass

        def json(self):
            return sahte_overpass(k)

    cikti = tmp_path / "m11.json"
    kod = m11.main(["--aralik-dk", "12", "--cikti", str(cikti), "--veri-tarihi", "2026-11-24"], http_post=lambda *a, **kw: Yanit())
    assert kod == 0
    tanim = json.loads(cikti.read_text(encoding="utf-8"))
    assert len(tanim["istasyonlar"]) == 15 and tanim["kaliplar"][0]["seferler"][0]["araliklar"][0]["aralik_dk"] == 12


def test_main_belirsiz_istasyonda_durur_ve_koordinat_dosyasi_calisir(tmp_path, capsys):
    k = hat_koordinatlari()
    veri = sahte_overpass(k)
    veri["elements"].append({"type": "node", "id": 1000, "lat": 41.30, "lon": 28.50, "tags": {"name": "Kargo Terminali", "railway": "station"}})

    class Yanit:
        def raise_for_status(self):
            pass

        def json(self):
            return veri

    cikti = tmp_path / "m11.json"
    kod = m11.main(["--aralik-dk", "10", "--cikti", str(cikti)], http_post=lambda *a, **kw: Yanit())
    assert kod == 2 and not cikti.exists() and "kargo_terminali" in capsys.readouterr().out
    csv_yol = tmp_path / "k.csv"
    csv_yol.write_text("id;enlem;boylam\nkargo_terminali;%s;%s\n" % k["kargo_terminali"], encoding="utf-8")
    kod = m11.main(["--aralik-dk", "10", "--cikti", str(cikti), "--koordinat", str(csv_yol)], http_post=lambda *a, **kw: Yanit())
    assert kod == 0 and cikti.exists()


def test_aralik_zorunlu():
    with pytest.raises(SystemExit):
        m11.main([])

"""Rota motoru (RAPTOR): sentetik ağlarla. Her test veritabanına küçük bir GTFS yazar, grafı kurar ve sorgular.

Koordinatlar (yer): kuzey/doğu metre; yürüme 1.3 × / (4.8 km/s) => 100 m = 98 sn.
"""
import math

import pytest
from sqlalchemy import select

from app.gtfs import loader
from app.gtfs.models import (
    GtfsCalendar, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTransfer, GtfsTrip,
)
from app.routing import graph, plan, raptor

LAT0, LON0 = 41.0, 29.0
HAFTA_ICI = [1, 1, 1, 1, 1, 0, 0]
HER_GUN = [1] * 7


def yer(kuzey=0.0, dogu=0.0):
    return LAT0 + kuzey / 111_195.0, LON0 + dogu / (111_195.0 * math.cos(math.radians(LAT0)))


def hm(s):
    sa, dk = s.split(":")[:2]
    return int(sa) * 3600 + int(dk) * 60


class Ag:
    """Test ağı kurucusu."""

    def __init__(self, oturum):
        self.o = oturum
        self._hat = {}

    def durak(self, ad, kuzey=0.0, dogu=0.0):
        if self.o.get(GtfsFeed, "t") is None:
            self.o.add(GtfsFeed(id="t", name="t"))
            self.o.flush()
        la, lo = yer(kuzey, dogu)
        self.o.add(GtfsStop(id=f"t:{ad}", feed_id="t", name=ad, lat=la, lon=lo, location_type=0))
        self.o.flush()
        return f"t:{ad}"

    def hizmet(self, ad, gunler):
        if self.o.get(GtfsCalendar, ad) is None:
            self.o.add(GtfsCalendar(service_id=ad, feed_id="t", monday=bool(gunler[0]), tuesday=bool(gunler[1]),
                                    wednesday=bool(gunler[2]), thursday=bool(gunler[3]), friday=bool(gunler[4]),
                                    saturday=bool(gunler[5]), sunday=bool(gunler[6])))
            self.o.flush()

    def sefer(self, hat, mod, saatler, *, hizmet="her", gunler=HER_GUN, kimlik=None, pickup=None, drop=None,
              baslik=None):
        """saatler: [(durak_adı, "HH:MM"), ...] (varış = kalkış)."""
        self.hizmet(hizmet, gunler)
        rid = f"t:{hat}"
        if self.o.get(GtfsRoute, rid) is None:
            self.o.add(GtfsRoute(id=rid, feed_id="t", short_name=hat, mode=mod))
            self.o.flush()
        tid = f"t:{kimlik or hat + '_' + saatler[0][1]}"
        self.o.add(GtfsTrip(id=tid, feed_id="t", route_id=rid, service_id=hizmet, headsign=baslik or saatler[-1][0]))
        self.o.flush()
        for i, (d, s) in enumerate(saatler, 1):
            self.o.add(GtfsStopTime(trip_id=tid, stop_sequence=i, stop_id=f"t:{d}", arrival_secs=hm(s),
                                    departure_secs=hm(s), pickup_type=(pickup or {}).get(d, 0),
                                    drop_off_type=(drop or {}).get(d, 0)))
        self.o.flush()
        return tid

    def yurume(self, a, b, sn, iki_yon=True):
        self.o.add(GtfsTransfer(from_stop_id=f"t:{a}", to_stop_id=f"t:{b}", transfer_type=2, min_transfer_secs=sn,
                                source="auto"))
        if iki_yon:
            self.o.add(GtfsTransfer(from_stop_id=f"t:{b}", to_stop_id=f"t:{a}", transfer_type=2,
                                    min_transfer_secs=sn, source="auto"))
        self.o.flush()

    def graf(self):
        self.o.commit()
        return graph.kur(self.o)


@pytest.fixture
def ag(oturum):
    oturum.rollback()
    for f in oturum.scalars(select(GtfsFeed.id)).all():
        loader._beslemeyi_sil(oturum, f)
    oturum.commit()
    yield Ag(oturum)
    oturum.rollback()
    for f in oturum.scalars(select(GtfsFeed.id)).all():
        loader._beslemeyi_sil(oturum, f)
    oturum.commit()


def idx(g, ad):
    return g.durak_id.index(f"t:{ad}")


def sorgu(g, kaynak, hedef, saat, gun=0, kaynak_sn=0, cikis_sn=0, **kw):
    return raptor.ara(g, {idx(g, kaynak): hm(saat) + kaynak_sn}, {idx(g, hedef): cikis_sn}, gun, **kw)


def arac_etaplari(y):
    return [e for e in y.etaplar if e.tip == "arac"]


# --- temel senaryolar ---------------------------------------------------------------------------
def test_aktarmasiz_en_erken_sefer(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10"), ("C", "08:20")], kimlik="s1")
    ag.sefer("L1", "bus", [("A", "08:30"), ("B", "08:40"), ("C", "08:50")], kimlik="s2")
    g = ag.graf()
    r = sorgu(g, "A", "C", "08:05")
    assert len(r) == 1 and r[0].aktarma == 0 and r[0].varis == hm("08:50")      # 08:00'ı kaçırdı
    e = arac_etaplari(r[0])[0]
    assert (e.kalkis, e.varis, e.durak_sayisi, e.mod) == (hm("08:30"), hm("08:50"), 2, "bus")
    assert g.meta_sefer_id[e.meta] == "t:s2" and g.hat_kisa[e.hat] == "L1" and g.meta_baslik[e.meta] == "C"
    # tam zamanında gelen yolcu 08:00 seferine biner (ilk binişte pay yok)
    assert sorgu(g, "A", "C", "08:00")[0].varis == hm("08:20")


def test_tek_aktarma_ve_kacirilan_aktarma(ag):
    for d in "ABCD":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:20")], kimlik="a1")
    ag.sefer("L2", "metro", [("B", "08:21"), ("C", "08:30")], kimlik="m1")     # 1 dk: payı (60 sn) yetiyor
    ag.sefer("L2", "metro", [("B", "08:40"), ("C", "08:50")], kimlik="m2")
    ag.sefer("L3", "bus", [("A", "08:00"), ("B", "08:19")], kimlik="x1")       # 08:19'da B'de
    g = ag.graf()
    r = sorgu(g, "A", "C", "08:00")[0]
    assert r.aktarma == 1 and r.varis == hm("08:30")
    assert [g.hat_kisa[e.hat] for e in arac_etaplari(r)] == ["L1", "L2"] or [g.hat_kisa[e.hat] for e in arac_etaplari(r)] == ["L3", "L2"]


def test_aktarma_payi_kacirir(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:20")], kimlik="a1")
    ag.sefer("L2", "bus", [("B", "08:20"), ("C", "08:30")], kimlik="m1")       # aynı dakika: 60 sn pay nedeniyle yetişilmez
    ag.sefer("L2", "bus", [("B", "08:50"), ("C", "09:00")], kimlik="m2")
    g = ag.graf()
    assert sorgu(g, "A", "C", "08:00")[0].varis == hm("09:00")
    assert sorgu(g, "A", "C", "08:00", aktarma_payi_sn=0)[0].varis == hm("08:30")


def test_yurume_aktarmasi(ag):
    for ad, k in (("A", 0), ("B", 100), ("B2", 300), ("C", 500)):
        ag.durak(ad, k, 0)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10")], kimlik="a1")
    ag.sefer("L2", "bus", [("B2", "08:20"), ("C", "08:30")], kimlik="b1")
    ag.yurume("B", "B2", 196)                                                  # 200 m yürüyüş
    g = ag.graf()
    r = sorgu(g, "A", "C", "08:00")[0]
    assert r.aktarma == 1 and r.varis == hm("08:30")
    assert [e.tip for e in r.etaplar] == ["arac", "yurume", "arac"]
    y = r.etaplar[1]
    assert (g.durak_ad[y.bas], g.durak_ad[y.bit], y.varis - y.kalkis) == ("B", "B2", 196)
    # yürüme kenarı yoksa ulaşılamaz
    ag.o.query(GtfsTransfer).delete()
    assert sorgu(ag.graf(), "A", "C", "08:00") == []


def test_ulasilamaz_ve_ters_yon(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10")], kimlik="a1")
    g = ag.graf()
    assert sorgu(g, "A", "C", "08:00") == []                                    # C'ye hat yok
    assert sorgu(g, "B", "A", "08:00") == []                                    # hat tek yönlü


def test_pareto_hizli_aktarmali_ve_yavas_dogrudan(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("YAVAS", "bus", [("A", "08:00"), ("C", "09:30")], kimlik="y1")      # aktarmasız ama 90 dk
    ag.sefer("L1", "metro", [("A", "08:00"), ("B", "08:10")], kimlik="a1")
    ag.sefer("L2", "metro", [("B", "08:15"), ("C", "08:25")], kimlik="b1")
    g = ag.graf()
    r = sorgu(g, "A", "C", "08:00")
    assert [(y.aktarma, y.varis) for y in r] == [(0, hm("09:30")), (1, hm("08:25"))]
    assert sorgu(g, "A", "C", "08:00", max_aktarma=0)[0].varis == hm("09:30")      # aktarma sınırı


def test_mod_suzgeci(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("M1", "metro", [("A", "08:00"), ("B", "08:10"), ("C", "08:20")], kimlik="m")
    ag.sefer("B1", "bus", [("A", "08:00"), ("B", "08:30"), ("C", "09:00")], kimlik="b")
    g = ag.graf()
    assert sorgu(g, "A", "C", "08:00")[0].varis == hm("08:20")
    assert sorgu(g, "A", "C", "08:00", izinli_modlar=["bus"])[0].varis == hm("09:00")
    assert sorgu(g, "A", "C", "08:00", izinli_modlar=["ferry"]) == []


# --- gün, gece yarısı, yasaklar, aralıklı seferler -------------------------------------------------
def test_hizmet_gunu(ag):
    for d in "AB":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10")], hizmet="hafta_ici", gunler=HAFTA_ICI, kimlik="a1")
    g = ag.graf()
    assert sorgu(g, "A", "B", "07:00", gun=0)[0].varis == hm("08:10")             # Pazartesi
    assert sorgu(g, "A", "B", "07:00", gun=5) == []                                # Cumartesi: sefer yok
    assert sorgu(g, "A", "B", "07:00", gun=6) == []


def test_gece_yarisini_asan_sefer_ertesi_gun_sabahi_gorunur(ag):
    for d in "AB":
        ag.durak(d)
    # Cuma gecesi 25:00 (= Cumartesi 01:00) kalkışı
    ag.sefer("N1", "ferry", [("A", "25:00"), ("B", "25:30")], hizmet="cuma", gunler=[0, 0, 0, 0, 1, 0, 0], kimlik="n1")
    g = ag.graf()
    # Cuma 23:30: sefer bugünün saatleriyle (25:00) bulunur
    assert sorgu(g, "A", "B", "23:30", gun=4)[0].varis == hm("25:30")
    # Cumartesi 00:30: sefer önceki günün seferi olarak 01:00'de görünür (kayma -24 sa)
    r = sorgu(g, "A", "B", "00:30", gun=5)[0]
    assert r.varis == hm("01:30") and arac_etaplari(r)[0].kalkis == hm("01:00")
    # Perşembe 00:30: ne Perşembe ne Çarşamba hizmeti var
    assert sorgu(g, "A", "B", "00:30", gun=3) == []


def test_binis_yasagi(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("F1", "ferry", [("A", "08:00"), ("B", "08:10"), ("C", "08:20")], pickup={"B": 1}, kimlik="f1")
    g = ag.graf()
    assert sorgu(g, "A", "C", "08:00")[0].varis == hm("08:20")
    assert sorgu(g, "B", "C", "08:00") == []                  # B'den binilemez (Karaköy 20:55 gibi)
    assert sorgu(g, "A", "B", "08:00")[0].varis == hm("08:10")  # ama B'ye inilebilir


def test_inis_yasagi(ag):
    for d in "ABC":
        ag.durak(d)
    ag.sefer("F1", "ferry", [("A", "08:00"), ("B", "08:10"), ("C", "08:20")], drop={"B": 1}, kimlik="f1")
    g = ag.graf()
    assert sorgu(g, "A", "B", "08:00") == []


def test_araliklu_seferler_somut_seferlere_acilir(ag):
    for d in "ABC":
        ag.durak(d)
    tid = ag.sefer("MR", "rail", [("A", "00:00"), ("B", "00:10"), ("C", "00:20")], kimlik="sablon")
    ag.o.add(GtfsFrequency(feed_id="t", trip_id=tid, start_secs=hm("06:00"), end_secs=hm("07:00"), headway_secs=900,
                           exact_times=0))
    ag.o.flush()
    g = ag.graf()
    assert g.sefer_sayisi() == 4                                    # 06:00 06:15 06:30 06:45
    assert sorgu(g, "A", "C", "06:20")[0].varis == hm("06:50")      # 06:30 seferi
    assert sorgu(g, "A", "C", "06:46") == []                        # pencere bitti
    assert g.meta_sefer_id[arac_etaplari(sorgu(g, "A", "C", "06:20")[0])[0].meta] == f"{tid}@{hm('06:30')}"


def test_hizmeti_olmayan_sefer_dislanir(ag):
    for d in "AB":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10")], hizmet="bos", gunler=[0] * 7, kimlik="a1")
    assert ag.graf().sefer_sayisi() == 0


def test_halka_hat_ayni_durak_iki_kez(ag):
    for d in "ABC":
        ag.durak(d, 0, 0 if d == "A" else 500)
    ag.sefer("R", "ferry", [("A", "08:00"), ("B", "08:10"), ("C", "08:20"), ("A", "08:30")], kimlik="r1")
    g = ag.graf()
    ayni = sorgu(g, "A", "A", "07:00")                                # kaynak = hedef: araçsız, süre 0
    assert len(ayni) == 1 and arac_etaplari(ayni[0]) == [] and ayni[0].varis == hm("07:00")
    assert sorgu(g, "A", "C", "07:00")[0].varis == hm("08:20")
    assert sorgu(g, "C", "A", "07:00")[0].varis == hm("08:30")


# --- koordinattan koordinata --------------------------------------------------------------------
def test_planla_erisim_cikis_yuruyusu_ve_tercih(ag):
    ag.durak("A", 0, 0)
    ag.durak("B", 5000, 0)
    ag.sefer("L1", "bus", [("A", "08:10"), ("B", "08:30")], kimlik="a1")
    g = ag.graf()
    bas, bit = yer(-300, 0), yer(5200, 0)                              # A'ya 300 m, B'den 200 m
    s = plan.planla(g, bas, bit, 0, hm("08:00"))
    assert len(s) == 1
    sec = s[0]
    assert [e.tip for e in sec.etaplar] == ["yurume", "arac", "yurume"]
    assert sec.etaplar[0].varis - sec.etaplar[0].kalkis == plan.yurume_sn(300)
    assert sec.varis == hm("08:30") + plan.yurume_sn(200) and sec.aktarma == 0
    assert abs(sec.yuruyus_m - 500 * 1.3) < 3 and sec.sure == sec.varis - sec.kalkis


def test_planla_yakin_noktalar_yaya_secenegi(ag):
    ag.durak("A", 0, 0)
    ag.durak("B", 5000, 0)
    ag.sefer("L1", "bus", [("A", "08:10"), ("B", "08:30")], kimlik="a1")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(400, 0), 0, hm("08:00"))
    assert s[0].etaplar[0].tip == "yurume" and len(s[0].etaplar) == 1 and s[0].aktarma == 0


def test_planla_menzil_disi_ve_gecersiz_tercih(ag):
    ag.durak("A", 0, 0)
    ag.durak("B", 5000, 0)
    ag.sefer("L1", "bus", [("A", "08:10"), ("B", "08:30")], kimlik="a1")
    g = ag.graf()
    assert plan.planla(g, yer(3000, 3000), yer(5200, 0), 0, hm("08:00")) == []   # başlangıçta 800 m içinde durak yok
    with pytest.raises(ValueError):
        plan.planla(g, yer(0, 0), yer(5000, 0), 0, hm("08:00"), tercih="en_ucuz")


def test_planla_tercih_siralamasi(ag):
    # hızlı ama 1 aktarmalı ve çok yürüten vs yavaş aktarmasız
    ag.durak("A", 0, 0); ag.durak("B", 3000, 0); ag.durak("C", 6000, 0); ag.durak("D", 6000, 700)
    ag.sefer("YAVAS", "bus", [("A", "08:00"), ("C", "09:00")], kimlik="y1")
    ag.sefer("L1", "metro", [("A", "08:00"), ("B", "08:10")], kimlik="a1")
    ag.sefer("L2", "metro", [("B", "08:15"), ("D", "08:25")], kimlik="b1")
    g = ag.graf()
    bas, bit = yer(0, 0), yer(6000, 0)
    hizli = plan.planla(g, bas, bit, 0, hm("08:00"), tercih="hizli", max_yurume_m=1000)
    az = plan.planla(g, bas, bit, 0, hm("08:00"), tercih="az_aktarma", max_yurume_m=1000)
    assert hizli[0].aktarma == 1 and az[0].aktarma == 0
    assert hizli[0].varis < az[0].varis
    yuru = plan.planla(g, bas, bit, 0, hm("08:00"), tercih="az_yuruyus", max_yurume_m=1000)
    assert yuru[0].yuruyus_m <= yuru[-1].yuruyus_m


# --- önbellek ---------------------------------------------------------------------------------
def test_graf_onbellek_gidis_donus_ve_parmak_izi(ag, tmp_path):
    for d in "AB":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10")], kimlik="a1")
    ag.o.commit()
    yol = str(tmp_path / "graf.pkl")
    g1 = graph.yukle(ag.o, yol)
    assert (tmp_path / "graf.pkl").exists()
    g2 = graph.yukle(ag.o, yol)
    assert g2.parmak_izi == g1.parmak_izi and sorgu(g2, "A", "B", "07:00")[0].varis == hm("08:10")
    # veri değişince (yeni aktarma kenarı) önbellek geçersiz olur
    ag.yurume("A", "B", 100)
    ag.o.commit()
    assert graph.parmak_izi(ag.o) != g1.parmak_izi
    g3 = graph.yukle(ag.o, yol)
    assert g3.parmak_izi == graph.parmak_izi(ag.o)
    assert graph.oku(str(tmp_path / "yok.pkl")) is None


def test_bozuk_saatler_enterpolasyon(ag):
    for d in "ABC":
        ag.durak(d)
    tid = ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10"), ("C", "08:20")], kimlik="a1")
    ag.o.query(GtfsStopTime).filter(GtfsStopTime.trip_id == tid, GtfsStopTime.stop_id == "t:B").update(
        {"arrival_secs": None, "departure_secs": None})
    g = ag.graf()
    assert sorgu(g, "A", "B", "08:00")[0].varis == hm("08:10")      # ara durak saati 08:00 ile 08:20 arasından


def test_durak_ozeti_teshis(ag):
    for d in ("Kabataş", "Taksim"):
        ag.durak(d)
    ag.sefer("F1", "funicular", [("Kabataş", "08:00"), ("Taksim", "08:03")], hizmet="hi", gunler=HAFTA_ICI, kimlik="f1")
    ag.sefer("F1", "funicular", [("Kabataş", "09:00"), ("Taksim", "09:03")], hizmet="hi", gunler=HAFTA_ICI, kimlik="f2")
    g = ag.graf()
    metin = plan.durak_ozeti(g, "kabatas", 1)
    assert "1 durak" in metin and "funicular F1" in metin and "5/5" not in metin
    assert "seferler(Pzt..Paz): 2/2/2/2/2/0/0" in metin and "Sal ilk 08:00 son 09:00" in metin
    assert "0 durak" in plan.durak_ozeti(g, "yok yok", 1)
    assert "1 durak" not in plan.durak_ozeti(g, "kabatas", 1, modlar=["bus"])


def test_ayni_sefere_baslangica_yakin_duraktan_binilir(ag):  # noqa: F811
    # Hat: UZAK (700 m) -> YAKIN (200 m) -> VARIS. Aynı sefer iki durağa da uğrar; yürüyerek ikisine de yetişilir.
    # Varış aynıdır; daha az yürütmek için YAKIN'dan binilmeli.
    ag.durak("UZAK", 700, 0)
    ag.durak("YAKIN", 200, 0)
    ag.durak("VARIS", 5000, 0)
    ag.sefer("L1", "bus", [("UZAK", "08:20"), ("YAKIN", "08:23"), ("VARIS", "08:40")], kimlik="a1")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(5000, 0), 0, hm("08:00"), max_yurume_m=1000)
    arac = [e for e in s[0].etaplar if e.tip == "arac"][0]
    assert g.durak_ad[arac.bas] == "YAKIN"
    assert s[0].yuruyus_m < 400                                        # 700 m'lik yürüyüş yok


def test_yakin_duraklar_alternatifi_listede_olur(ag):  # noqa: F811
    # HIZLI hat uzak duraktan (750 m) kalkar ve erken varır; YAVAS hat yakın duraktan (100 m) kalkar ve geç varır.
    # Yalnızca erken varışa bakılırsa YAVAS elenirdi (aynı aktarma sayısında domine); yakın durak alternatifi olarak da çıkmalı.
    for ad, k in (("UZAK", 750), ("YAKIN", 100), ("VARIS", 6000), ("VARIS2", 6050)):
        ag.durak(ad, k, 0)
    ag.sefer("HIZLI", "bus", [("UZAK", "08:15"), ("VARIS", "08:28")], kimlik="h1")
    ag.sefer("YAVAS", "bus", [("YAKIN", "08:05"), ("VARIS2", "08:50")], kimlik="y1")
    # fazladan duraklar: en yakın 3 durak içinde YAKIN bulunsun, UZAK 4. sırada kalsın (yakın duraklar araması YAVAS'ı bulur)
    for ad, k in (("D1", 120), ("D2", 140), ("D3", 160)):
        ag.durak(ad, k, 0)
        ag.sefer("X" + ad, "bus", [(ad, "07:00"), ("VARIS", "07:10")], kimlik="x" + ad)
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(6000, 0), 0, hm("08:00"), max_yurume_m=1000, en_cok=5)
    hatlar = {g.hat_kisa[e.hat] for sec in s for e in sec.etaplar if e.tip == "arac"}
    assert {"HIZLI", "YAVAS"} <= hatlar
    assert s[0].varis < [x for x in s if any(g.hat_kisa[e.hat] == "YAVAS" for e in x.etaplar if e.tip == "arac")][0].varis


# --- sıralama ve eleme (genelleştirilmiş maliyet) -----------------------------------------------
def test_planla_yarim_dakika_kazandiran_aktarmalar_elenir(ag):  # noqa: F811
    # Doğrudan hat 08:40'ta varır. Alternatif: otobüs + 1 duraklık metrobüs + otobüs, 08:39'da varır (1 dk kazanç, 2 aktarma).
    for ad, k in (("A", 0), ("M", 2000), ("N", 2300), ("B", 5000)):
        ag.durak(ad, k, 0)
    ag.sefer("D1", "bus", [("A", "08:10"), ("B", "08:40")], kimlik="d1")
    ag.sefer("X1", "bus", [("A", "08:10"), ("M", "08:25")], kimlik="x1")
    ag.sefer("MB", "metrobus", [("M", "08:27"), ("N", "08:29")], kimlik="mb")
    ag.sefer("X2", "bus", [("N", "08:31"), ("B", "08:39")], kimlik="x2")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(5000, 0), 0, hm("08:00"))
    assert [sec.aktarma for sec in s] == [0] and {g.hat_kisa[e.hat] for e in s[0].etaplar if e.tip == "arac"} == {"D1"}
    # alternatif gerçekten belirgin (>=5 dk) kazandırıyorsa elenmez
    ag.o.query(GtfsStopTime).filter(GtfsStopTime.trip_id == "t:d1").update({"arrival_secs": hm("09:05"), "departure_secs": hm("09:05")})
    s = plan.planla(ag.graf(), yer(0, 0), yer(5000, 0), 0, hm("08:00"))
    assert [sec.aktarma for sec in s] == [2, 0] or [sec.aktarma for sec in s] == [0, 2]
    assert s[0].aktarma == 2                                                   # 26 dk daha erken varır: önde


def test_planla_ayni_hat_dizisi_tek_secenek(ag):  # noqa: F811
    ag.durak("P1", 100, 0); ag.durak("P2", 700, 0); ag.durak("B", 6000, 0)
    ag.sefer("L1", "bus", [("P2", "08:15"), ("P1", "08:20"), ("B", "08:50")], kimlik="l1")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(6000, 0), 0, hm("08:00"), max_yurume_m=1000)
    assert len(s) == 1                                                         # yakın/uzak durak varyantları tek seçenek


def test_planla_cesitlilik_en_iyi_hat_yasaklanarak_alternatif_bulunur(ag):  # noqa: F811
    # Aynı duraklar arasında hızlı (HIZLI) ve yavaş (YAVAS) iki paralel hat. Yalnızca erken varışa bakan Pareto, yavaşı eler
    # (aynı aktarma sayısı); çeşitlilik aramasında hızlı hat yasaklanınca yavaş çıkar.
    ag.durak("A", 0, 0); ag.durak("B", 6000, 0)
    ag.sefer("HIZLI", "bus", [("A", "08:10"), ("B", "08:25")], kimlik="h1")
    ag.sefer("YAVAS", "bus", [("A", "08:12"), ("B", "08:50")], kimlik="y1")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(6000, 0), 0, hm("08:00"))
    assert [g.hat_kisa[sec.etaplar[1].hat] for sec in s] == ["HIZLI", "YAVAS"]
    # çeşitlilik kapalıysa yalnızca en hızlı
    k = plan.planla(g, yer(0, 0), yer(6000, 0), 0, hm("08:00"), cesitlilik=False)
    assert [g.hat_kisa[sec.etaplar[1].hat] for sec in k] == ["HIZLI"]


def test_raptor_yasak_hatlar(ag):  # noqa: F811
    for d in "AB":
        ag.durak(d)
    ag.sefer("L1", "bus", [("A", "08:00"), ("B", "08:10")], kimlik="a1")
    ag.sefer("L2", "bus", [("A", "08:05"), ("B", "08:30")], kimlik="a2")
    g = ag.graf()
    l1 = g.hat_kisa.index("L1")
    assert sorgu(g, "A", "B", "08:00")[0].varis == hm("08:10")
    assert sorgu(g, "A", "B", "08:00", yasak_hatlar={l1})[0].varis == hm("08:30")
    assert sorgu(g, "A", "B", "08:00", yasak_hatlar={l1, g.hat_kisa.index("L2")}) == []


def test_maliyet_formulu():
    # 40 dk süre + 2 aktarma (16 dk) + 10 dk yürüme (+5 dk ek) = 61 dk
    assert plan._maliyet(0, 2400, 2, 600) == 2400 + 2 * 480 + 300
    assert plan.AKTARMA_CEZASI_SN == 480 and plan.YURUME_EK_KATSAYI == 0.5 and plan.DEGER_ESIGI_SN == 300


def test_planla_hizli_siralama_aktarma_cezasini_hesaba_katar(ag):  # noqa: F811
    # A seçeneği 6 dk daha erken varır ama 2 aktarma yapar; B aktarmasızdır. Salt varışa bakılsa A önde olurdu;
    # maliyette A = süre + 16 dk ceza olduğundan B öne geçer. (A yine de elenmez: 5 dk eşiğinden fazla kazandırıyor.)
    for ad, k in (("A", 0), ("M", 2000), ("N", 2300), ("B", 5000)):
        ag.durak(ad, k, 0)
    ag.sefer("D1", "bus", [("A", "08:10"), ("B", "08:40")], kimlik="d1")
    ag.sefer("X1", "bus", [("A", "08:10"), ("M", "08:15")], kimlik="x1")
    ag.sefer("MB", "metrobus", [("M", "08:17"), ("N", "08:20")], kimlik="mb")
    ag.sefer("X2", "bus", [("N", "08:22"), ("B", "08:34")], kimlik="x2")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(5000, 0), 0, hm("08:00"))
    assert [sec.aktarma for sec in s] == [0, 2]
    assert s[1].varis < s[0].varis and s[0].maliyet < s[1].maliyet


def test_planla_kumulatif_yasak_ucuncu_alternatifi_bulur(ag):  # noqa: F811
    # Üç paralel hat: HIZLI, ORTA (otobüs) ve METRO. Hatlar tek tek yasaklanınca yalnızca HIZLI->ORTA çıkar; HIZLI ve ORTA birlikte
    # yasaklanınca METRO ortaya çıkmalı (Google'ın sunduğu "farklı mod" alternatifi).
    ag.durak("A", 0, 0); ag.durak("B", 6000, 0)
    ag.sefer("HIZLI", "bus", [("A", "08:10"), ("B", "08:25")], kimlik="h1")
    ag.sefer("ORTA", "bus", [("A", "08:12"), ("B", "08:40")], kimlik="o1")
    ag.sefer("METRO", "metro", [("A", "08:15"), ("B", "08:55")], kimlik="m1")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(6000, 0), 0, hm("08:00"))
    assert [g.hat_kisa[sec.etaplar[1].hat] for sec in s] == ["HIZLI", "ORTA", "METRO"]


def test_planla_ayni_gorunen_metrobus_varyantlari_tek_secenek(ag):  # noqa: F811
    # 34BZ ve 34G aynı koridorda aynı saatlerde gider; kullanıcıya iki ayrı (aynı görünen) seçenek gösterilmemeli.
    ag.durak("A", 0, 0); ag.durak("B", 6000, 0)
    ag.sefer("34BZ", "metrobus", [("A", "08:10"), ("B", "08:25")], kimlik="z1")
    ag.sefer("34G", "metrobus", [("A", "08:10"), ("B", "08:26")], kimlik="g1")
    ag.sefer("ORTA", "bus", [("A", "08:12"), ("B", "08:50")], kimlik="o1")
    g = ag.graf()
    s = plan.planla(g, yer(0, 0), yer(6000, 0), 0, hm("08:00"))
    assert [g.hat_kisa[sec.etaplar[1].hat] for sec in s] == ["34BZ", "ORTA"]

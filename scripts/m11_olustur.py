"""M11 (Gayrettepe - İstanbul Havalimanı - Halkalı) tanım dosyasını (data/m11.json) üretir.

Saatler ve istasyon sırası TCDD'nin "ilk ve son tren saatleri" tablosundan gelir (aşağıda, koda gömülü). İstasyon KONUMLARI
OpenStreetMap'ten (Overpass API) otomatik alınır; böylece 15 istasyonun koordinatı elle girilmez. Sefer SIKLIĞI tabloda
yoktur: `--aralik-dk` ile TCDD sayfasından/uygulamasından okunan değer verilir (tahmin edilmez).

    python scripts/m11_olustur.py --aralik-dk 10

Overpass yoğunsa betik 3 sunucuyu 3 tur dener. Belirsiz istasyon (OSM'de birden çok farklı konum) olursa betik adayları yazıp durur; `--koordinat dosya.csv`
(id;enlem;boylam) ile elle düzeltilebilir. Üretilen dosya `data/m11.json`'a yazılır ve doğrulanır; ardından:

    python scripts/build_gtfs.py hepsi m11 --hedef sqlite:///gtfs_data/gtfs.db
    python scripts/build_gtfs.py aktarma --hedef sqlite:///gtfs_data/gtfs.db
"""
import argparse
import csv
import datetime
import json
import math
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import requests

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

from app.gtfs.manual import dogrula  # noqa: E402
from app.gtfs.textfix import ascii_katla  # noqa: E402

OVERPASS_ADRESLERI = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
                      "https://overpass.kumi.systems/api/interpreter")
TUR_SAYISI = 3                    # tüm sunucular başarısız olursa bu kadar tur denenir (aralarında bekleme)
ZAMAN_ASIMI = (10, 70)            # (bağlanma, okuma) sn: kalabalık sunucuda sonsuz beklemez
# Overpass, tanımlayıcı bir User-Agent olmayan istemcilere 406 döner; kişisel bilgi içermeyen genel bir ad kullanılır.
BASLIKLAR = {"User-Agent": "smarttransit-m11-olustur/1.0", "Accept": "application/json"}
KUTU = (40.95, 28.45, 41.40, 29.10)          # güney, batı, kuzey, doğu (İstanbul kuzeybatısı)
KAYNAK_ADRES = "https://www.tcddtasimacilik.gov.tr/marmaray/tr/gayrettepetrensaatleri"

# (id, ad, katlanmış ad parçası (eşleştirme), Overpass düzenli ifadesi (Türkçe harfler "." ile), son trenin dakika farkı)
# Dakika farkları TCDD tablosunun "Halkalı yönü, son tren" sütunundan: Gayrettepe 23:58'e göre (00:02 = +4, 00:07 = +9, ...).
ISTASYONLAR: List[Tuple[str, str, str, str, int]] = [
    ("gayrettepe", "Gayrettepe", "GAYRETTEPE", "Gayrettepe", 0),
    ("kagithane", "Kâğıthane", "THANE", "K.[ğg][ıi]thane", 4),
    ("hasdal_universite", "Hasdal-Üniversite", "HASDAL", "Hasdal", 9),
    ("kemerburgaz", "Kemerburgaz", "KEMERBURGAZ", "Kemerburgaz", 14),
    ("gokturk", "Göktürk", "GOKTURK", "G.kt.rk", 17),
    ("ihsaniye", "İhsaniye", "HSANIYE", "hsaniye", 25),
    ("istanbul_havalimani", "İstanbul Havalimanı", "HAVALIMANI", "Havaliman", 31),
    ("kargo_terminali", "Kargo Terminali", "KARGO", "Kargo", 34),
    ("tasoluk", "Taşoluk", "TASOLUK", "Ta.oluk", 39),
    ("arnavutkoy_hastane", "Arnavutköy-Hastane", "ARNAVUTKOY", "Arnavutk", 43),
    ("ibni_haldun_universitesi", "İbni Haldun Üniversitesi", "HALDUN", "Haldun", 49),
    ("kayasehir", "Kayaşehir", "KAYASEHIR", "Kaya.ehir", 53),
    ("olimpiyatkoy", "Olimpiyatköy", "OLIMPIYAT", "Olimpiyat", 57),
    ("halkali_stadi", "Halkalı Stadı", "HALKALI STAD", "Halkal. Stad", 60),
    ("halkali", "Halkalı", "HALKALI", "Halkal", 64),
]
# Tablodaki ilk/son tren (uç istasyonlardan kalkış)
GAYRETTEPE_HALKALI = ("05:58", "23:58")
HALKALI_GAYRETTEPE = ("06:03", "23:48")
EN_YUKSEK_HIZ_KMH = 130          # hat hızı sınırı üstünde ortalama hız: yanlış istasyon eşleşmesi
EN_DUSUK_HIZ_KMH = 15
GRUP_M = 400.0                   # aynı istasyonun OSM düğümleri bu mesafe içindeyse tek konum sayılır


def mesafe_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dlat = (a[0] - b[0]) * 111_000
    dlon = (a[1] - b[1]) * 111_000 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlon)


def overpass_sorgusu() -> str:
    """Kutudaki TÜM raylı durak düğümleri (hafif sorgu; ad süzgeci sunucuda değil burada yapılır: kalabalık sunucuda zaman aşımını önler)."""
    s, w, n, e = KUTU
    return (f'[out:json][timeout:40];(node["railway"~"^(station|halt|stop)$"]({s},{w},{n},{e});'
            f'node["station"~"^(subway|train)$"]({s},{w},{n},{e}););out body;')


def adaylari_ayikla(yanit: dict) -> Dict[str, List[dict]]:
    """Overpass yanıtından istasyon başına aday düğümler: {id: [{ad, lat, lon, etiketler}]}."""
    sonuc: Dict[str, List[dict]] = {i: [] for i, *_ in ISTASYONLAR}
    # "Halkalı" parçası "Halkalı Stadı"nı da yakalar: daha özgül (uzun) parçası olan istasyon önce eşleşir
    sirali = sorted(ISTASYONLAR, key=lambda x: -len(x[2]))
    for e in yanit.get("elements", []):
        if e.get("type") != "node" or "lat" not in e:
            continue
        et = e.get("tags", {})
        if not (et.get("railway") in ("station", "halt", "stop") or et.get("station") in ("subway", "train")):
            continue                                     # otobüs durağı vb. raylı olmayan düğümler aday olmaz
        ad = ascii_katla(et.get("name", ""))
        if not ad:
            continue
        for kimlik, _, parca, _, _ in sirali:
            if parca in ad:
                sonuc[kimlik].append({"ad": et.get("name", ""), "lat": e["lat"], "lon": e["lon"], "etiketler": et})
                break
    return sonuc


def _m11_isareti(aday: dict) -> bool:
    return any("M11" in str(v).upper() for v in aday["etiketler"].values())


def konum_sec(kimlik: str, adaylar: List[dict]) -> Optional[Tuple[float, float]]:
    """Adaylar tek konumda toplanıyorsa ortalama; değilse M11 etiketlileri; yine belirsizse None."""
    if not adaylar:
        return None
    def ortalama(liste):
        return (sum(a["lat"] for a in liste) / len(liste), sum(a["lon"] for a in liste) / len(liste))
    nokta = ortalama(adaylar)
    if all(mesafe_m((a["lat"], a["lon"]), nokta) <= GRUP_M for a in adaylar):
        return nokta
    m11 = [a for a in adaylar if _m11_isareti(a)]
    if m11:
        nokta = ortalama(m11)
        if all(mesafe_m((a["lat"], a["lon"]), nokta) <= GRUP_M for a in m11):
            return nokta
    return None


def hiz_kontrolu(koordinatlar: Dict[str, Tuple[float, float]]) -> List[str]:
    """Ardışık istasyonlar arası ortalama hız (kuş uçuşu / tablo süresi) makul mü? Sorunları döndürür."""
    sorunlar = []
    for (a, ad_a, _, _, dk_a), (b, ad_b, _, _, dk_b) in zip(ISTASYONLAR, ISTASYONLAR[1:]):
        m = mesafe_m(koordinatlar[a], koordinatlar[b])
        dk = dk_b - dk_a
        hiz = m / 1000 / (dk / 60)
        if not (EN_DUSUK_HIZ_KMH <= hiz <= EN_YUKSEK_HIZ_KMH):
            sorunlar.append(f"{ad_a} → {ad_b}: {m / 1000:.1f} km / {dk} dk = {hiz:.0f} km/s (beklenen {EN_DUSUK_HIZ_KMH}-{EN_YUKSEK_HIZ_KMH})")
    return sorunlar


def tanim_uret(koordinatlar: Dict[str, Tuple[float, float]], aralik_dk: int, veri_tarihi: str) -> dict:
    return {
        "besleme": {
            "id": "m11", "ad": "M11 Gayrettepe - İstanbul Havalimanı - Halkalı (TCDD, elle tanımlı)", "veri_tarihi": veri_tarihi,
            "kaynak": (f"TCDD Taşımacılık, Gayrettepe - İstanbul Havalimanı - Halkalı Metro Hattı ilk ve son tren saatleri ({KAYNAK_ADRES}). "
                       "Seferler uçtan uca varsayılır (tablodaki ara istasyon ilk tren saatleri kısa hatlı seferleri de içerir, modellenmedi); "
                       f"istasyonlar arası süreler son tren sütunundan; sıklık {aralik_dk} dk (TCDD'den okunan değer). "
                       "İstasyon konumları: OpenStreetMap."),
        },
        "kurum": {"id": "tcdd", "ad": "TCDD Taşımacılık", "url": "https://www.tcddtasimacilik.gov.tr"},
        "istasyonlar": [{"id": i, "ad": ad, "enlem": round(koordinatlar[i][0], 6), "boylam": round(koordinatlar[i][1], 6),
                         "ofset_sn": dk * 60} for i, ad, _, _, dk in ISTASYONLAR],
        "hizmetler": {"her_gun": {"gunler": [1, 1, 1, 1, 1, 1, 1], "aciklama": "Her gün"}},
        "hatlar": [{"id": "m11", "kisa_ad": "M11", "uzun_ad": "Gayrettepe - İstanbul Havalimanı - Halkalı"}],
        "kaliplar": [
            {"id": "gayrettepe_halkali", "hat": "m11", "yon": 0, "baslik": "Halkalı", "nereden": "gayrettepe", "nereye": "halkali",
             "seferler": [{"hizmet": "her_gun", "araliklar": [{"ilk": GAYRETTEPE_HALKALI[0], "son": GAYRETTEPE_HALKALI[1], "aralik_dk": aralik_dk}]}]},
            {"id": "halkali_gayrettepe", "hat": "m11", "yon": 1, "baslik": "Gayrettepe", "nereden": "halkali", "nereye": "gayrettepe",
             "seferler": [{"hizmet": "her_gun", "araliklar": [{"ilk": HALKALI_GAYRETTEPE[0], "son": HALKALI_GAYRETTEPE[1], "aralik_dk": aralik_dk}]}]},
        ],
    }


def koordinat_dosyasi_oku(yol: str) -> Dict[str, Tuple[float, float]]:
    sonuc = {}
    with open(yol, encoding="utf-8-sig", newline="") as f:
        for satir in csv.reader(f, delimiter=";"):
            if len(satir) >= 3 and satir[0] != "id" and satir[1].strip() and satir[2].strip():     # boş şablon satırları atlanır
                sonuc[satir[0].strip()] = (float(satir[1].replace(",", ".")), float(satir[2].replace(",", ".")))
    return sonuc


def main(argv=None, *, http_post=requests.post) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aralik-dk", type=int, required=True, help="Sefer sıklığı (dakika); TCDD sayfasından okunan değer")
    ap.add_argument("--koordinat", help="id;enlem;boylam CSV: OSM yerine/eksik istasyonlar için elle koordinat")
    ap.add_argument("--veri-tarihi", default=datetime.date.today().isoformat())
    ap.add_argument("--cikti", default=os.path.join(KOK, "data", "m11.json"))
    a = ap.parse_args(argv)
    if a.aralik_dk <= 0:
        ap.error("--aralik-dk pozitif olmalı")

    koordinat: Dict[str, Tuple[float, float]] = {}
    if a.koordinat:
        koordinat.update(koordinat_dosyasi_oku(a.koordinat))
    eksik = [i for i, *_ in ISTASYONLAR if i not in koordinat]
    if eksik:
        print("OpenStreetMap'ten (Overpass) konumlar alınıyor...")
        yanit, son_hata = None, None
        for tur in range(TUR_SAYISI):
            for adres in OVERPASS_ADRESLERI:              # biri yoğun/reddederse diğer sunucu denenir
                try:
                    print(f"  {adres} (tur {tur + 1}/{TUR_SAYISI})...")
                    yanit = http_post(adres, data={"data": overpass_sorgusu()}, headers=BASLIKLAR, timeout=ZAMAN_ASIMI)
                    yanit.raise_for_status()
                    break
                except requests.RequestException as e:
                    son_hata, yanit = e, None
                    print(f"    başarısız: {type(e).__name__}: {str(e)[:120]}")
            if yanit is not None:
                break
            if tur + 1 < TUR_SAYISI:
                print("  Tüm sunucular meşgul; 10 sn sonra yeniden denenecek...")
                time.sleep(10)
        if yanit is None:
            print("Overpass'a ulaşılamadı (sunucular yoğun olabilir; birkaç dakika sonra yeniden deneyin). "
                  "Ya da koordinatları Google Maps'ten `--koordinat dosya.csv` ile verin.")
            raise SystemExit(4) from son_hata
        adaylar = adaylari_ayikla(yanit.json())
        belirsiz = []
        for kimlik in eksik:
            nokta = konum_sec(kimlik, adaylar[kimlik])
            if nokta is None:
                belirsiz.append(kimlik)
            else:
                koordinat[kimlik] = nokta
        if belirsiz:
            print("\nŞu istasyonların konumu bulunamadı ya da belirsiz (adaylar):")
            for kimlik in belirsiz:
                print(f"  {kimlik}:")
                for c in adaylar[kimlik]:
                    print(f"      {c['lat']:.5f};{c['lon']:.5f}  {c['ad']}  {dict(list(c['etiketler'].items())[:4])}")
                if not adaylar[kimlik]:
                    print("      (hiç aday yok)")
            print("\nGoogle Maps'ten ilgili istasyonların koordinatını `id;enlem;boylam` satırlarıyla bir CSV'ye yazıp "
                  "`--koordinat dosya.csv` ile yeniden çalıştırın.")
            return 2
    sorunlar = hiz_kontrolu(koordinat)
    if sorunlar:
        print("Koordinatlar tablo süreleriyle uyuşmuyor (yanlış istasyon eşleşmesi olabilir):")
        for s in sorunlar:
            print("  -", s)
        print("İlgili istasyonları `--koordinat` ile elle düzeltin.")
        return 3
    tanim = tanim_uret(koordinat, a.aralik_dk, a.veri_tarihi)
    dogrula(tanim)
    with open(a.cikti, "w", encoding="utf-8") as f:
        json.dump(tanim, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Yazıldı: {a.cikti} ({len(tanim['istasyonlar'])} istasyon, her {a.aralik_dk} dk)")
    print("Sıradaki: python scripts/build_gtfs.py hepsi m11 --hedef sqlite:///gtfs_data/gtfs.db  ve  ... aktarma ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())

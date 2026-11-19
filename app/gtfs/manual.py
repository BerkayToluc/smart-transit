"""Elle tanımlanan besleme (ör. Marmaray): kurallardan GTFS dosyaları üretir.

Neden: portaldaki Marmaray verisi (2019) bugünkü hizmetle uyuşmuyor (docs/veri-kaynaklari.md).
Resmi tarifenin her seferini tek tek yazmak yerine yalnızca KURALLAR yazılır:

    "Halkalı → Gebze, 05:58'den 22:58'e her 15 dakikada bir"

Bu modül kuralları (data/marmaray.json) okur, doğrular ve standart GTFS dosyalarına çevirir
(`agency`, `routes`, `trips`, `stops`, `stop_times`, `frequencies`, `calendar`). Ardından aynı
yükleyici (`app/gtfs/loader.py`) kullanılır; seferlere açma planlama aşamasında yapılır
(`app/gtfs/rules.py`).

Tanım biçimi için bkz. data/marmaray.json ve docs/schema.md.
"""
import csv
import json
import os
import re
from typing import Dict, List, Tuple

from app.gtfs.reader import parse_time

GUN_SUTUNLARI = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_KIMLIK = re.compile(r"[a-z0-9_]+")
# Elle tanımlı beslemeler İstanbul bölgesinde olmalı (yanlış yazılmış koordinatı yakalar)
ENLEM_ARALIGI, BOYLAM_ARALIGI = (40.0, 42.0), (27.5, 31.0)


def tanim_oku(yol: str) -> dict:
    with open(yol, encoding="utf-8") as f:
        tanim = json.load(f)
    dogrula(tanim)
    return tanim


def _zaman(deger, hata: List[str], nerede: str):
    """"05:58" ya da "25:28" -> saniye. Geçersizse hata listesine ekler."""
    sn = parse_time(str(deger)) if deger is not None else None
    if sn is None:
        hata.append(f"{nerede}: geçersiz saat {deger!r}")
    return sn


def dogrula(tanim: dict) -> None:
    """Tanımı denetler; sorunların tümünü tek bir ValueError'da toplar."""
    h: List[str] = []
    for anahtar in ("besleme", "kurum", "istasyonlar", "hizmetler", "hatlar", "kaliplar"):
        if anahtar not in tanim:
            h.append(f"'{anahtar}' bölümü yok")
    if h:
        raise ValueError("; ".join(h))

    ist = tanim["istasyonlar"]
    if len(ist) < 2:
        h.append("en az 2 istasyon gerekli")
    kimlikler = set()
    onceki = None
    for i, s in enumerate(ist):
        n = f"istasyonlar[{i}]"
        if not _KIMLIK.fullmatch(str(s.get("id", ""))):
            h.append(f"{n}: id küçük harf/rakam/alt çizgi olmalı: {s.get('id')!r}")
        if s.get("id") in kimlikler:
            h.append(f"{n}: tekrarlanan id {s.get('id')!r}")
        kimlikler.add(s.get("id"))
        if not str(s.get("ad", "")).strip():
            h.append(f"{n}: ad boş")
        if not (isinstance(s.get("enlem"), (int, float)) and ENLEM_ARALIGI[0] <= s["enlem"] <= ENLEM_ARALIGI[1]):
            h.append(f"{n} ({s.get('id')}): enlem İstanbul bölgesinde değil: {s.get('enlem')!r}")
        if not (isinstance(s.get("boylam"), (int, float)) and BOYLAM_ARALIGI[0] <= s["boylam"] <= BOYLAM_ARALIGI[1]):
            h.append(f"{n} ({s.get('id')}): boylam İstanbul bölgesinde değil: {s.get('boylam')!r}")
        o = s.get("ofset_sn")
        if not isinstance(o, int) or o < 0:
            h.append(f"{n} ({s.get('id')}): ofset_sn negatif olmayan tam sayı olmalı: {o!r}")
        elif onceki is not None and o <= onceki:
            h.append(f"{n} ({s.get('id')}): ofset_sn artmalı ({onceki} -> {o})")
        if isinstance(o, int):
            onceki = o

    hizmetler = tanim["hizmetler"]
    for ad, hz in hizmetler.items():
        g = hz.get("gunler")
        if not _KIMLIK.fullmatch(ad):
            h.append(f"hizmetler.{ad}: ad küçük harf/rakam/alt çizgi olmalı")
        if not (isinstance(g, list) and len(g) == 7 and all(x in (0, 1) for x in g) and any(g)):
            h.append(f"hizmetler.{ad}: 'gunler' Pazartesi..Pazar için 0/1 içeren 7 elemanlı liste olmalı (en az bir 1)")

    hat_idleri = set()
    for i, hat in enumerate(tanim["hatlar"]):
        if not _KIMLIK.fullmatch(str(hat.get("id", ""))):
            h.append(f"hatlar[{i}]: id küçük harf/rakam/alt çizgi olmalı")
        if hat.get("id") in hat_idleri:
            h.append(f"hatlar[{i}]: tekrarlanan id {hat.get('id')!r}")
        hat_idleri.add(hat.get("id"))
        if not str(hat.get("kisa_ad", "")).strip():
            h.append(f"hatlar[{i}]: kisa_ad boş")

    kalip_idleri = set()
    for i, k in enumerate(tanim["kaliplar"]):
        n = f"kaliplar[{i}] ({k.get('id')})"
        if not _KIMLIK.fullmatch(str(k.get("id", ""))):
            h.append(f"{n}: id küçük harf/rakam/alt çizgi olmalı")
        if k.get("id") in kalip_idleri:
            h.append(f"{n}: tekrarlanan id")
        kalip_idleri.add(k.get("id"))
        if k.get("hat") not in hat_idleri:
            h.append(f"{n}: bilinmeyen hat {k.get('hat')!r}")
        if k.get("yon") not in (0, 1):
            h.append(f"{n}: yon 0 ya da 1 olmalı")
        if not str(k.get("baslik", "")).strip():
            h.append(f"{n}: baslik boş")
        for alan in ("nereden", "nereye"):
            if k.get(alan) not in kimlikler:
                h.append(f"{n}: bilinmeyen istasyon {alan}={k.get(alan)!r}")
        if k.get("nereden") == k.get("nereye"):
            h.append(f"{n}: nereden ve nereye aynı")
        if not k.get("seferler"):
            h.append(f"{n}: seferler boş")
        for j, sf in enumerate(k.get("seferler", [])):
            if sf.get("hizmet") not in hizmetler:
                h.append(f"{n}.seferler[{j}]: bilinmeyen hizmet {sf.get('hizmet')!r}")
            if not sf.get("araliklar"):
                h.append(f"{n}.seferler[{j}]: araliklar boş")
            for m, a in enumerate(sf.get("araliklar", [])):
                nn = f"{n}.seferler[{j}].araliklar[{m}]"
                ilk, son = _zaman(a.get("ilk"), h, nn), _zaman(a.get("son"), h, nn)
                if ilk is not None and son is not None and son < ilk:
                    h.append(f"{nn}: son ({a.get('son')}) ilk'ten ({a.get('ilk')}) önce")
                ar = a.get("aralik_dk")
                if not isinstance(ar, int) or ar <= 0:
                    h.append(f"{nn}: aralik_dk pozitif tam sayı olmalı: {ar!r}")
    if h:
        raise ValueError("Marmaray tanımı geçersiz: " + "; ".join(h))


def kalkis_pencereleri(ilk_sn: int, son_sn: int, aralik_sn: int) -> List[Tuple[int, int, int]]:
    """"İlk sefer ... son sefer ... her X dakikada bir" kuralını GTFS frequency pencerelerine çevirir.

    Gerçek tarifelerde son sefer çoğu zaman aralık ızgarasına oturmaz (ör. 06:09'dan her 8 dk,
    son tren 21:54; ızgara 21:53'e denk gelir). İlk ve son sefer TAM olarak korunur:
      * ızgara son seferle çakışırsa tek pencere,
      * ızgaranın son noktası son seferden `aralik/2`'den daha yakınsa o nokta son seferle değiştirilir
        (art arda iki tren oluşmasın),
      * aksi halde ızgaranın ardına son sefer ayrıca eklenir.
    Pencere uçları [başlangıç, bitiş) biçimindedir; bitiş saniyesi dahil değildir.
    Döndürülen her üçlü: (başlangıç_sn, bitiş_sn, aralık_sn).
    """
    if aralik_sn <= 0:
        raise ValueError("aralik_sn pozitif olmalı")
    if son_sn < ilk_sn:
        raise ValueError("son, ilk'ten önce olamaz")
    n = (son_sn - ilk_sn) // aralik_sn
    son_izgara = ilk_sn + n * aralik_sn
    if son_izgara == son_sn:
        return [(ilk_sn, son_sn + 1, aralik_sn)]
    if n == 0:
        return [(ilk_sn, ilk_sn + 1, aralik_sn), (son_sn, son_sn + 1, aralik_sn)]
    if (son_sn - son_izgara) * 2 < aralik_sn:
        return [(ilk_sn, son_izgara, aralik_sn), (son_sn, son_sn + 1, aralik_sn)]
    return [(ilk_sn, son_izgara + 1, aralik_sn), (son_sn, son_sn + 1, aralik_sn)]


def hms(sn: int) -> str:
    """Saniye -> "SS:DD:SN" (24 saati aşabilir)."""
    return f"{sn // 3600:02d}:{sn % 3600 // 60:02d}:{sn % 60:02d}"


def _yaz(yol: str, baslik: List[str], satirlar: List[list]) -> int:
    with open(yol, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(baslik)
        w.writerows(satirlar)
    return len(satirlar)


def gtfs_uret(tanim: dict, hedef_klasor: str) -> Dict[str, int]:
    """Tanımdan GTFS dosyalarını `hedef_klasor`e yazar; dosya başına satır sayısını döndürür.

    Her kalıp × hizmet için bir ŞABLON sefer üretilir (saatleri 00:00:00'dan başlar) ve
    `frequencies.csv` o şablonun hangi saatlerde kaç dakikada bir tekrarlandığını söyler.
    İstasyonlar arası süreler `ofset_sn` farklarından gelir; ters yönde aynı süreler kullanılır.
    """
    dogrula(tanim)
    os.makedirs(hedef_klasor, exist_ok=True)
    yol = lambda ad: os.path.join(hedef_klasor, f"{ad}.csv")
    b = tanim["besleme"]
    baslangic = (b.get("veri_tarihi") or "2026-01-01").replace("-", "")
    ist = tanim["istasyonlar"]
    sira = {s["id"]: i for i, s in enumerate(ist)}
    sayim: Dict[str, int] = {}

    sayim["agency"] = _yaz(yol("agency"), ["agency_id", "agency_name", "agency_url", "agency_timezone"],
                           [[tanim["kurum"]["id"], tanim["kurum"]["ad"], tanim["kurum"].get("url", ""), "Europe/Istanbul"]])
    sayim["calendar"] = _yaz(
        yol("calendar"), ["service_id", *GUN_SUTUNLARI, "start_date", "end_date"],
        [[ad, *hz["gunler"], baslangic, "20991231"] for ad, hz in tanim["hizmetler"].items()])
    # route_type=2 (raylı): mod, yükleyicide hesaplanır
    sayim["routes"] = _yaz(
        yol("routes"), ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
        [[h["id"], tanim["kurum"]["id"], h["kisa_ad"], h.get("uzun_ad", ""), 2] for h in tanim["hatlar"]])

    kullanilan = set()
    trips, stop_times, frekans = [], [], []
    for k in tanim["kaliplar"]:
        i, j = sira[k["nereden"]], sira[k["nereye"]]
        adim = 1 if j > i else -1
        indeksler = list(range(i, j + adim, adim))
        for ix in indeksler:
            kullanilan.add(ix)
        for sf in k["seferler"]:
            sefer_id = f"{k['id']}_{sf['hizmet']}"
            trips.append([k["hat"], sf["hizmet"], sefer_id, k["baslik"], k["yon"]])
            for sn_no, ix in enumerate(indeksler, 1):
                t = hms(abs(ist[ix]["ofset_sn"] - ist[i]["ofset_sn"]))
                stop_times.append([sefer_id, t, t, ist[ix]["id"], sn_no])
            for a in sf["araliklar"]:
                ilk, son = parse_time(a["ilk"]), parse_time(a["son"])
                for bas, bit, ar in kalkis_pencereleri(ilk, son, a["aralik_dk"] * 60):
                    frekans.append([sefer_id, hms(bas), hms(bit), ar, 0])
    sayim["trips"] = _yaz(yol("trips"), ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"], trips)
    sayim["stop_times"] = _yaz(yol("stop_times"), ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
                               stop_times)
    sayim["frequencies"] = _yaz(yol("frequencies"), ["trip_id", "start_time", "end_time", "headway_secs", "exact_times"],
                                frekans)
    sayim["stops"] = _yaz(
        yol("stops"), ["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon", "location_type"],
        [[ist[ix]["id"], "", ist[ix]["ad"], "", ist[ix]["enlem"], ist[ix]["boylam"], 0] for ix in sorted(kullanilan)])
    return sayim

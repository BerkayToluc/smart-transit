"""Vapur tarifesi (Şehir Hatları): sefer saatleri tek tek yazılmış veri dosyasından GTFS üretir.

Neden ayrı bir biçim: vapurun güncel, makinece okunabilir bir tarifesi yoktur; resmi kaynak,
Şehir Hatları'nın tarife kitapçığıdır ve her iskelenin her kalkış saatini tek tek verir. Marmaray'daki
gibi "her 15 dakikada bir" kuralı yazmak yerine saatler olduğu gibi (`data/vapur.json`) tutulur;
böylece düzensiz seferler de (ör. Ortaköy hattı, gece seferleri) tarifedeki gibi kalır.

Dosyadaki her sefer grubu: hat, hizmet (gün tipi), yön ve DURAK DİZİSİ. `saatler` listesinin her
elemanı, o dizideki duraklar için boşlukla ayrılmış saatlerdir ("06:10 06:35" = Kadıköy 06:10,
Karaköy 06:35). 24:00 sonrası "25:00" gibi yazılır. `binis_yok` listesindeki duraklardan yolcu alınmaz.

Her sefer ayrı bir GTFS seferidir (frekans yok): saatler tarifedeki gibi birebir korunur.
"""
import json
import os
import re
from typing import Dict, List

from app.gtfs.manual import BOYLAM_ARALIGI, ENLEM_ARALIGI, GUN_SUTUNLARI, _KIMLIK, _yaz, hms
from app.gtfs.reader import parse_time


def tanim_oku(yol: str) -> dict:
    with open(yol, encoding="utf-8") as f:
        tanim = json.load(f)
    dogrula(tanim)
    return tanim


def dogrula(tanim: dict) -> None:
    """Tanımı denetler; sorunların tümünü tek bir ValueError'da toplar."""
    h: List[str] = []
    for anahtar in ("besleme", "kurum", "iskeleler", "hizmetler", "hatlar", "seferler"):
        if anahtar not in tanim:
            h.append(f"'{anahtar}' bölümü yok")
    if h:
        raise ValueError("; ".join(h))

    iskeleler = set()
    for i, s in enumerate(tanim["iskeleler"]):
        n = f"iskeleler[{i}] ({s.get('id')})"
        if not _KIMLIK.fullmatch(str(s.get("id", ""))):
            h.append(f"{n}: id küçük harf/rakam/alt çizgi olmalı")
        if s.get("id") in iskeleler:
            h.append(f"{n}: tekrarlanan id")
        iskeleler.add(s.get("id"))
        if not str(s.get("ad", "")).strip():
            h.append(f"{n}: ad boş")
        if not (isinstance(s.get("enlem"), (int, float)) and ENLEM_ARALIGI[0] <= s["enlem"] <= ENLEM_ARALIGI[1]):
            h.append(f"{n}: enlem İstanbul bölgesinde değil: {s.get('enlem')!r}")
        if not (isinstance(s.get("boylam"), (int, float)) and BOYLAM_ARALIGI[0] <= s["boylam"] <= BOYLAM_ARALIGI[1]):
            h.append(f"{n}: boylam İstanbul bölgesinde değil: {s.get('boylam')!r}")

    for ad, hz in tanim["hizmetler"].items():
        g = hz.get("gunler")
        if not _KIMLIK.fullmatch(ad):
            h.append(f"hizmetler.{ad}: ad küçük harf/rakam/alt çizgi olmalı")
        if not (isinstance(g, list) and len(g) == 7 and all(x in (0, 1) for x in g) and any(g)):
            h.append(f"hizmetler.{ad}: 'gunler' 7 elemanlı 0/1 listesi olmalı (en az bir 1)")

    hatlar = set()
    for i, hat in enumerate(tanim["hatlar"]):
        if not _KIMLIK.fullmatch(str(hat.get("id", ""))):
            h.append(f"hatlar[{i}]: id küçük harf/rakam/alt çizgi olmalı")
        if hat.get("id") in hatlar:
            h.append(f"hatlar[{i}]: tekrarlanan id {hat.get('id')!r}")
        hatlar.add(hat.get("id"))
        if not str(hat.get("kisa_ad", "")).strip():
            h.append(f"hatlar[{i}]: kisa_ad boş")

    for i, g in enumerate(tanim["seferler"]):
        n = f"seferler[{i}] ({g.get('hat')}/{g.get('hizmet')})"
        if g.get("hat") not in hatlar:
            h.append(f"{n}: bilinmeyen hat {g.get('hat')!r}")
        if g.get("hizmet") not in tanim["hizmetler"]:
            h.append(f"{n}: bilinmeyen hizmet {g.get('hizmet')!r}")
        if g.get("yon") not in (0, 1):
            h.append(f"{n}: yon 0 ya da 1 olmalı")
        duraklar = g.get("duraklar") or []
        if len(duraklar) < 2:
            h.append(f"{n}: en az 2 durak gerekli")
        for d in duraklar:
            if d not in iskeleler:
                h.append(f"{n}: bilinmeyen iskele {d!r}")
        for d in g.get("binis_yok", []):
            if d not in duraklar:
                h.append(f"{n}: binis_yok'taki {d!r} dizide yok")
        if not g.get("saatler"):
            h.append(f"{n}: saatler boş")
        for j, satir in enumerate(g.get("saatler", [])):
            parcalar = str(satir).split()
            if len(parcalar) != len(duraklar):
                h.append(f"{n}.saatler[{j}]: {len(duraklar)} saat bekleniyordu: {satir!r}")
                continue
            sn = [parse_time(p) if re.fullmatch(r"\d{1,2}:\d{2}", p) else None for p in parcalar]
            if None in sn:
                h.append(f"{n}.saatler[{j}]: geçersiz saat {satir!r}")
            elif sn != sorted(sn) or len(set(sn)) != len(sn):
                h.append(f"{n}.saatler[{j}]: saatler artan olmalı {satir!r}")
    if h:
        raise ValueError("Vapur tanımı geçersiz: " + "; ".join(h))


def gtfs_uret(tanim: dict, hedef_klasor: str) -> Dict[str, int]:
    """Tanımdan GTFS dosyalarını yazar; dosya başına satır sayısını döndürür."""
    dogrula(tanim)
    os.makedirs(hedef_klasor, exist_ok=True)
    yol = lambda ad: os.path.join(hedef_klasor, f"{ad}.csv")
    baslangic = (tanim["besleme"].get("veri_tarihi") or "2026-01-01").replace("-", "")
    iskele = {s["id"]: s for s in tanim["iskeleler"]}
    ad_of = {s["id"]: s["ad"] for s in tanim["iskeleler"]}
    sayim: Dict[str, int] = {}

    sayim["agency"] = _yaz(yol("agency"), ["agency_id", "agency_name", "agency_url", "agency_timezone"],
                           [[tanim["kurum"]["id"], tanim["kurum"]["ad"], tanim["kurum"].get("url", ""), "Europe/Istanbul"]])
    sayim["calendar"] = _yaz(
        yol("calendar"), ["service_id", *GUN_SUTUNLARI, "start_date", "end_date"],
        [[ad, *hz["gunler"], baslangic, "20991231"] for ad, hz in tanim["hizmetler"].items()])
    # route_type=4 (vapur)
    sayim["routes"] = _yaz(
        yol("routes"), ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
        [[h["id"], tanim["kurum"]["id"], h["kisa_ad"], h.get("uzun_ad", ""), 4] for h in tanim["hatlar"]])

    trips, stop_times, kullanilan = [], [], set()
    for g in tanim["seferler"]:
        duraklar = g["duraklar"]
        kullanilan.update(duraklar)
        for satir in g["saatler"]:
            saatler = [parse_time(p) for p in satir.split()]
            sefer_id = f"{g['hat']}_{g['hizmet']}_{g['yon']}_{duraklar[0]}_{satir.split()[0].replace(':', '')}"
            trips.append([g["hat"], g["hizmet"], sefer_id, ad_of[duraklar[-1]], g["yon"]])
            for no, (d, sn) in enumerate(zip(duraklar, saatler), 1):
                binis = 1 if d in g.get("binis_yok", []) else 0
                stop_times.append([sefer_id, hms(sn), hms(sn), d, no, binis])
    sayim["trips"] = _yaz(yol("trips"), ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id"], trips)
    sayim["stop_times"] = _yaz(
        yol("stop_times"), ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence", "pickup_type"],
        stop_times)
    sayim["stops"] = _yaz(
        yol("stops"), ["stop_id", "stop_code", "stop_name", "stop_desc", "stop_lat", "stop_lon", "location_type"],
        [[d, "", iskele[d]["ad"], "", iskele[d]["enlem"], iskele[d]["boylam"], 0] for d in iskele if d in kullanilan])
    return sayim

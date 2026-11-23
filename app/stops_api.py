"""Durak arama ve yakındaki duraklar (#14): `GET /api/stops/search`, `GET /api/stops/nearby`.

Rota grafı bellekte olduğundan sorgular veritabanına gitmez. Aynı fiziksel istasyonun ayrı durakları (iki yön, metro girişleri vb.)
tek satırda gruplanır: aynı (Türkçe karakterden bağımsız) ad ve en çok `GRUP_YARICAP_M` içinde.
"""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from cachetools import LRUCache
from fastapi import APIRouter, Depends, HTTPException, Query

from app.gtfs.textfix import ascii_katla
from app.guvenlik import hiz_siniri
from app.plan_api import ISTANBUL_BOYLAM, ISTANBUL_ENLEM
from app.routing import servis
from app.routing.graph import Graf, mesafe_m

router = APIRouter()
GRUP_YARICAP_M = 400.0
EN_COK_HAT = 12
OTOBUS_GRUP_SINIRI = 5            # arama sonucunda yalnızca otobüs durakları en çok bu kadar satır (istasyon türleri önde)
_indeks_onbellek: LRUCache = LRUCache(maxsize=2)


def _graf() -> Graf:
    g = servis.graf_al()
    if g is None or g.durak_sayisi == 0:
        raise HTTPException(status_code=503, detail="Rota verisi hazır değil.")
    return g


def _ad_indeksi(g: Graf) -> List[Tuple[str, int]]:
    """(katlanmış ad, durak) listesi; yalnızca seferi olan duraklar. Graf sürümüne göre önbelleklenir."""
    anahtar = servis.surum()
    if anahtar not in _indeks_onbellek:
        _indeks_onbellek[anahtar] = [(ascii_katla(ad), i) for i, ad in enumerate(g.durak_ad) if g.durak_paternleri[i]]
    return _indeks_onbellek[anahtar]


def _modlar_ve_hatlar(g: Graf, uyeler: List[int]) -> Tuple[List[str], List[str]]:
    modlar, hatlar = set(), {}
    for i in uyeler:
        for pi, _ in g.durak_paternleri[i]:
            p = g.paternler[pi]
            modlar.add(p.mod)
            hatlar.setdefault(g.hat_kisa[p.hat], p.mod)
    # raylı/vapur/metrobüs hatları önde, sonra alfabetik
    sirali = sorted(hatlar, key=lambda h: (hatlar[h] == "bus", h))
    return sorted(modlar), sirali[:EN_COK_HAT]


def _grupla(g: Graf, adaylar: List[int]) -> List[List[int]]:
    """Aynı katlanmış ada sahip ve birbirine GRUP_YARICAP_M içindeki durakları gruplar (girdi sırası korunur)."""
    gruplar: List[List[int]] = []
    ad_gruplari: Dict[str, List[List[int]]] = defaultdict(list)
    for i in adaylar:
        ad = ascii_katla(g.durak_ad[i])
        for grup in ad_gruplari[ad]:
            if mesafe_m(g.durak_lat[i], g.durak_lon[i], g.durak_lat[grup[0]], g.durak_lon[grup[0]]) <= GRUP_YARICAP_M:
                grup.append(i)
                break
        else:
            yeni = [i]
            ad_gruplari[ad].append(yeni)
            gruplar.append(yeni)
    return gruplar


def _satir(g: Graf, uyeler: List[int], mesafe: Optional[float] = None) -> dict:
    modlar, hatlar = _modlar_ve_hatlar(g, uyeler)
    ilk = uyeler[0]
    d = {"name": g.durak_ad[ilk], "lat": g.durak_lat[ilk], "lng": g.durak_lon[ilk], "stop_ids": [g.durak_id[i] for i in uyeler],
         "stop_id": g.durak_id[ilk], "modes": modlar, "routes": hatlar}
    if mesafe is not None:
        d["distance_m"] = round(mesafe)
    return d


@router.get("/api/stops/search", dependencies=[Depends(hiz_siniri("stops", 120))])
def durak_ara(q: str = Query(..., min_length=3, max_length=60, description="Durak adı (Türkçe karakterden bağımsız)"),
              limit: int = Query(12, ge=1, le=30)):
    g = _graf()
    aranan = ascii_katla(q.strip())
    if len(aranan) < 3:
        raise HTTPException(status_code=422, detail="En az 3 harf girin.")
    onek, icerir = [], []
    for ad, i in _ad_indeksi(g):
        if ad.startswith(aranan) or (" " + aranan) in ad:
            onek.append(i)
        elif aranan in ad:
            icerir.append(i)
    gruplar = _grupla(g, onek + icerir)
    istasyon, otobus = [], []
    for grup in gruplar:
        satir = _satir(g, grup)
        (otobus if satir["modes"] == ["bus"] else istasyon).append(satir)
    sonuc = (istasyon + otobus[:OTOBUS_GRUP_SINIRI])[:limit]
    return {"stops": sonuc}


@router.get("/api/stops/nearby", dependencies=[Depends(hiz_siniri("stops", 120))])
def yakin_duraklar(lat: float = Query(..., ge=ISTANBUL_ENLEM[0], le=ISTANBUL_ENLEM[1]),
                   lng: float = Query(..., ge=ISTANBUL_BOYLAM[0], le=ISTANBUL_BOYLAM[1]),
                   radius_m: int = Query(500, ge=100, le=1500), limit: int = Query(20, ge=1, le=50)):
    g = _graf()
    yakin = g.yakin_duraklar(lat, lng, radius_m)                 # mesafeye göre sıralı
    mesafe = dict(yakin)
    sonuc = [_satir(g, grup, min(mesafe[i] for i in grup)) for grup in _grupla(g, [i for i, _ in yakin])]
    sonuc.sort(key=lambda s: s["distance_m"])
    return {"stops": sonuc[:limit]}

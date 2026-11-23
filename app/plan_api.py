"""POST /api/plan: koordinattan koordinata aktarmalı rota (RAPTOR, bkz. app/routing/)."""
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app import saglik
from app.routing import plan, servis
from app.routing.graph import mesafe_m

from app.guvenlik import hiz_siniri  # noqa: E402

router = APIRouter()
_plan_onbellek = TTLCache(maxsize=256, ttl=30)
_plan_kilit = threading.Lock()

# Türkiye kalıcı UTC+3 (2016'dan beri yaz saati yok); Windows'ta tz veritabanı olmadığından sabit ofset.
TR = timezone(timedelta(hours=3))
ISTANBUL_ENLEM = (40.7, 41.7)
ISTANBUL_BOYLAM = (27.8, 30.0)
MODLAR = ("bus", "metrobus", "metro", "tram", "funicular", "cable_car", "rail", "ferry")
TERCIH = {"fastest": "hizli", "fewest_transfers": "az_aktarma", "least_walking": "az_yuruyus"}


class Nokta(BaseModel):
    lat: float = Field(..., ge=ISTANBUL_ENLEM[0], le=ISTANBUL_ENLEM[1], description="Enlem (İstanbul sınırları içinde)")
    lng: float = Field(..., ge=ISTANBUL_BOYLAM[0], le=ISTANBUL_BOYLAM[1], description="Boylam (İstanbul sınırları içinde)")
    name: Optional[str] = Field(None, max_length=120)


class PlanIstegi(BaseModel):
    origin: Nokta
    dest: Nokta
    depart_at: Optional[datetime] = Field(None, description="Kalkış anı (ISO 8601). Saat dilimi yoksa İstanbul saati. Boşsa şimdi.")
    arrive_by: Optional[datetime] = Field(None, description="Varış anı (ISO 8601): bu saatte ya da daha önce varacak, EN GEÇ kalkışlı rotalar.")
    modes: Optional[List[Literal[MODLAR]]] = Field(None, description=f"İzinli modlar; boşsa hepsi: {', '.join(MODLAR)}")
    max_transfers: int = Field(3, ge=0, le=5)
    max_walk_m: int = Field(800, ge=100, le=2000, description="Başlangıç/varışta durağa en çok yürüme (m)")
    preference: Literal["fastest", "fewest_transfers", "least_walking"] = "fastest"
    max_results: int = Field(3, ge=1, le=5)

    @model_validator(mode="after")
    def _zaman_cakismasi(self):
        if self.depart_at is not None and self.arrive_by is not None:
            raise ValueError("depart_at ve arrive_by birlikte verilemez")
        return self


class YerBilgisi(BaseModel):
    name: str
    lat: float
    lng: float
    stop_id: Optional[str] = None
    time: str = Field(..., description="ISO 8601, +03:00")


class Etap(BaseModel):
    type: Literal["walk", "transit"]
    mode: str                                   # walk | bus | metro | ferry ...
    route_short_name: Optional[str] = None
    route_long_name: Optional[str] = None
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    headsign: Optional[str] = None
    from_: YerBilgisi = Field(..., alias="from")
    to: YerBilgisi
    num_stops: int = 0
    duration: int = Field(..., description="saniye")
    distance_m: Optional[float] = Field(None, description="yalnız yürüme etabı")
    polyline: List[List[float]] = Field(..., description="[[enlem, boylam], ...]")
    geometry: Optional[Literal["resmi", "durak"]] = Field(
        None, description="transit etabı: 'resmi' = İETT resmî hat güzergahından kesilmiş çizgi, 'durak' = durak sırası çizgisi")

    model_config = {"populate_by_name": True}


class Yolculuk(BaseModel):
    departure_time: str
    arrival_time: str
    total_duration: int
    transfers: int
    walk_distance: float
    legs: List[Etap]


class PlanYaniti(BaseModel):
    itineraries: List[Yolculuk]
    neden: Optional[str] = None
    mesaj: Optional[str] = None


def _yerel(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return datetime.now(TR)
    return dt.replace(tzinfo=TR) if dt.tzinfo is None else dt.astimezone(TR)


def _iso(gun0: datetime, sn: int) -> str:
    return (gun0 + timedelta(seconds=int(sn))).isoformat()


def _etap(g, e, o, d, gun0: datetime, guz=None) -> dict:
    def yer(i, nokta, sn):
        if i < 0:
            return {"name": nokta.name or ("Başlangıç" if nokta is o else "Varış"), "lat": nokta.lat, "lng": nokta.lng,
                    "stop_id": None, "time": _iso(gun0, sn)}
        return {"name": g.durak_ad[i], "lat": g.durak_lat[i], "lng": g.durak_lon[i], "stop_id": g.durak_id[i],
                "time": _iso(gun0, sn)}

    bas, bit = yer(e.bas, o, e.kalkis), yer(e.bit, d, e.varis)
    if e.tip == "yurume":
        mesafe = mesafe_m(bas["lat"], bas["lng"], bit["lat"], bit["lng"]) * plan.YURUME_KATSAYISI
        return {"type": "walk", "mode": "walk", "from": bas, "to": bit, "num_stops": 0, "duration": e.varis - e.kalkis,
                "distance_m": round(mesafe, 1), "polyline": [[bas["lat"], bas["lng"]], [bit["lat"], bit["lng"]]]}
    p = g.paternler[e.patern]
    cizgi = [[g.durak_lat[p.duraklar[k]], g.durak_lon[p.duraklar[k]]] for k in range(e.bas_sira, e.bit_sira + 1)]
    geometri = "durak"
    if guz is not None and e.mod in ("bus", "metrobus"):
        kesit = guz.dilimle(g.hat_kisa[e.hat], (bas["lat"], bas["lng"]), (bit["lat"], bit["lng"]))
        if kesit:
            cizgi, geometri = [[la, lo] for la, lo in kesit], "resmi"
    return {"type": "transit", "mode": e.mod, "route_short_name": g.hat_kisa[e.hat] or None,
            "route_long_name": g.hat_uzun[e.hat] or None, "route_id": g.hat_id[e.hat],
            "trip_id": g.meta_sefer_id[e.meta], "headsign": g.meta_baslik[e.meta] or None, "from": bas, "to": bit,
            "num_stops": e.durak_sayisi, "duration": e.varis - e.kalkis, "polyline": cizgi,
            "geometry": geometri}


ARAMA_PENCERESI_SN = 4 * 3600      # varışa göre aramada en erken kalkış: varıştan 4 saat önce
ARAMA_COZUNURLUK_SN = 60


def _varisa_gore(g, bas, bit, gun, t_sn, ortak):
    """`t_sn`'ye kadar varan en GEÇ kalkışlı seçenekler. Varış saati kalkışla azalmayan arttığından (daha geç
    kalkan daha geç varır) ikili arama: en geç uygun kalkışı 1 dk çözünürlükle bulur."""
    lo = max(0, t_sn - ARAMA_PENCERESI_SN)
    hi = t_sn

    def dene(d, cesitlilik=False):
        return [s for s in plan.planla(g, bas, bit, gun, d, cesitlilik=cesitlilik, **ortak) if s.varis <= t_sn]

    en_iyi = dene(lo)
    if not en_iyi:
        return []                      # 4 saat önce çıkılsa da yetişilmiyor
    while hi - lo > ARAMA_COZUNURLUK_SN:
        orta = (lo + hi) // 2
        uygun = dene(orta)
        if uygun:
            lo, en_iyi = orta, uygun
        else:
            hi = orta
    return dene(lo, cesitlilik=True) or en_iyi      # çeşitli alternatifler yalnızca bulunan kalkış anı için aranır (hız)


@router.get("/api/plan/durum")
def plan_durum():
    """Rota grafının hazır olup olmadığı (açılışta arka planda yüklenir)."""
    return servis.durum()


@router.post("/api/plan", response_model=PlanYaniti, response_model_exclude_none=True,
             dependencies=[Depends(hiz_siniri("plan", 60))])
def plan_et(istek: PlanIstegi):
    # Kısa TTL önbellek (aynı graf sürümü + aynı istek; "şimdi" istekleri dakikaya göre ayrılır). Hata yanıtları önbelleklenmez.
    anahtar = (servis.surum(), istek.model_dump_json(),
               int(time.time() // 60) if istek.depart_at is None and istek.arrive_by is None else None)
    with _plan_kilit:
        bulunan = _plan_onbellek.get(anahtar)
    if bulunan is not None:
        saglik.plan_onbellek["isabet"] += 1
        return bulunan
    saglik.plan_onbellek["iskalama"] += 1
    sonuc = _plan_hesapla(istek)
    with _plan_kilit:
        _plan_onbellek[anahtar] = sonuc
    return sonuc


def _plan_hesapla(istek: PlanIstegi):
    g = servis.graf_al()
    if g is None or g.durak_sayisi == 0:
        d = servis.durum()
        if d["hata"]:
            raise HTTPException(status_code=503, detail=f"Rota verisi yüklenemedi: {d['hata']}")
        if d["yukleniyor"]:
            raise HTTPException(status_code=503, detail="Rota verisi hazırlanıyor, birkaç dakika sonra tekrar deneyin.")
        raise HTTPException(status_code=503, detail=(
            "Rota verisi (GTFS) yüklü değil. `python scripts/build_gtfs.py hepsi ...` ve `aktarma` ile veriyi yükleyin."))
    o, d_ = istek.origin, istek.dest
    ortak = dict(izinli_modlar=istek.modes, max_aktarma=istek.max_transfers, max_yurume_m=istek.max_walk_m,
                 tercih=TERCIH[istek.preference], en_cok=istek.max_results)
    if istek.arrive_by is not None:
        hedef = _yerel(istek.arrive_by)
        gun0 = hedef.replace(hour=0, minute=0, second=0, microsecond=0)
        t_sn = hedef.hour * 3600 + hedef.minute * 60 + hedef.second
        secenekler = _varisa_gore(g, (o.lat, o.lng), (d_.lat, d_.lng), hedef.weekday(), t_sn, ortak)
    else:
        baslangic = _yerel(istek.depart_at)
        gun0 = baslangic.replace(hour=0, minute=0, second=0, microsecond=0)
        saat_sn = baslangic.hour * 3600 + baslangic.minute * 60 + baslangic.second
        secenekler = plan.planla(g, (o.lat, o.lng), (d_.lat, d_.lng), baslangic.weekday(), saat_sn, **ortak)
    if not secenekler:
        neden, mesaj = "baglanti_yok", "Bu iki nokta arasında seçili modlarla bir rota bulunamadı."
        if istek.arrive_by is not None:
            neden, mesaj = "yetismiyor", "Bu varış saatine yetişen bir rota bulunamadı. Daha geç bir varış saati deneyin."
        if istek.arrive_by is None and not g.yakin_duraklar(o.lat, o.lng, istek.max_walk_m):
            neden, mesaj = "baslangicta_durak_yok", f"Başlangıç noktasının {istek.max_walk_m} m çevresinde durak yok."
        elif istek.arrive_by is None and not g.yakin_duraklar(d_.lat, d_.lng, istek.max_walk_m):
            neden, mesaj = "varista_durak_yok", f"Varış noktasının {istek.max_walk_m} m çevresinde durak yok."
        return {"itineraries": [], "neden": neden, "mesaj": mesaj}
    guz = servis.guzergah_al()
    cikti = []
    for s in secenekler:
        etaplar = [_etap(g, e, o, d_, gun0, guz) for e in s.etaplar]
        cikti.append({"departure_time": _iso(gun0, s.kalkis), "arrival_time": _iso(gun0, s.varis),
                      "total_duration": s.sure, "transfers": s.aktarma, "walk_distance": round(s.yuruyus_m, 1),
                      "legs": etaplar})
    return {"itineraries": cikti}

"""POST /api/plan: koordinattan koordinata aktarmalı rota (RAPTOR, bkz. app/routing/)."""
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.routing import plan, servis
from app.routing.graph import mesafe_m

router = APIRouter()

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
    arrive_by: Optional[datetime] = Field(None, description="Henüz desteklenmiyor (501).")
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


def _etap(g, e, o, d, gun0: datetime) -> dict:
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
    return {"type": "transit", "mode": e.mod, "route_short_name": g.hat_kisa[e.hat] or None,
            "route_long_name": g.hat_uzun[e.hat] or None, "route_id": g.hat_id[e.hat],
            "trip_id": g.meta_sefer_id[e.meta], "headsign": g.meta_baslik[e.meta] or None, "from": bas, "to": bit,
            "num_stops": e.durak_sayisi, "duration": e.varis - e.kalkis, "polyline": cizgi}


@router.get("/api/plan/durum")
def plan_durum():
    """Rota grafının hazır olup olmadığı (açılışta arka planda yüklenir)."""
    return servis.durum()


@router.post("/api/plan", response_model=PlanYaniti, response_model_exclude_none=True)
def plan_et(istek: PlanIstegi):
    if istek.arrive_by is not None:
        raise HTTPException(status_code=501, detail="arrive_by henüz desteklenmiyor; depart_at kullanın.")
    g = servis.graf_al()
    if g is None or g.durak_sayisi == 0:
        d = servis.durum()
        if d["hata"]:
            raise HTTPException(status_code=503, detail=f"Rota verisi yüklenemedi: {d['hata']}")
        if d["yukleniyor"]:
            raise HTTPException(status_code=503, detail="Rota verisi hazırlanıyor, birkaç dakika sonra tekrar deneyin.")
        raise HTTPException(status_code=503, detail=(
            "Rota verisi (GTFS) yüklü değil. `python scripts/build_gtfs.py hepsi ...` ve `aktarma` ile veriyi yükleyin."))
    baslangic = _yerel(istek.depart_at)
    gun0 = baslangic.replace(hour=0, minute=0, second=0, microsecond=0)
    saat_sn = baslangic.hour * 3600 + baslangic.minute * 60 + baslangic.second
    o, d_ = istek.origin, istek.dest
    secenekler = plan.planla(
        g, (o.lat, o.lng), (d_.lat, d_.lng), baslangic.weekday(), saat_sn, izinli_modlar=istek.modes,
        max_aktarma=istek.max_transfers, max_yurume_m=istek.max_walk_m, tercih=TERCIH[istek.preference],
        en_cok=istek.max_results)
    if not secenekler:
        neden, mesaj = "baglanti_yok", "Bu iki nokta arasında seçili modlarla bir rota bulunamadı."
        if not g.yakin_duraklar(o.lat, o.lng, istek.max_walk_m):
            neden, mesaj = "baslangicta_durak_yok", f"Başlangıç noktasının {istek.max_walk_m} m çevresinde durak yok."
        elif not g.yakin_duraklar(d_.lat, d_.lng, istek.max_walk_m):
            neden, mesaj = "varista_durak_yok", f"Varış noktasının {istek.max_walk_m} m çevresinde durak yok."
        return {"itineraries": [], "neden": neden, "mesaj": mesaj}
    cikti = []
    for s in secenekler:
        etaplar = [_etap(g, e, o, d_, gun0) for e in s.etaplar]
        cikti.append({"departure_time": _iso(gun0, s.kalkis), "arrival_time": _iso(gun0, s.varis),
                      "total_duration": s.sure, "transfers": s.aktarma, "walk_distance": round(s.yuruyus_m, 1),
                      "legs": etaplar})
    return {"itineraries": cikti}

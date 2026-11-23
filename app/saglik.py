"""Sağlık ve izleme (#32): `/health`, istek süresi günlüğü, yavaş istek uyarısı, plan önbelleği metriği."""
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.routing import servis

router = APIRouter()
logger = logging.getLogger("smarttransit.istek")
if not logging.getLogger().handlers and not logger.handlers:      # uvicorn varsayılanında kök günlükçü sessizdir; istek satırları görünsün
    _isleyici = logging.StreamHandler()
    _isleyici.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_isleyici)
    logger.setLevel(logging.INFO)
YAVAS_ESIK_SN = 1.0

# Plan önbelleği isabet/ıskalama sayaçları (app/plan_api.py günceller)
plan_onbellek = {"isabet": 0, "iskalama": 0}


def _veritabani() -> dict:
    from app.db import SessionLocal
    t0 = time.perf_counter()
    try:
        with SessionLocal() as oturum:
            oturum.execute(text("SELECT 1"))
        return {"durum": "ok", "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as e:  # noqa: BLE001 - sağlık ucu hata ayrıntısını bildirir, kendisi çökmemeli
        logger.warning("sağlık: veritabanı hatası: %r", e)
        return {"durum": "hata", "hata": type(e).__name__}


def _rota_grafi() -> dict:
    d = servis.durum()
    if d["hazir"]:
        return {"durum": "ok", "durak": d["durak"], "sefer": d["sefer"]}
    if d["yukleniyor"]:
        return {"durum": "yukleniyor"}
    return {"durum": "hata", "hata": d["hata"] or "Rota verisi yüklü değil"}


def _iett() -> dict:
    from app import live
    son = live.iett_son
    if son["ok"] is None:
        return {"durum": "bilinmiyor"}          # henüz canlı veri istenmedi; sağlık ucu dış servise istek atmaz
    return {"durum": "ok" if son["ok"] else "erisilemiyor", "saniye_once": round(time.monotonic() - son["an"], 1)}


@router.get("/health")
def health():
    """Bileşen bazlı durum. Veritabanı yoksa 503; rota grafı yüklenirken ya da İETT erişilemiyorken 200 + `degraded`."""
    bilesenler = {"veritabani": _veritabani(), "rota_grafi": _rota_grafi(), "iett": _iett()}
    toplam = sum(plan_onbellek.values())
    bilesenler["plan_onbellegi"] = {**plan_onbellek, "isabet_orani": round(plan_onbellek["isabet"] / toplam, 3) if toplam else None}
    if bilesenler["veritabani"]["durum"] != "ok":
        genel, kod = "down", 503
    elif bilesenler["rota_grafi"]["durum"] != "ok" or bilesenler["iett"]["durum"] == "erisilemiyor":
        genel, kod = "degraded", 200
    else:
        genel, kod = "ok", 200
    return JSONResponse({"durum": genel, "bilesenler": bilesenler}, status_code=kod)


async def istek_suresi_gunlugu(request: Request, call_next):
    """Her istek için yöntem, yol, durum kodu ve süre; YAVAS_ESIK_SN üstü WARNING."""
    t0 = time.perf_counter()
    durum = 500
    try:
        yanit = await call_next(request)
        durum = yanit.status_code
        yanit.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.0f}"
        return yanit
    finally:
        sure = time.perf_counter() - t0
        seviye = logging.WARNING if sure > YAVAS_ESIK_SN else logging.INFO
        logger.log(seviye, "%s %s -> %s %.0f ms%s", request.method, request.url.path, durum, sure * 1000,
                   " YAVAS" if sure > YAVAS_ESIK_SN else "")

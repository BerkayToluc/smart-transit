"""SmartTransit API giriş noktası: uygulamayı kurar, router'ları bağlar.

İş mantığı `app/` paketindedir:
  app/db.py          bağlantı, modeller, get_db
  app/catalog.py     /, /api/hatlar, /api/duraklar, /api/guzergah
  app/live.py        İETT canlı araç + varış tahmini (/api/canli-otobus, /api/moovit)
  app/nearest.py     /api/en-yakin-durak
  app/plan_api.py    POST /api/plan (aktarmalı rota; motor: app/routing/)
  app/yaklasan.py    GET /api/yaklasan (iki durak arası hatlar + canlı araç varış tahmini)
  app/gtfs_admin.py  /api/admin/* ve GTFS metin/koordinat yardımcıları
  app/utils.py       ortak yardımcılar
  app/gtfs/          çok modlu GTFS şeması, okuyucu ve yükleyici (docs/schema.md)

Aşağıdaki yeniden dışa aktarımlar (`__all__`) eski kullanım için korunur:
`from main import engine, SessionLocal, Hat, Durak, ...` yazan betikler
(gtfs_yukle.py, veri_yukle.py, hat_ekleyici.py) ve testler çalışmaya devam eder.
Yeni kod `app.*` modüllerinden içe aktarmalıdır.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text  # noqa: F401  (eski betikler `from main import text` kullanıyor)

from app import catalog, gtfs_admin, guvenlik, live, nearest, plan_api, saglik, yaklasan
from app.routing import servis
from app.gtfs import models as _gtfs_models  # noqa: F401  (gtfs_* tablolarının açılışta oluşması için)
from app.db import (  # noqa: F401
    Base, DATABASE_URL, Durak, Guzergah, Hat, OtobusLive, SessionLocal, engine, get_db,
)
from app.gtfs_admin import (  # noqa: F401
    GEOJSON_DOSYA, GTFS_KLASORU, _ayrac_tespit_et, _geojson_guzergah_bul,
    _guzergah_esle_ve_kaydet, _koordinat_duzelt, _mojibake_duzelt, _route_kodu_parcala,
    _tum_hat_kodlarini_bul, gtfs_aktar, tum_hatlari_aktar, tum_hatlari_listele,
)
from app.live import (  # noqa: F401
    _noktayi_segmente_izdusur, _otobus_gecmisi, _otobus_rota_konumu, _rota_kumulatif_mesafe,
    canli_otobus_getir, iett_cache, iett_verisi_cek, moovit_dinamik_algoritma,
)
from app.nearest import EvrenselRotaIstegi, en_yakin_durak_bul  # noqa: F401
from app.utils import mesafe_hesapla_km  # noqa: F401


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    print("Mükemmel! Veritabanı bağlandı ve tablolar oluşturuldu.")
    if os.getenv("ROTA_GRAF_ARKA_PLAN", "1") != "0":
        servis.arka_planda_yukle()          # rota grafı: önbellekten/veritabanından, API'yi bekletmeden
    yield


app = FastAPI(title="SmartTransit API", lifespan=lifespan)

_izinli_originler, _kimlik_bilgisi = guvenlik.cors_ayarlari()      # CORS_ORIGINS ortam değişkeni (#29)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_izinli_originler,
    allow_credentials=_kimlik_bilgisi,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)

app.middleware("http")(saglik.istek_suresi_gunlugu)
app.include_router(saglik.router)
app.include_router(catalog.router)
app.include_router(live.router)
app.include_router(nearest.router)
app.include_router(plan_api.router)
app.include_router(yaklasan.router)
app.include_router(gtfs_admin.router)

"""Rota grafının süreç genelinde tek örneği (API tarafından kullanılır).

Veri kaynağı: `GTFS_DATABASE_URL` (örn. sqlite:///gtfs_data/gtfs.db); yoksa `DATABASE_URL`. Böylece canlı otobüs takibi
Neon'da kalırken rota yerel/ayrı bir veritabanından beslenebilir.

Graf büyüktür (İETT'li veride kurulumu ~1 dk): API açılırken arka plan iş parçacığında yüklenir
(önbellek varsa birkaç sn); hazır olana dek /api/plan 503 döner. Testler `graf_ayarla` ile kendi grafını koyar.
"""
import os
import threading
from typing import Optional

from app.routing.graph import Graf

ONBELLEK_YOLU = os.getenv("ROTA_GRAF_ONBELLEK", os.path.join("gtfs_data", "graf.pkl"))
_durum = {"graf": None, "hata": None, "yukleniyor": False}
_kilit = threading.Lock()


def graf_al() -> Optional[Graf]:
    return _durum["graf"]


def graf_ayarla(g: Optional[Graf]) -> None:
    with _kilit:
        _durum["graf"], _durum["hata"], _durum["yukleniyor"] = g, None, False


def durum() -> dict:
    g = _durum["graf"]
    return {"hazir": g is not None and g.durak_sayisi > 0, "yukleniyor": _durum["yukleniyor"], "hata": _durum["hata"],
            "durak": g.durak_sayisi if g else 0, "ornek": len(g.paternler) if g else 0,
            "sefer": g.sefer_sayisi() if g else 0}


def yukle() -> None:
    """Grafı (önbellekten ya da veritabanından) kurar; hata olursa durumda saklar."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db import SessionLocal, normalize_database_url
    from app.routing import graph
    with _kilit:
        if _durum["yukleniyor"]:
            return
        _durum["yukleniyor"], _durum["hata"] = True, None
    try:
        # GTFS verisi (rota) canlı takip veritabanından (Neon) ayrı olabilir: tam İETT verisi 500+ MB'dır.
        gtfs_url = os.getenv("GTFS_DATABASE_URL")
        oturum_fabrikasi = sessionmaker(bind=create_engine(normalize_database_url(gtfs_url))) if gtfs_url else SessionLocal
        with oturum_fabrikasi() as oturum:
            g = graph.yukle(oturum, ONBELLEK_YOLU)
        with _kilit:
            _durum["graf"] = g
    except Exception as e:  # noqa: BLE001  (API ayakta kalmalı; hata /api/plan/durum'da görünür)
        with _kilit:
            _durum["hata"] = f"{type(e).__name__}: {e}"
    finally:
        with _kilit:
            _durum["yukleniyor"] = False


def arka_planda_yukle() -> threading.Thread:
    t = threading.Thread(target=yukle, name="rota-graf", daemon=True)
    t.start()
    return t

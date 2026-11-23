"""Güvenlik yardımcıları (#29): CORS ayarı, yönetici anahtarı, istek hız sınırı.

Ortam değişkenleri:
  CORS_ORIGINS        virgülle ayrılmış izinli origin listesi (varsayılan: yerel geliştirme adresleri). `*` yazılırsa her origin
                      izinlidir ama kimlik bilgisi (cookie) kapatılır.
  ADMIN_API_KEY       /api/admin/* için anahtar (`X-Admin-Key` başlığı). Tanımlı değilse yönetici uç noktaları kapalıdır (403).
  RATE_LIMIT_DEVRE_DISI=1  hız sınırını kapatır (testler).
"""
import os
import secrets
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Tuple

from fastapi import Header, HTTPException, Request

VARSAYILAN_ORIGINLER = ("http://localhost:3000", "http://127.0.0.1:3000")


def cors_ayarlari() -> Tuple[List[str], bool]:
    """(izinli originler, kimlik bilgisine izin). `*` ile kimlik bilgisi birlikte kullanılmaz."""
    ham = os.getenv("CORS_ORIGINS", "").strip()
    if not ham:
        return list(VARSAYILAN_ORIGINLER), False
    originler = [o.strip().rstrip("/") for o in ham.split(",") if o.strip()]
    if "*" in originler:
        return ["*"], False
    return originler, False


def yonetici_anahtari_gerekli(x_admin_key: str = Header(None)) -> None:
    """`/api/admin/*` için bağımlılık: doğru `X-Admin-Key` yoksa 401/403."""
    beklenen = os.getenv("ADMIN_API_KEY", "")
    if not beklenen:
        raise HTTPException(status_code=403, detail="Yönetici uç noktaları kapalı (ADMIN_API_KEY tanımlı değil).")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, beklenen):
        raise HTTPException(status_code=401, detail="Geçersiz yönetici anahtarı.")


_ZAMANLAR: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)


def hiz_siniri(ad: str, limit: int, pencere_sn: int = 60) -> Callable:
    """İstemci IP'si başına `pencere_sn` saniyede en çok `limit` istek (bellek içi, tek süreç). Aşılırsa 429."""
    def bagimlilik(request: Request) -> None:
        if os.getenv("RATE_LIMIT_DEVRE_DISI") == "1":
            return
        ip = request.client.host if request.client else "?"
        kayit = _ZAMANLAR[(ad, ip)]
        simdi = time.monotonic()
        while kayit and simdi - kayit[0] > pencere_sn:
            kayit.popleft()
        if len(kayit) >= limit:
            bekle = max(1, int(pencere_sn - (simdi - kayit[0])))
            raise HTTPException(status_code=429, detail="Çok fazla istek; biraz sonra tekrar deneyin.",
                                headers={"Retry-After": str(bekle)})
        kayit.append(simdi)
    return bagimlilik

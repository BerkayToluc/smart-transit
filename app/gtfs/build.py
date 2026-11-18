"""Besleme indirme ve raporlama (scripts/build_gtfs.py bunu kullanır).

İndirme, İBB Açık Veri Portalı'nın CKAN API'sini (`package_show`) kullanır; dosya adresleri
koda sabit yazılmaz, böylece portaldaki kaynak kimlikleri değişse de çalışır.

NOT: Portal bulut sunucularından açılmıyor; bu işlemler yerel makinede çalıştırılmalıdır.
"""
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import requests
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.gtfs.feeds import IBB_MULTIMODAL, IETT, FeedConfig
from app.gtfs.loader import EXCEL_SATIR_SINIRI, _veri_satiri_say
from app.gtfs.models import (
    GtfsAgency, GtfsCalendar, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTrip,
)

PORTAL = "https://data.ibb.gov.tr"
# Düzeltilmemiş bozuk kodlamanın izleri: Å/Ã/Ä/Â (UTF-8'in yanlış okunması), C1 kontrol karakterleri,
# U+FFFD (çözülemeyen bayt). Gerçek Türkçe metinde bunlar neredeyse hiç görülmez.
SUPHELI_KARAKTER = re.compile("[ÅÃÄÂ\x80-\x9f\ufffd]")
GTFS_DOSYALARI = ("agency", "calendar", "calendar_dates", "routes", "stops", "stop_times", "trips",
                  "frequencies", "shapes", "transfers")


@dataclass(frozen=True)
class BeslemeKaynagi:
    config: FeedConfig
    paket: str         # portaldaki veri seti adı (CKAN "name")
    klasor: str        # varsayılan yerel klasör


BESLEMELER: Dict[str, BeslemeKaynagi] = {
    "iett": BeslemeKaynagi(IETT, "iett-gtfs-verisi", os.path.join("gtfs_data", "iett")),
    "ibb": BeslemeKaynagi(IBB_MULTIMODAL, "public-transport-gtfs-data", os.path.join("gtfs_data", "multimodal")),
}


# ---------------------------------------------------------------- indirme
def kaynak_listesi(paket: str, *, http_get: Callable = requests.get, portal: str = PORTAL) -> List[dict]:
    """Veri setindeki indirilecek GTFS dosyalarını döndürür: [{ad, url, boyut, bicim}, ...].

    Aynı dosya hem CSV hem ZIP olarak varsa **ZIP tercih edilir**: İETT'nin portaldaki
    `stop_times.csv` dosyası Excel'de kırpılmıştır (tam 1.048.575 satır), ZIP sürümü ise
    eksiksizdir (docs/veri-kaynaklari.md)."""
    yanit = http_get(f"{portal}/api/3/action/package_show", params={"id": paket}, timeout=60,
                     headers={"User-Agent": "SmartTransit/1.0"})
    yanit.raise_for_status()
    veri = yanit.json()
    if not veri.get("success"):
        raise RuntimeError(f"Portal '{paket}' veri setini döndürmedi: {veri.get('error')}")
    secilen: Dict[str, dict] = {}
    for k in veri["result"].get("resources", []):
        ad = (k.get("name") or "").strip().lower()
        bicim = (k.get("format") or "").upper()
        if ad not in GTFS_DOSYALARI or not k.get("url") or bicim not in ("CSV", "ZIP"):
            continue
        if ad in secilen and not (bicim == "ZIP" and secilen[ad]["bicim"] == "csv"):
            continue
        secilen[ad] = {"ad": ad, "url": k["url"], "boyut": k.get("size"), "bicim": bicim.lower()}
    return [secilen[a] for a in GTFS_DOSYALARI if a in secilen]


def indir(besleme: str, klasor: Optional[str] = None, *, http_get: Callable = requests.get,
          log: Callable[[str], None] = print, deneme: int = 3, portal: str = PORTAL) -> List[str]:
    """Beslemenin GTFS dosyalarını `klasor`e indirir. Boyutu portalla aynı olan dosyalar atlanır.
    Yarım kalmış indirmeler `.part` olarak yazılıp tamamlanınca adlandırılır."""
    kaynak = BESLEMELER[besleme]
    hedef = klasor or kaynak.klasor
    os.makedirs(hedef, exist_ok=True)
    dosyalar = kaynak_listesi(kaynak.paket, http_get=http_get, portal=portal)
    if not dosyalar:
        raise RuntimeError(f"'{kaynak.paket}' içinde indirilecek GTFS CSV dosyası bulunamadı")
    indirilen = []
    for d in dosyalar:
        csv_yol = os.path.join(hedef, f"{d['ad']}.csv")
        indirme_yolu = os.path.join(hedef, f"{d['ad']}.zip") if d["bicim"] == "zip" else csv_yol
        boyut = int(d["boyut"]) if d.get("boyut") else None
        if boyut and os.path.exists(indirme_yolu) and os.path.getsize(indirme_yolu) == boyut \
                and os.path.exists(csv_yol):
            log(f"  {d['ad']}.{d['bicim']} zaten var ({boyut:,} B), atlandı")
            continue
        for sira in range(1, deneme + 1):
            try:
                log(f"  {d['ad']}.{d['bicim']} indiriliyor...")
                _dosya_indir(d["url"], indirme_yolu, http_get)
                if d["bicim"] == "zip":
                    log(f"  {d['ad']}.zip içinden {d['ad']}.csv açılıyor...")
                    _zipten_ac(indirme_yolu, d["ad"], csv_yol)
                break
            except (requests.RequestException, OSError, zipfile.BadZipFile) as hata:
                if sira == deneme:
                    raise
                log(f"    hata ({hata}); {sira}/{deneme}. deneme, tekrar deneniyor")
                time.sleep(2 * sira)
        indirilen.append(csv_yol)
        if d["ad"] == "stop_times" and _veri_satiri_say(csv_yol) == EXCEL_SATIR_SINIRI:
            log(f"  ! UYARI: {csv_yol} tam {EXCEL_SATIR_SINIRI:,} veri satırı; Excel'de kırpılmış olabilir")
    return indirilen


def _zipten_ac(zip_yol: str, ad: str, hedef_csv: str) -> None:
    """ZIP içindeki `<ad>.csv` (ya da `.txt`) dosyasını diske akıtarak açar."""
    with zipfile.ZipFile(zip_yol) as z:
        uyeler = [i for i in z.infolist() if not i.is_dir()]
        adaylar = [i for i in uyeler if os.path.basename(i.filename).lower() in (f"{ad}.csv", f"{ad}.txt")]
        if not adaylar and len(uyeler) == 1:
            adaylar = uyeler
        if not adaylar:
            raise RuntimeError(f"{zip_yol} içinde {ad}.csv bulunamadı (içerik: {[u.filename for u in uyeler]})")
        gecici = hedef_csv + ".part"
        with z.open(adaylar[0]) as kaynak, open(gecici, "wb") as hedef:
            shutil.copyfileobj(kaynak, hedef, length=1024 * 1024)
    os.replace(gecici, hedef_csv)


def _dosya_indir(url: str, yol: str, http_get: Callable) -> None:
    gecici = yol + ".part"
    with http_get(url, stream=True, timeout=120, headers={"User-Agent": "SmartTransit/1.0"}) as y:
        y.raise_for_status()
        with open(gecici, "wb") as f:
            for blok in y.iter_content(chunk_size=1024 * 1024):
                if blok:
                    f.write(blok)
    os.replace(gecici, yol)


# ---------------------------------------------------------------- rapor
def rapor(session: Session, feed_id: str) -> dict:
    """Bir beslemenin sayım özeti ve olası sorun göstergeleri."""
    feed = session.get(GtfsFeed, feed_id)
    if feed is None:
        return {"feed_id": feed_id, "yuklu": False}
    sayi = lambda model: session.execute(
        select(func.count()).select_from(model).where(model.feed_id == feed_id)).scalar_one()
    hat_modlari = dict(session.execute(
        select(GtfsRoute.mode, func.count()).where(GtfsRoute.feed_id == feed_id).group_by(GtfsRoute.mode)).all())
    sefer_modlari = dict(session.execute(
        select(GtfsRoute.mode, func.count()).select_from(GtfsTrip).join(GtfsRoute, GtfsTrip.route_id == GtfsRoute.id)
        .where(GtfsTrip.feed_id == feed_id).group_by(GtfsRoute.mode)).all())
    trip_idleri = select(GtfsTrip.id).where(GtfsTrip.feed_id == feed_id)
    saatli_seferler = select(GtfsStopTime.trip_id).where(GtfsStopTime.trip_id.in_(trip_idleri)).distinct()
    gunsuz = session.execute(
        select(func.count()).select_from(GtfsCalendar).where(
            GtfsCalendar.feed_id == feed_id, ~GtfsCalendar.monday, ~GtfsCalendar.tuesday, ~GtfsCalendar.wednesday,
            ~GtfsCalendar.thursday, ~GtfsCalendar.friday, ~GtfsCalendar.saturday, ~GtfsCalendar.sunday)).scalar_one()
    durak_adlari = session.execute(select(GtfsStop.name).where(GtfsStop.feed_id == feed_id)).scalars().all()
    hat_adlari = session.execute(
        select(GtfsRoute.short_name, GtfsRoute.long_name).where(GtfsRoute.feed_id == feed_id)).all()
    supheli_durak = [n for n in durak_adlari if SUPHELI_KARAKTER.search(n or "")]
    supheli_hat = [f"{k or ''} {u or ''}".strip() for k, u in hat_adlari
                   if SUPHELI_KARAKTER.search(f"{k or ''} {u or ''}")]
    return {
        "feed_id": feed_id, "yuklu": True, "ad": feed.name, "veri_tarihi": feed.data_date,
        "yuklenme": feed.imported_at, "kaynak_notu": feed.source_note,
        "agency": sayi(GtfsAgency), "route": sayi(GtfsRoute), "trip": sayi(GtfsTrip),
        "stop": sayi(GtfsStop), "calendar": sayi(GtfsCalendar), "frequency": sayi(GtfsFrequency),
        "stop_time": session.execute(select(func.count()).select_from(GtfsStopTime)
                                     .where(GtfsStopTime.trip_id.in_(trip_idleri))).scalar_one(),
        "hat_modlari": hat_modlari, "sefer_modlari": sefer_modlari,
        "uyarilar": {
            "gunsuz_hizmet": gunsuz,
            "saatsiz_sefer": session.execute(
                select(func.count()).select_from(GtfsTrip).where(
                    GtfsTrip.feed_id == feed_id, GtfsTrip.id.not_in(saatli_seferler))).scalar_one(),
            "supheli_karakter_durak": len(supheli_durak),
            "supheli_karakter_hat": len(supheli_hat),
            "supheli_ornekler": (supheli_durak + supheli_hat)[:3],
            "adsiz_durak": sum(1 for n in durak_adlari if not n or n == "?"),
        },
    }


def rapor_metni(r: dict) -> str:
    if not r.get("yuklu"):
        return f"[{r['feed_id']}] yüklü değil"
    sat = [f"[{r['feed_id']}] {r['ad']}",
           f"  veri tarihi: {r['veri_tarihi'] or 'bilinmiyor'} | yüklenme: {r['yuklenme']}",
           f"  kurum {r['agency']}, hat {r['route']}, sefer {r['trip']}, durak {r['stop']}, "
           f"durak saati {r['stop_time']:,}, aralıklı tanım {r['frequency']}, hizmet {r['calendar']}",
           "  hat modları:   " + ", ".join(f"{m}={n}" for m, n in sorted(r["hat_modlari"].items())),
           "  sefer modları: " + ", ".join(f"{m}={n}" for m, n in sorted(r["sefer_modlari"].items()))]
    u = r["uyarilar"]
    if u["gunsuz_hizmet"]:
        sat.append(f"  ! {u['gunsuz_hizmet']} hizmetin hiçbir günü işaretli değil (planlamada çalışmaz)")
    if u["saatsiz_sefer"]:
        sat.append(f"  ! {u['saatsiz_sefer']} seferin durak saati yok (aralıklı şablon olabilir)")
    if u["supheli_karakter_durak"] or u["supheli_karakter_hat"]:
        sat.append(f"  ! bozuk karakter şüphesi: {u['supheli_karakter_durak']} durak, {u['supheli_karakter_hat']} hat adı "
                   f"(örnek: {u['supheli_ornekler']})")
    else:
        sat.append("  isim kontrolü: bozuk karakter şüphesi yok")
    if u["adsiz_durak"]:
        sat.append(f"  ! {u['adsiz_durak']} durağın adı boş")
    return "\n".join(sat)


def boyut_bilgisi(session: Session) -> Dict[str, int]:
    """gtfs_* tablolarının diskteki boyutu (bayt). PostgreSQL'de tablo bazında, SQLite'ta dosya boyutu."""
    motor = session.get_bind()
    if motor.dialect.name == "postgresql":
        satirlar = session.execute(text(
            "SELECT relname, pg_total_relation_size(c.oid) FROM pg_class c "
            "WHERE relkind = 'r' AND relname LIKE 'gtfs\\_%'")).all()
        return {ad: int(b) for ad, b in satirlar}
    if motor.dialect.name == "sqlite" and motor.url.database and os.path.exists(motor.url.database):
        return {"(sqlite dosyası)": os.path.getsize(motor.url.database)}
    return {}

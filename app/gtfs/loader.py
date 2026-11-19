"""GTFS besleme klasörünü veritabanındaki `gtfs_*` tablolarına yükler.

Kullanım:
    from app.gtfs.feeds import IBB_MULTIMODAL
    from app.gtfs.loader import load_feed
    ozet = load_feed(session, "gtfs_data/multimodal", IBB_MULTIMODAL)

Davranış:
  * Aynı besleme tekrar yüklenirse önce o beslemenin eski kayıtları silinir (idempotent).
  * Tüm kimliklere kaynak öneki eklenir ("ibb:123"); farklı beslemeler çakışmaz.
  * Hat modu `classify_mode` ile belirlenir; `exclude_modes` / `exclude_route` ile elenen
    hatların seferleri, durakları ve saatleri yüklenmez.
  * Yalnızca yüklenen seferlerin kullandığı duraklar (ve üst istasyonları) yüklenir.
  * Tüm işlem tek işlemde (transaction) yapılır; hata olursa hiçbir şey değişmez.
"""
import os
from typing import Callable, Dict, Iterable, List, Optional, Set

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.gtfs import reader
from app.gtfs.feeds import FeedConfig
from app.gtfs.models import (
    GtfsAgency, GtfsCalendar, GtfsCalendarDate, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop,
    GtfsStopTime, GtfsTransfer, GtfsTrip,
)
from app.gtfs.modes import classify_mode

BATCH = 5000
EXCEL_SATIR_SINIRI = 1_048_575   # Excel'in bir sayfaya sığdırdığı veri satırı sayısı (başlık hariç)


def _ekleme_ifadesi(session: Session, model, yoksay_cakisma: bool):
    """Gerekirse `ON CONFLICT DO NOTHING` ile (SQLite ve PostgreSQL) ekleme ifadesi döndürür."""
    if yoksay_cakisma:
        diyalekt = session.get_bind().dialect.name
        if diyalekt == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            return pg_insert(model).on_conflict_do_nothing()
        if diyalekt == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            return sqlite_insert(model).on_conflict_do_nothing()
    return insert(model)


def _toplu_ekle(session: Session, model, satirlar: Iterable[dict], batch: int = BATCH,
                yoksay_cakisma: bool = False) -> int:
    """Satırları `batch`'lik gruplar halinde ekler; DENENEN satır sayısını döndürür.
    `yoksay_cakisma=True` ise aynı anahtarlı tekrar satırlar sessizce atlanır."""
    ifade = _ekleme_ifadesi(session, model, yoksay_cakisma)
    toplam = 0
    grup: List[dict] = []
    for s in satirlar:
        grup.append(s)
        if len(grup) >= batch:
            session.execute(ifade, grup)
            toplam += len(grup)
            grup = []
    if grup:
        session.execute(ifade, grup)
        toplam += len(grup)
    return toplam


def _veri_satiri_say(yol: str) -> int:
    """Dosyadaki veri satırı sayısı (başlık hariç); büyük dosyalar için ikili okuma."""
    with open(yol, "rb") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _beslemeyi_sil(session: Session, feed_id: str) -> None:
    """Bir beslemenin tüm kayıtlarını bağımlılık sırasıyla siler."""
    trip_idler = select(GtfsTrip.id).where(GtfsTrip.feed_id == feed_id)
    session.execute(delete(GtfsStopTime).where(GtfsStopTime.trip_id.in_(trip_idler)))
    # Otomatik aktarma kenarları (#11) beslemeler arası olabilir (feed_id boş); bu beslemenin duraklarına
    # bağlı olanlar, duraklarla birlikte silinmeli (PostgreSQL yabancı anahtarı yoksa siler/hata verir).
    stop_idler = select(GtfsStop.id).where(GtfsStop.feed_id == feed_id)
    session.execute(delete(GtfsTransfer).where(GtfsTransfer.from_stop_id.in_(stop_idler)))
    session.execute(delete(GtfsTransfer).where(GtfsTransfer.to_stop_id.in_(stop_idler)))
    for model in (GtfsFrequency, GtfsTransfer, GtfsTrip, GtfsCalendarDate, GtfsCalendar,
                  GtfsRoute, GtfsStop, GtfsAgency):
        session.execute(delete(model).where(model.feed_id == feed_id))
    session.execute(delete(GtfsFeed).where(GtfsFeed.id == feed_id))


def load_feed(session: Session, feed_dir: str, config: FeedConfig, *,
              progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    """Beslemeyi yükler ve sayım özeti döndürür. Hata olursa geri alır ve hatayı yeniden fırlatır."""
    log = progress or (lambda _m: None)
    yol = lambda ad: os.path.join(feed_dir, f"{ad}.csv")
    if not os.path.isdir(feed_dir):
        raise FileNotFoundError(f"Besleme klasörü yok: {feed_dir}")
    for zorunlu in ("routes", "trips", "stops", "stop_times"):
        if not os.path.exists(yol(zorunlu)):
            raise FileNotFoundError(f"Zorunlu GTFS dosyası yok: {yol(zorunlu)}")
    if _veri_satiri_say(yol("stop_times")) == EXCEL_SATIR_SINIRI:
        raise ValueError(
            f"stop_times.csv tam olarak {EXCEL_SATIR_SINIRI} veri satırı: bu, dosyanın Excel'de "
            "açılıp kaydedilirken kırpıldığının işaretidir. Lütfen dosyayı orijinal haliyle indirin "
            "(İETT için portaldaki stop_times.ZIP sürümü eksiksizdir: `scripts/build_gtfs.py indir` onu kullanır).")

    P = config.prefixed
    metin = lambda v: reader.temizle_metin(v, fix_mojibake=config.fix_mojibake)
    ozet: Dict[str, int] = {}

    try:
        _beslemeyi_sil(session, config.feed_id)
        session.execute(insert(GtfsFeed), [{
            "id": config.feed_id, "name": config.name, "data_date": config.data_date,
            "source_note": config.source_note,
        }])

        # --- kurumlar ---
        kurumlar = [{
            "id": P(r["agency_id"] or "0"), "feed_id": config.feed_id,
            "name": metin(r.get("agency_name")) or "?", "url": r.get("agency_url") or None,
            "timezone": r.get("agency_timezone") or None,
        } for r in reader.iter_rows(yol("agency"))]
        ozet["agency"] = _toplu_ekle(session, GtfsAgency, kurumlar)
        kurum_idleri: Set[str] = {k["id"] for k in kurumlar}

        # --- takvim ---
        def gun(r, ad):
            return r.get(ad, "0") == "1"
        takvim = [{
            "service_id": P(r["service_id"]), "feed_id": config.feed_id,
            **{g: gun(r, g) for g in ("monday", "tuesday", "wednesday", "thursday", "friday",
                                      "saturday", "sunday")},
            "start_date": reader.parse_date(r.get("start_date")),
            "end_date": reader.parse_date(r.get("end_date")),
        } for r in reader.iter_rows(yol("calendar")) if r.get("service_id")]
        ozet["calendar"] = _toplu_ekle(session, GtfsCalendar, takvim)
        istisna = [{
            "service_id": P(r["service_id"]), "date": reader.parse_date(r.get("date")),
            "feed_id": config.feed_id, "exception_type": reader.parse_int(r.get("exception_type"), 1),
        } for r in reader.iter_rows(yol("calendar_dates"))
            if r.get("service_id") and reader.parse_date(r.get("date"))]
        ozet["calendar_date"] = _toplu_ekle(session, GtfsCalendarDate, istisna)

        # --- hatlar (mod belirle, ele) ---
        hatlar, tutulan_hat_idleri = [], set()
        elenen_hat = 0
        for r in reader.iter_rows(yol("routes")):
            if not r.get("route_id"):
                continue
            if (r.get("agency_id") or None) in config.exclude_agencies:
                elenen_hat += 1
                continue
            tip = reader.parse_int(r.get("route_type"))
            kisa = metin(r.get("route_short_name"))
            uzun = metin(r.get("route_long_name"))
            mod = classify_mode(tip, agency_id=r.get("agency_id") or None, short_name=kisa,
                                rules=config.mode_rules)
            hat = {"short_name": kisa, "long_name": uzun, "mode": mod}
            if mod in config.exclude_modes or (config.exclude_route and config.exclude_route(hat)):
                elenen_hat += 1
                continue
            ajans = P(r["agency_id"]) if r.get("agency_id") and P(r["agency_id"]) in kurum_idleri else None
            hatlar.append({
                "id": P(r["route_id"]), "feed_id": config.feed_id, "agency_id": ajans,
                "short_name": kisa or None, "long_name": uzun or None, "route_type": tip,
                "mode": mod, "color": r.get("route_color") or None,
            })
            tutulan_hat_idleri.add(r["route_id"])
        ozet["route"] = _toplu_ekle(session, GtfsRoute, hatlar)
        ozet["route_excluded"] = elenen_hat

        # --- seferler (yalnızca tutulan hatlar) ---
        seferler, tutulan_sefer_idleri = [], set()
        for r in reader.iter_rows(yol("trips")):
            if r.get("route_id") in tutulan_hat_idleri and r.get("trip_id") and r.get("service_id"):
                seferler.append({
                    "id": P(r["trip_id"]), "feed_id": config.feed_id, "route_id": P(r["route_id"]),
                    "service_id": P(r["service_id"]), "headsign": metin(r.get("trip_headsign")) or None,
                    "direction_id": reader.parse_int(r.get("direction_id")),
                    "shape_id": P(r["shape_id"]) if r.get("shape_id") else None,
                    "wheelchair_accessible": reader.parse_int(r.get("wheelchair_accessible")),
                })
                tutulan_sefer_idleri.add(r["trip_id"])
        ozet["trip"] = _toplu_ekle(session, GtfsTrip, seferler)

        # --- 1. geçiş: tutulan seferlerin kullandığı duraklar ---
        log("stop_times 1. geçiş (kullanılan duraklar)...")
        gerekli_duraklar: Set[str] = set()
        for r in reader.iter_rows(yol("stop_times")):
            if r.get("trip_id") in tutulan_sefer_idleri and r.get("stop_id"):
                gerekli_duraklar.add(r["stop_id"])

        # --- duraklar (geçerli koordinatlı olanlar + üst istasyonlar) ---
        tum_duraklar = {}
        gecersiz_koordinat = 0
        for r in reader.iter_rows(yol("stops")):
            sid = r.get("stop_id")
            if not sid:
                continue
            lat, lon = reader.parse_lat(r.get("stop_lat")), reader.parse_lon(r.get("stop_lon"))
            tum_duraklar[sid] = (r, lat, lon)
        secilen: Set[str] = set()
        bulunamayan = 0
        for sid in gerekli_duraklar:
            kayit = tum_duraklar.get(sid)
            if kayit is None:
                bulunamayan += 1
                continue
            if kayit[1] is None or kayit[2] is None:
                gecersiz_koordinat += 1
                continue
            secilen.add(sid)
            ust = kayit[0].get("parent_station")
            while ust and ust in tum_duraklar and ust not in secilen:
                if tum_duraklar[ust][1] is None or tum_duraklar[ust][2] is None:
                    break
                secilen.add(ust)
                ust = tum_duraklar[ust][0].get("parent_station")
        durak_satirlari = []
        for sid in secilen:
            r, lat, lon = tum_duraklar[sid]
            ust = r.get("parent_station")
            durak_satirlari.append({
                "id": P(sid), "feed_id": config.feed_id, "code": r.get("stop_code") or None,
                "name": metin(r.get("stop_name")) or "?", "lat": lat, "lon": lon,
                "location_type": reader.parse_int(r.get("location_type"), 0) or 0,
                "parent_station": P(ust) if ust and ust in secilen else None,
                "wheelchair_boarding": reader.parse_int(r.get("wheelchair_boarding")),
            })
        ozet["stop"] = _toplu_ekle(session, GtfsStop, durak_satirlari)
        ozet["stop_invalid_coordinates"] = gecersiz_koordinat
        ozet["stop_not_found"] = bulunamayan

        # --- 2. geçiş: durak saatleri ---
        log("stop_times 2. geçiş (ekleniyor)...")
        bilinmeyen = 0

        def saat_satirlari():
            nonlocal bilinmeyen
            for r in reader.iter_rows(yol("stop_times")):
                if r.get("trip_id") not in tutulan_sefer_idleri:
                    continue
                if r.get("stop_id") not in secilen:
                    bilinmeyen += 1
                    continue
                varis = reader.parse_time(r.get("arrival_time"))
                kalkis = reader.parse_time(r.get("departure_time"))
                yield {
                    "trip_id": P(r["trip_id"]), "stop_sequence": reader.parse_int(r.get("stop_sequence"), 0),
                    "stop_id": P(r["stop_id"]),
                    "arrival_secs": varis if varis is not None else kalkis,
                    "departure_secs": kalkis if kalkis is not None else varis,
                    "pickup_type": reader.parse_int(r.get("pickup_type"), 0) or 0,
                    "drop_off_type": reader.parse_int(r.get("drop_off_type"), 0) or 0,
                }
        denenen = _toplu_ekle(session, GtfsStopTime, saat_satirlari(), yoksay_cakisma=True)
        ozet["stop_time"] = session.execute(
            select(func.count()).select_from(GtfsStopTime)
            .where(GtfsStopTime.trip_id.in_(select(GtfsTrip.id).where(GtfsTrip.feed_id == config.feed_id)))
        ).scalar_one()
        ozet["stop_time_duplicate"] = denenen - ozet["stop_time"]       # aynı (sefer, sıra) tekrarları
        ozet["stop_time_unknown_stop"] = bilinmeyen

        # --- aralıklı seferler ---
        frekanslar = []
        for r in reader.iter_rows(yol("frequencies")):
            b, e = reader.parse_time(r.get("start_time")), reader.parse_time(r.get("end_time"))
            h = reader.parse_int(r.get("headway_secs"))
            if r.get("trip_id") in tutulan_sefer_idleri and b is not None and e is not None and h and h > 0:
                frekanslar.append({
                    "feed_id": config.feed_id, "trip_id": P(r["trip_id"]), "start_secs": b,
                    "end_secs": e, "headway_secs": h,
                    "exact_times": reader.parse_int(r.get("exact_times"), 0) or 0,
                })
        ozet["frequency"] = _toplu_ekle(session, GtfsFrequency, frekanslar)

        # --- aktarmalar (varsa) ---
        yuklu_durak = {P(s) for s in secilen}
        aktarmalar = [{
            "feed_id": config.feed_id, "from_stop_id": P(r["from_stop_id"]), "to_stop_id": P(r["to_stop_id"]),
            "transfer_type": reader.parse_int(r.get("transfer_type"), 0) or 0,
            "min_transfer_secs": reader.parse_int(r.get("min_transfer_time")), "source": "feed",
        } for r in reader.iter_rows(yol("transfers"))
            if r.get("from_stop_id") and r.get("to_stop_id")
            and P(r["from_stop_id"]) in yuklu_durak and P(r["to_stop_id"]) in yuklu_durak]
        ozet["transfer"] = _toplu_ekle(session, GtfsTransfer, aktarmalar)

        session.commit()
    except Exception:
        session.rollback()
        raise
    log(f"Yüklendi: {ozet}")
    return ozet

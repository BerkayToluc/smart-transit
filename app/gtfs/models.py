"""Çok modlu toplu taşıma (GTFS benzeri) veritabanı şeması.

Mevcut canlı takip tabloları (`hatlar`, `duraklar`, `otobusler`, `guzergah_noktalari`) AYNEN
kalır; bu modüldeki tablolar yanlarına eklenir ve `gtfs_` önekini taşır.

Tasarım kararları (ayrıntı: docs/schema.md):
  * Her kayıt bir besleme (`feed_id`) ve **kaynak önekli kimlik** taşır: "iett:292235",
    "ibb:292235". Farklı kurumların beslemelerinde aynı kimlik çakışabildiği için.
  * Saatler **gece yarısından geçen saniye** olarak tutulur (25:20 = 91200); 24 saati aşabilir.
  * `gtfs_frequency` ham haliyle saklanır; gerçek seferlere açma planlama aşamasında
    (app/gtfs/rules.py).
  * `mode`: kaynaktaki `route_type` güvenilir olmadığı için hesaplanan, normalleştirilmiş mod.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)

from app.db import Base

ID_UZUNLUK = 96   # "kaynak:kimlik" için yeterli (en uzun gözlenen kimlik ~ 20 karakter)


class GtfsFeed(Base):
    """Bir veri kaynağı (besleme): nereden geldi, verinin tarihi ne, ne zaman yüklendi."""
    __tablename__ = "gtfs_feed"
    id = Column(String(32), primary_key=True)             # "iett", "ibb", "marmaray"
    name = Column(String(200), nullable=False)
    data_date = Column(Date, nullable=True)                # verinin KENDİ tarihi (kayıt tarihi değil)
    source_note = Column(Text, nullable=True)
    imported_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class GtfsAgency(Base):
    __tablename__ = "gtfs_agency"
    id = Column(String(ID_UZUNLUK), primary_key=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    url = Column(String(300), nullable=True)
    timezone = Column(String(64), nullable=True)


class GtfsStop(Base):
    __tablename__ = "gtfs_stop"
    id = Column(String(ID_UZUNLUK), primary_key=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    code = Column(String(64), nullable=True)
    name = Column(String(300), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    location_type = Column(Integer, nullable=False, default=0)    # 0 durak, 1 istasyon (üst), ...
    parent_station = Column(String(ID_UZUNLUK), nullable=True, index=True)
    wheelchair_boarding = Column(Integer, nullable=True)           # 0 bilinmiyor, 1 var, 2 yok

    __table_args__ = (Index("ix_gtfs_stop_lat_lon", "lat", "lon"),)


class GtfsRoute(Base):
    __tablename__ = "gtfs_route"
    id = Column(String(ID_UZUNLUK), primary_key=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    agency_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_agency.id"), nullable=True, index=True)
    short_name = Column(String(100), nullable=True)
    long_name = Column(String(300), nullable=True)
    route_type = Column(Integer, nullable=True)       # kaynaktaki HAM değer (güvenilmez)
    mode = Column(String(20), nullable=False, index=True)   # bus, metro, tram, ferry, ... (modes.py)
    color = Column(String(8), nullable=True)


class GtfsCalendar(Base):
    """Hizmet günleri. Tarih aralıkları (start/end) çoğu beslemede süresi dolmuş olduğundan
    planlama yalnızca haftanın günlerine bakar (bkz. rules.service_runs_on_weekday)."""
    __tablename__ = "gtfs_calendar"
    service_id = Column(String(ID_UZUNLUK), primary_key=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    monday = Column(Boolean, nullable=False, default=False)
    tuesday = Column(Boolean, nullable=False, default=False)
    wednesday = Column(Boolean, nullable=False, default=False)
    thursday = Column(Boolean, nullable=False, default=False)
    friday = Column(Boolean, nullable=False, default=False)
    saturday = Column(Boolean, nullable=False, default=False)
    sunday = Column(Boolean, nullable=False, default=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)


class GtfsCalendarDate(Base):
    """İstisna günler (bayram vb.). Mevcut beslemelerde yok; şema ileride için hazır."""
    __tablename__ = "gtfs_calendar_date"
    service_id = Column(String(ID_UZUNLUK), primary_key=True)
    date = Column(Date, primary_key=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    exception_type = Column(Integer, nullable=False)    # 1 eklendi, 2 kaldırıldı


class GtfsTrip(Base):
    __tablename__ = "gtfs_trip"
    id = Column(String(ID_UZUNLUK), primary_key=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    route_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_route.id"), nullable=False, index=True)
    service_id = Column(String(ID_UZUNLUK), nullable=False, index=True)
    headsign = Column(String(300), nullable=True)
    direction_id = Column(Integer, nullable=True)
    shape_id = Column(String(ID_UZUNLUK), nullable=True)
    wheelchair_accessible = Column(Integer, nullable=True)


class GtfsStopTime(Base):
    __tablename__ = "gtfs_stop_time"
    trip_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_trip.id"), primary_key=True)
    stop_sequence = Column(Integer, primary_key=True)
    stop_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_stop.id"), nullable=False, index=True)
    arrival_secs = Column(Integer, nullable=True)       # gece yarısından beri saniye (24 saati aşabilir)
    departure_secs = Column(Integer, nullable=True)
    pickup_type = Column(Integer, nullable=False, default=0)
    drop_off_type = Column(Integer, nullable=False, default=0)


class GtfsFrequency(Base):
    """Aralıklı sefer tanımı: [start, end) penceresinde `headway_secs` aralıkla.
    Ham saklanır; gerçek seferlere açma planlama aşamasında yapılır."""
    __tablename__ = "gtfs_frequency"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=False, index=True)
    trip_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_trip.id"), nullable=False, index=True)
    start_secs = Column(Integer, nullable=False)
    end_secs = Column(Integer, nullable=False)
    headway_secs = Column(Integer, nullable=False)
    exact_times = Column(Integer, nullable=False, default=0)


class GtfsTransfer(Base):
    """İki durak arasındaki aktarma (yürüme). `source`: feed | manual | auto (#11)."""
    __tablename__ = "gtfs_transfer"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    feed_id = Column(String(32), ForeignKey("gtfs_feed.id"), nullable=True, index=True)
    from_stop_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_stop.id"), nullable=False, index=True)
    to_stop_id = Column(String(ID_UZUNLUK), ForeignKey("gtfs_stop.id"), nullable=False, index=True)
    transfer_type = Column(Integer, nullable=False, default=0)   # 0 önerilen, 2 en az süre gerekir, 3 yasak
    min_transfer_secs = Column(Integer, nullable=True)
    source = Column(String(16), nullable=False, default="feed")

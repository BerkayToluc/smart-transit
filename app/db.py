"""Veritabanı bağlantısı, modeller ve oturum bağımlılığı."""
import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

# 🔐 VERİTABANI (Neon.tech) — bağlantı bilgisi koda yazılmaz, ortamdan okunur.
# Yerelde proje kökündeki .env dosyasından (bkz. .env.example), sunucuda ortam
# değişkeninden gelir.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv kurulu değilse yalnızca gerçek ortam değişkenleri kullanılır
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL ortam değişkeni tanımlı değil. .env.example dosyasını .env olarak "
        "kopyalayıp doldurun."
    )

# Neon boşta kalan bağlantıları ve (ücretsiz planda) veritabanını uyutuyor; havuzdaki
# bağlantı kapanmışsa "SSL connection has been closed unexpectedly" hatası alınıyordu.
# pool_pre_ping: bağlantı her kullanımdan önce yoklanır, ölüyse yenisi açılır.
# pool_recycle: 5 dakikadan eski bağlantılar baştan açılır.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# =====================================================================
# 📦 VERİTABANI MODELLERİ
# =====================================================================
class Hat(Base):
    __tablename__ = "hatlar"
    id = Column(Integer, primary_key=True, index=True)
    hat_kodu = Column(String(20), unique=True, nullable=False)
    hat_adi = Column(String(100), nullable=False)


class Durak(Base):
    __tablename__ = "duraklar"
    id = Column(Integer, primary_key=True, index=True)
    hat_id = Column(Integer, ForeignKey("hatlar.id"), nullable=False)
    durak_adi = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    sira_no = Column(Integer, nullable=False)
    yon = Column(String)


class OtobusLive(Base):
    __tablename__ = "otobusler"
    id = Column(Integer, primary_key=True, index=True)
    plaka = Column(String(20), unique=True, nullable=False)
    hat_id = Column(Integer, ForeignKey("hatlar.id"), nullable=False)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)
    son_guncelleme = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Guzergah(Base):
    __tablename__ = "guzergah_noktalari"
    id = Column(Integer, primary_key=True, index=True)
    hat_id = Column(Integer, ForeignKey("hatlar.id"), nullable=False)
    yon = Column(String, nullable=False)
    sira_no = Column(Integer, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

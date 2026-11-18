"""Hat / durak / güzergah katalog uç noktaları (salt okunur, veritabanından)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import Durak, Guzergah, Hat, get_db

router = APIRouter()


@router.get("/")
def ana_sayfa():
    return {"mesaj": "SmartTransit API Tıkır Tıkır Çalışıyor"}


@router.get("/api/hatlar")
def api_hatlari_getir(db: Session = Depends(get_db)):
    hatlar = db.query(Hat).all()
    return [{"id": h.id, "hat_kodu": h.hat_kodu, "hat_adi": h.hat_adi} for h in hatlar]


@router.get("/api/duraklar/{hat_id}")
def api_duraklari_getir(hat_id: int, db: Session = Depends(get_db)):
    duraklar = db.query(Durak).filter(Durak.hat_id == hat_id).order_by(Durak.sira_no).all()
    return [{
        "id": d.id,
        "durak_adi": d.durak_adi,
        "latitude": float(d.latitude),
        "longitude": float(d.longitude),
        "sira_no": d.sira_no,
        "yon": d.yon
    } for d in duraklar]


@router.get("/api/guzergah/{hat_id}/{yon}")
def guzergah_getir(hat_id: int, yon: str, db: Session = Depends(get_db)):
    noktalar = (
        db.query(Guzergah)
        .filter(Guzergah.hat_id == hat_id, Guzergah.yon == yon)
        .order_by(Guzergah.sira_no)
        .all()
    )
    return [{"lat": float(n.latitude), "lng": float(n.longitude)} for n in noktalar]

"""Seçilen hat üzerinde başlangıç noktasına en yakın durak ve yön."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import Durak, Hat, get_db
from app.utils import mesafe_hesapla_km

from app.guvenlik import hiz_siniri  # noqa: E402

router = APIRouter()


class EvrenselRotaIstegi(BaseModel):
    hat_kodu: str = Field(..., min_length=1, max_length=20)
    baslangic_lat: float = Field(..., ge=-90, le=90)
    baslangic_lng: float = Field(..., ge=-180, le=180)
    hedef_lat: float = Field(..., ge=-90, le=90)
    hedef_lng: float = Field(..., ge=-180, le=180)


@router.post("/api/en-yakin-durak", dependencies=[Depends(hiz_siniri("en_yakin", 60))])
def en_yakin_durak_bul(istek: EvrenselRotaIstegi, db: Session = Depends(get_db)):
    hat = db.query(Hat).filter(Hat.hat_kodu == istek.hat_kodu.upper()).first()
    if not hat:
        return {"hata": f"{istek.hat_kodu} hattı veritabanında bulunamadı."}

    tum_duraklar = db.query(Durak).filter(
        Durak.hat_id == hat.id,
        Durak.yon != None,
        Durak.sira_no != None
    ).all()

    if not tum_duraklar:
        return {"hata": "Bu hatta ait kayıtlı geçerli durak bulunamadı."}

    yonler = set([d.yon for d in tum_duraklar])
    dogru_yon = None
    en_yakin_baslangic = None
    en_kisa_yurume = float('inf')

    try:
        for y in yonler:
            duraklar_y = [d for d in tum_duraklar if d.yon == y]
            if not duraklar_y:
                continue
            baslangic_d = min(duraklar_y, key=lambda d: mesafe_hesapla_km(istek.baslangic_lat, istek.baslangic_lng,
                                                                          float(d.latitude), float(d.longitude)))
            hedef_d = min(duraklar_y,
                          key=lambda d: mesafe_hesapla_km(istek.hedef_lat, istek.hedef_lng, float(d.latitude),
                                                          float(d.longitude)))
            baslangic_sira = int(baslangic_d.sira_no)
            hedef_sira = int(hedef_d.sira_no)
            if baslangic_sira <= hedef_sira:
                dogru_yon = y
                en_yakin_baslangic = baslangic_d
                en_kisa_yurume = mesafe_hesapla_km(istek.baslangic_lat, istek.baslangic_lng,
                                                   float(baslangic_d.latitude), float(baslangic_d.longitude))
                break
    except Exception:
        pass

    if not dogru_yon or not en_yakin_baslangic:
        return {"hata": "Seçtiğiniz rotaya uygun bu hatta bir güzergah bulunamadı."}

    return {
        "mesaj": "Evrensel durak ve yön başarıyla hesaplandı!",
        "durak_id": en_yakin_baslangic.id,
        "durak_adi": en_yakin_baslangic.durak_adi,
        "durak_lat": float(en_yakin_baslangic.latitude),
        "durak_lon": float(en_yakin_baslangic.longitude),
        "hesaplanan_yon": dogru_yon,
        "yurume_mesafesi_km": round(en_kisa_yurume, 2)
    }

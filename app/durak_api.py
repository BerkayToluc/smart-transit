"""Durak sayfası (#23): `GET /api/stops/{stop_id}/departures`: bir duraktan (ve aynı istasyonun diğer duraklarından) geçen hatlar,
sıradaki planlı kalkışlar ve otobüslerde canlı kalan dakika.

Canlı veri: İETT SOAP hat başına bir çağrıdır (15 sn önbellekli, #30); kalabalık duraklarda çağrı sayısı sınırlıdır
(`CANLI_HAT_SAYISI`): kalkışı en yakın ilk hatlar için canlı aranır, diğerleri yalnızca planlıdır.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.gtfs.textfix import ascii_katla
from app.guvenlik import hiz_siniri
from app.routing import servis
from app.routing.graph import Graf
from app.routing.raptor import _sonraki
from app.yaklasan import CANLI_MODLAR, _indeks, hat_araclari

router = APIRouter()
TR = timezone(timedelta(hours=3))
GRUP_YARICAP_M = 400.0            # aynı ad + bu mesafe içindeki duraklar tek istasyon sayılır (stops_api ile aynı)
PLANLI_ADET = 4
CANLI_HAT_SAYISI = 6
EN_COK_CANLI_ARAC = 3


def _simdi() -> datetime:
    return datetime.now(TR)


def _istasyon_uyeleri(g: Graf, i: int) -> List[int]:
    """Durağın aynı fiziksel istasyondaki kardeşleri (aynı katlanmış ad, ≤400 m), kendisi ilk sırada."""
    ad = ascii_katla(g.durak_ad[i])
    uyeler = [i]
    for j, _ in g.yakin_duraklar(g.durak_lat[i], g.durak_lon[i], GRUP_YARICAP_M):
        if j != i and ascii_katla(g.durak_ad[j]) == ad:
            uyeler.append(j)
    return uyeler


def _kalkislar(p, sira: int, gun: int, simdi_sn: int) -> List[int]:
    """Bu durakta şimdiden sonraki en çok PLANLI_ADET planlı kalkış (saniye; gün aşan seferler için 86400'ü geçebilir)."""
    cikti, t = [], simdi_sn
    for _ in range(PLANLI_ADET):
        s = _sonraki(p, sira, t, gun)
        if s is None:
            break
        cikti.append(s[0])
        t = s[0] + 60
    return cikti


def _saat(sn: int) -> str:
    return f"{(sn // 3600) % 24:02d}:{sn % 3600 // 60:02d}"


@router.get("/api/stops/{stop_id}/departures", dependencies=[Depends(hiz_siniri("durak", 30))])
def durak_kalkislari(stop_id: str = Path(..., min_length=3, max_length=60), limit: int = Query(12, ge=1, le=30)):
    g = servis.graf_al()
    if g is None or g.durak_sayisi == 0:
        raise HTTPException(status_code=503, detail="Rota verisi hazır değil.")
    idx = _indeks(g)
    if stop_id not in idx:
        raise HTTPException(status_code=404, detail="Durak bulunamadı.")
    i0 = idx[stop_id]
    simdi = _simdi()
    gun, simdi_sn = simdi.weekday(), simdi.hour * 3600 + simdi.minute * 60 + simdi.second
    uyeler = _istasyon_uyeleri(g, i0)

    # (hat, mod, yön) başına en çok seferli örüntü; son durağı olan ya da binilemeyen örüntüler dışarıda
    secilen: Dict[Tuple[str, str, str], Tuple[int, int]] = {}
    modlar = set()
    for m in uyeler:
        for pi, sira in g.durak_paternleri[m]:
            p = g.paternler[pi]
            modlar.add(p.mod)
            if not p.biner[sira] or sira == len(p.duraklar) - 1:
                continue
            anahtar = (g.hat_kisa[p.hat], p.mod, g.durak_ad[p.duraklar[-1]])
            if anahtar not in secilen or p.sefer_sayisi > g.paternler[secilen[anahtar][0]].sefer_sayisi:
                secilen[anahtar] = (pi, sira)

    satirlar = []
    for (hat, mod, yon), (pi, sira) in secilen.items():
        p = g.paternler[pi]
        kalkis = _kalkislar(p, sira, gun, simdi_sn)
        satirlar.append({"hat": hat, "mod": mod, "yon": yon, "pi": pi, "sira": sira, "kalkis": kalkis})
    # planlı kalkışı olmayan (bugün seferi bitmiş) hatlar listelenmez; en yakın kalkışa göre sırala
    satirlar = [s for s in satirlar if s["kalkis"]]
    satirlar.sort(key=lambda s: (s["kalkis"][0], s["hat"]))

    canli_hata = False
    sonuc = []
    canli_sayisi = 0
    for s in satirlar:
        p = g.paternler[s["pi"]]
        canli, canli_denendi, erisilemiyor = [], False, False
        if p.mod in CANLI_MODLAR and canli_sayisi < CANLI_HAT_SAYISI:
            canli_sayisi += 1
            canli_denendi = True
            r = hat_araclari(g, s["hat"], {"pi": s["pi"], "a": s["sira"], "b": len(p.duraklar) - 1}, simdi)
            erisilemiyor = bool(r.get("canli_erisilemiyor"))
            canli = [{"dakika": a["dakika"], "kapi_no": a["kapi_no"], "mesafe_km": a["mesafe_km"]} for a in r["araclar"][:EN_COK_CANLI_ARAC]]
        canli_hata = canli_hata or erisilemiyor
        sonuc.append({
            "hat": s["hat"], "mod": s["mod"], "yon": s["yon"],
            "planli": [{"saat": _saat(t), "dk": max(0, (t - simdi_sn) // 60)} for t in s["kalkis"]],
            "canli": canli, "canli_denendi": canli_denendi, "canli_erisilemiyor": erisilemiyor,
        })
    # canlı aracı olanlar, canlı dakikaya göre önde; sonra planlı kalkışa göre (zaten sıralı)
    sonuc.sort(key=lambda r: (r["canli"][0]["dakika"] if r["canli"] else r["planli"][0]["dk"], r["hat"]))
    return {
        "stop": {"stop_id": stop_id, "name": g.durak_ad[i0], "lat": g.durak_lat[i0], "lng": g.durak_lon[i0],
                 "stop_ids": [g.durak_id[m] for m in uyeler], "modes": sorted(modlar)},
        "departures": sonuc[:limit],
        "toplam_hat": len(sonuc),
        "canli_erisilemiyor": canli_hata,
    }

"""Yaklaşan otobüsler: bir biniş durağından bir iniş durağına giden hatlar ve canlı araçların biniş durağına varış tahmini.

Rota planlayıcıdaki her otobüs bacağı için kullanılır (biniş durağı → iniş durağı). Eski `/api/moovit` mantığı
(İETT canlı konum + rotaya izdüşüm + gerçek zamanlı hız) yeni GTFS grafı üzerine taşındı: hat güzergâhı, veritabanındaki
eski hat/durak tabloları yerine rota grafındaki örüntüdür (app/routing/).
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.live import (
    ETKIN_HIZ_MAX_KMH, ETKIN_HIZ_MIN_KMH, GECTI_TOLERANS_KM, MAKS_MAKUL_HIZ_KMH, ROTADAN_MAKS_SAPMA_KM,
    VARSAYILAN_HIZ_KMH, _gecmis_al, _gecmis_yaz, _otobus_rota_konumu, _rota_kumulatif_mesafe, iett_verisi_cek,
)
from app.routing import servis
from app.routing.graph import Graf
from app.routing.raptor import _sonraki
from app.utils import mesafe_hesapla_km

from app.guvenlik import hiz_siniri  # noqa: E402

router = APIRouter()
TR = timezone(timedelta(hours=3))
CANLI_MODLAR = ("bus",)      # yalnız İETT otobüsleri (metrobüs canlı listesine alınmaz)
EN_COK_HAT = 12


def _indeks(g: Graf) -> Dict[str, int]:
    """durak kimliği -> indeks (grafta ilk kullanımda bir kez kurulur)."""
    idx = g.__dict__.get("_durak_idx")
    if idx is None:
        idx = {d: i for i, d in enumerate(g.durak_id)}
        g.__dict__["_durak_idx"] = idx
    return idx


def hatlari_bul(g: Graf, bas: int, bit: int) -> Dict[str, dict]:
    """bas'tan bit'e (aynı örüntüde, bas önce) giden otobüs/metrobüs hatları: kısa ad -> en çok seferli örüntü."""
    bulunan: Dict[str, dict] = {}
    for pi, sira_a in g.durak_paternleri[bas]:
        p = g.paternler[pi]
        if p.mod not in CANLI_MODLAR or not p.biner[sira_a]:
            continue
        sira_b = next((k for k in range(sira_a + 1, len(p.duraklar)) if p.duraklar[k] == bit and p.iner[k]), None)
        if sira_b is None:
            continue
        ad = g.hat_kisa[p.hat]
        if ad and (ad not in bulunan or p.sefer_sayisi > g.paternler[bulunan[ad]["pi"]].sefer_sayisi):
            bulunan[ad] = {"pi": pi, "a": sira_a, "b": sira_b}
    return bulunan


def _planli(g: Graf, p, sira: int, gun: int, simdi_sn: int, adet: int = 3) -> List[str]:
    """Biniş durağından sıradaki planlı kalkışlar ("14:20")."""
    cikti, t = [], simdi_sn
    for _ in range(adet):
        s = _sonraki(p, sira, t, gun)
        if s is None:
            break
        cikti.append(f"{(s[0] // 3600) % 24:02d}:{s[0] % 3600 // 60:02d}")
        t = s[0] + 60
    return cikti


def _sure_dk(p, a: int, b: int) -> Optional[int]:
    """Biniş-iniş arası tarifedeki yolculuk süresi (medyan, dk)."""
    n = p.sefer_sayisi
    if not n:
        return None
    fark = sorted(p.varis[b][i] - p.kalkis[a][i] for i in range(n))
    return max(1, round(fark[n // 2] / 60))


def _yon_kumeleri(g: Graf, p):
    """Hat yönünü canlı araçların `yon` metninden ayırmak için: hedef yönün son durakları / ters yönün son durakları (≈ ilk duraklar)."""
    adlar = [g.durak_ad[d].upper() for d in p.duraklar]
    return " ".join(adlar[-15:]), " ".join(adlar[:15])


def hat_araclari(g: Graf, hat: str, bilgi: dict, simdi: datetime) -> dict:
    p = g.paternler[bilgi["pi"]]
    sira_a = bilgi["a"]
    noktalar = [SimpleNamespace(latitude=g.durak_lat[d], longitude=g.durak_lon[d]) for d in p.duraklar]
    kum = _rota_kumulatif_mesafe(noktalar)
    yolcu_s = kum[sira_a]
    hedef_metin, ters_metin = _yon_kumeleri(g, p)

    araclar = iett_verisi_cek(hat) or []
    kesin_hedef, kesin_ters = set(), set()
    for a in araclar:
        yon = str(a.get("yon", "")).upper()
        kelimeler = [k for k in yon.replace("-", " ").split() if len(k) > 2]
        h = any(k in hedef_metin for k in kelimeler)
        t = any(k in ters_metin for k in kelimeler)
        if t and not h:
            kesin_ters.add(yon)
        elif h and not t:
            kesin_hedef.add(yon)

    yaklasan, tum = [], []
    for a in araclar:
        try:
            lat = float(str(a["enlem"]).replace(",", "."))
            lon = float(str(a["boylam"]).replace(",", "."))
        except (KeyError, ValueError):
            continue
        yon = str(a.get("yon", "")).upper()
        kapi = a.get("kapino", "")
        tum.append({"kapi_no": kapi, "enlem": lat, "boylam": lon, "yon": a.get("yon", "")})
        if yon in kesin_ters:
            continue
        if not kesin_ters and kesin_hedef and yon not in kesin_hedef:
            continue
        anahtar = f"{hat}:{bilgi['pi']}:{kapi}"
        onceki = _gecmis_al(anahtar)
        gecen = (simdi - onceki["zaman"]).total_seconds() if onceki else 0
        konum = _otobus_rota_konumu(lat, lon, noktalar, kum, onceki, gecen)
        if konum is None or konum[0] > ROTADAN_MAKS_SAPMA_KM:
            continue
        s_bus = konum[1]
        ema = onceki.get("hiz_ema") if onceki else None
        kayit = {"lat": lat, "lon": lon, "zaman": simdi, "s": s_bus, "hiz_ema": ema}
        if onceki:
            km = mesafe_hesapla_km(onceki["lat"], onceki["lon"], lat, lon)
            if km < 0.005:
                kayit = onceki
            elif gecen > 2:
                anlik = min(max(km / (gecen / 3600), 1.0), MAKS_MAKUL_HIZ_KMH)
                ema = anlik if ema is None else 0.5 * ema + 0.5 * anlik
                kayit["hiz_ema"] = ema
        _gecmis_yaz(anahtar, kayit)
        hiz = VARSAYILAN_HIZ_KMH if ema is None else 0.5 * ema + 0.5 * VARSAYILAN_HIZ_KMH
        hiz = min(max(hiz, ETKIN_HIZ_MIN_KMH), ETKIN_HIZ_MAX_KMH)
        kalan = yolcu_s - s_bus
        if kalan < -GECTI_TOLERANS_KM:
            continue                      # biniş durağını geçti
        kalan = max(kalan, 0.0)
        dakika = max(1, int(round(kalan / hiz * 60)))
        if dakika < 120:
            yaklasan.append({"kapi_no": kapi, "dakika": dakika, "mesafe_km": round(kalan, 2), "hiz_kmh": round(hiz, 1),
                             "yon": a.get("yon", ""), "enlem": lat, "boylam": lon})
    yaklasan.sort(key=lambda x: x["dakika"])
    gun = simdi.weekday()
    simdi_sn = simdi.hour * 3600 + simdi.minute * 60 + simdi.second
    return {
        "hat": hat, "mod": p.mod, "yon": g.durak_ad[p.duraklar[-1]], "sure_dk": _sure_dk(p, sira_a, bilgi["b"]),
        "araclar": yaklasan, "tum_araclar": tum, "planli": _planli(g, p, sira_a, gun, simdi_sn),
    }


@router.get("/api/yaklasan", dependencies=[Depends(hiz_siniri("yaklasan", 30))])
def yaklasan_otobusler(
    bas: str = Query(..., description="biniş durağı kimliği (örn. iett:123)"),
    bit: str = Query(..., description="iniş durağı kimliği"),
    hatlar: Optional[str] = Query(None, max_length=200, description="virgülle ayrılmış hat kısa adları; boşsa bu iki durak arasındaki tüm hatlar"),
    oncelik: Optional[str] = Query(None, description="listede başa alınacak hat (rotadaki hat)"),
):
    g = servis.graf_al()
    if g is None or g.durak_sayisi == 0:
        raise HTTPException(status_code=503, detail="Rota verisi hazır değil.")
    idx = _indeks(g)
    if bas not in idx or bit not in idx:
        raise HTTPException(status_code=404, detail="Durak bulunamadı.")
    tum_hatlar = hatlari_bul(g, idx[bas], idx[bit])
    secilen = [h.strip() for h in hatlar.split(",")] if hatlar else None
    adlar = sorted(tum_hatlar, key=lambda h: (h != oncelik, -g.paternler[tum_hatlar[h]["pi"]].sefer_sayisi, h))
    uygun = adlar[:EN_COK_HAT]
    if oncelik and oncelik in tum_hatlar and oncelik not in uygun:
        uygun = [oncelik] + uygun[:-1]
    simdi = datetime.now(TR)
    sonuc = [hat_araclari(g, h, tum_hatlar[h], simdi) for h in uygun if secilen is None or h in secilen]
    sonuc.sort(key=lambda r: (r["araclar"][0]["dakika"] if r["araclar"] else 10 ** 6, r["hat"]))
    return {
        "binis": {"stop_id": bas, "name": g.durak_ad[idx[bas]], "lat": g.durak_lat[idx[bas]], "lng": g.durak_lon[idx[bas]]},
        "inis": {"stop_id": bit, "name": g.durak_ad[idx[bit]], "lat": g.durak_lat[idx[bit]], "lng": g.durak_lon[idx[bit]]},
        "hat_adlari": adlar,
        "hatlar": sonuc,
    }

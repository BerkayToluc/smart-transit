"""Rota planına canlı otobüs bilgisi (#22): ilk otobüs bacağı için "bu otobüs durağa kaç dk sonra gelir", tarifeden sapma ve güncel varış.

Yalnızca "şimdi" sorgularında ve ilk otobüs bacağında çalışır (sonraki bacaklarda belirsizlik büyür; metro/vapur için canlı kaynak yok).
Mevcut `/api/yaklasan` mantığı (İETT konumu + rotaya izdüşüm + gerçek zamanlı hız) yeniden kullanılır; ek İETT çağrısı hat başına 15 sn
önbelleklidir. Servis yavaş ya da erişilemezse plan beklemez: `source: "tarife"` ve `service_down` ile planlı tarifeye dönülür.
Sıralama DEĞİŞMEZ (sonucun "zıplamasını" önlemek için); yalnızca etiket, güncel varış ve "daha iyi alternatif" uyarısı eklenir.
"""
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app import live
from app.routing.graph import Graf
from app.yaklasan import _indeks, hat_araclari, hatlari_bul

BUTCE_SN = 4.0                 # tüm canlı aramalar için toplam süre sınırı
EN_COK_PARALEL = 4
ALTERNATIF_KAZANC_DK = 5       # "daha iyi alternatif": canlı gecikmeye rağmen bu kadar dk erken varan başka seçenek
UYARI_GECIKME_DK = 5           # ... ve (gecikme ≥ 5 dk ya da bekleme ≥ 10 dk)
UYARI_BEKLEME_DK = 10
EN_FAZLA_ILERI_DK = 90         # durağa 90 dk'dan geç varılacaksa canlı araç anlamsız


def _dk(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp() / 60


def ilk_otobus_bacagi(yolculuk: dict) -> Optional[Tuple[int, dict]]:
    """(indeks, bacak): ilk otobüs bacağı (durak kimlikleri ve hat adı olan)."""
    for i, e in enumerate(yolculuk["legs"]):
        if e["type"] == "transit":
            if e["mode"] == "bus" and e.get("route_short_name") and e["from"].get("stop_id") and e["to"].get("stop_id"):
                return i, e
            return None            # ilk binilen araç otobüs değil (metro/vapur...): canlı bilgi yok
    return None


def hesapla(g: Graf, yolculuk: dict, araclar_dk: List[Tuple[float, str]], simdi_dk: float, hizmet_yok: bool) -> dict:
    """Tek yolculuk için canlı bilgi. `araclar_dk`: durağa yaklaşan araçlar [(dakika, kapı no)]."""
    i, e = ilk_otobus_bacagi(yolculuk)
    planli_binis = _dk(e["from"]["time"])
    durağa_varis = _dk(yolculuk["legs"][i - 1]["to"]["time"]) if i > 0 else _dk(yolculuk["departure_time"])
    durağa_dk = durağa_varis - simdi_dk                      # kullanıcı durağa şimdiden kaç dk sonra varır
    bilgi = {"source": "tarife", "route": e["route_short_name"], "stop": e["from"]["name"], "stop_id": e["from"]["stop_id"],
             "planned_departure": e["from"]["time"], "service_down": hizmet_yok, "reach_min": max(0, round(durağa_dk))}
    if hizmet_yok or durağa_dk > EN_FAZLA_ILERI_DK:
        return bilgi
    # Yetişilebilecek ilk araç: durağa kullanıcıdan (yaklaşık) önce ya da onunla birlikte varmayan
    uygun = [(d, k) for d, k in sorted(araclar_dk) if d >= durağa_dk - 0.5]
    bilgi["vehicles"] = [{"minutes": d, "gate": k} for d, k in sorted(araclar_dk)[:3]]
    if not uygun:
        if araclar_dk:
            bilgi["missed"] = True                           # araçlar var ama siz durağa varmadan geçecek: sonraki sefer tarifeye göre
            bilgi["nearest_min"] = round(min(d for d, _ in araclar_dk))
        else:
            bilgi["no_vehicle"] = True                       # yaklaşan canlı araç görünmüyor: tarifeye göre
        return bilgi
    d, k = uygun[0]
    gercek_binis = simdi_dk + d
    bilgi.update({
        "source": "canli", "gate": k, "arrives_in_min": round(d),
        "wait_min": max(0, round(d - durağa_dk)),
        "delay_min": round(gercek_binis - planli_binis),     # tarifeye göre sapma (+: geç)
    })
    return bilgi


def uygula(g: Graf, sonuc: dict, simdi: datetime) -> dict:
    """`/api/plan` sonucuna (itineraries listesi) her yolculuk için `live` alanı ekler. Hata verirse sonuca dokunmaz."""
    yolculuklar = sonuc.get("itineraries") or []
    isler: Dict[Tuple[str, str, str], dict] = {}
    idx = _indeks(g)
    for y in yolculuklar:
        b = ilk_otobus_bacagi(y)
        if not b:
            continue
        e = b[1]
        a, z = e["from"]["stop_id"], e["to"]["stop_id"]
        if a in idx and z in idx:
            isler.setdefault((e["route_short_name"], a, z), {})
    if not isler:
        return sonuc
    simdi_dk = simdi.timestamp() / 60

    def calis(anahtar):
        hat, a, z = anahtar
        durum = live.iett_durum(hat, hizli=True)                 # önbelleği ısıt (tek deneme, kısa zaman aşımı)
        if durum["erisilemiyor"]:
            return anahtar, ([], True)
        bilgi = hatlari_bul(g, idx[a], idx[z]).get(hat)
        if bilgi is None:
            return anahtar, ([], False)
        r = hat_araclari(g, hat, bilgi, simdi)
        return anahtar, ([(x["dakika"], x["kapi_no"]) for x in r["araclar"]], False)

    havuz = ThreadPoolExecutor(max_workers=EN_COK_PARALEL)
    try:
        bekleyen = {havuz.submit(calis, k): k for k in isler}
        bitti, _ = wait(bekleyen, timeout=BUTCE_SN)
        for f in bitti:
            try:
                k, v = f.result()
                isler[k] = {"araclar": v[0], "hizmet_yok": v[1]}
            except Exception:  # noqa: BLE001 - canlı bilgi isteğe bağlıdır; plan bozulmasın
                live.logger.exception("canlı plan bilgisi hesaplanamadı")
    finally:
        havuz.shutdown(wait=False, cancel_futures=True)

    for y in yolculuklar:
        b = ilk_otobus_bacagi(y)
        if not b:
            continue
        e = b[1]
        k = (e["route_short_name"], e["from"]["stop_id"], e["to"]["stop_id"])
        veri = isler.get(k)
        if not veri or "araclar" not in veri:                    # bütçe aşıldı ya da hat bulunamadı: tarife
            y["live"] = {"source": "tarife", "route": k[0], "stop": e["from"]["name"], "stop_id": k[1],
                         "planned_departure": e["from"]["time"], "service_down": veri is None}
            continue
        y["live"] = hesapla(g, y, veri["araclar"], simdi_dk, veri["hizmet_yok"])
        gecikme = y["live"].get("delay_min") or 0
        if gecikme > 0:
            y["adjusted_arrival_time"] = (datetime.fromisoformat(y["arrival_time"]) + timedelta(minutes=gecikme)).isoformat()

    # "Daha iyi alternatif": canlı gecikme/bekleme yüzünden bu seçenek belirgin kötüleştiyse ve başka seçenek ≥5 dk erken varıyorsa
    guncel = [_dk(y.get("adjusted_arrival_time") or y["arrival_time"]) for y in yolculuklar]
    for i, y in enumerate(yolculuklar):
        l = y.get("live")
        if not l or l.get("source") != "canli":
            continue
        if (l.get("delay_min") or 0) >= UYARI_GECIKME_DK or (l.get("wait_min") or 0) >= UYARI_BEKLEME_DK:
            en_iyi = min((j for j in range(len(yolculuklar)) if j != i), key=lambda j: guncel[j], default=None)
            if en_iyi is not None and guncel[i] - guncel[en_iyi] >= ALTERNATIF_KAZANC_DK:
                l["better_option"] = en_iyi
                l["better_gain_min"] = round(guncel[i] - guncel[en_iyi])
    return sonuc

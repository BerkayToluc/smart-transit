"""Besleme indirme ve raporlama (scripts/build_gtfs.py bunu kullanır).

İndirme, İBB Açık Veri Portalı'nın CKAN API'sini (`package_show`) kullanır; dosya adresleri
koda sabit yazılmaz, böylece portaldaki kaynak kimlikleri değişse de çalışır.

NOT: Portal bulut sunucularından açılmıyor; bu işlemler yerel makinede çalıştırılmalıdır.
"""
import os
import re
import shutil
import time
import statistics
import zipfile
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import requests
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.gtfs import manual, vapur
from app.gtfs.feeds import IBB_MULTIMODAL, IETT, MARMARAY, VAPUR, FeedConfig
from app.gtfs.loader import EXCEL_SATIR_SINIRI, _veri_satiri_say
from app.gtfs.rules import expand_frequency_starts
from app.gtfs.textfix import ascii_katla
from app.gtfs.models import (
    GtfsAgency, GtfsCalendar, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTrip,
)

PORTAL = "https://data.ibb.gov.tr"
# Düzeltilmemiş bozuk kodlamanın izleri: Å/Ã/Ä/Â (UTF-8'in yanlış okunması), C1 kontrol karakterleri,
# U+FFFD (çözülemeyen bayt). Gerçek Türkçe metinde bunlar neredeyse hiç görülmez.
SUPHELI_KARAKTER = re.compile("[ÅÃÄÂ\x80-\x9f\ufffd]")
GTFS_DOSYALARI = ("agency", "calendar", "calendar_dates", "routes", "stops", "stop_times", "trips",
                  "frequencies", "shapes", "transfers")


KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass(frozen=True)
class BeslemeKaynagi:
    config: FeedConfig
    paket: str                      # portaldaki veri seti adı (CKAN "name"); elle tanımlı beslemede boş
    klasor: str                     # varsayılan yerel klasör
    manuel: Optional[str] = None    # elle tanımlı besleme: tanım dosyası (indirme yok, dosyalar üretilir)
    bicim: str = "kural"            # "kural": manual.py (frekans kuralları); "sefer": vapur.py (saat saat)


BESLEMELER: Dict[str, BeslemeKaynagi] = {
    "iett": BeslemeKaynagi(IETT, "iett-gtfs-verisi", os.path.join("gtfs_data", "iett")),
    "ibb": BeslemeKaynagi(IBB_MULTIMODAL, "public-transport-gtfs-data", os.path.join("gtfs_data", "multimodal")),
    "marmaray": BeslemeKaynagi(MARMARAY, "", os.path.join("gtfs_data", "marmaray"),
                               manuel=os.path.join(KOK, "data", "marmaray.json")),
    "vapur": BeslemeKaynagi(VAPUR, "", os.path.join("gtfs_data", "vapur"),
                            manuel=os.path.join(KOK, "data", "vapur.json"), bicim="sefer"),
}


# ---------------------------------------------------------------- elle tanımlı beslemeler
def manuel_uret(besleme: str, klasor: Optional[str] = None, *, log: Callable[[str], None] = print) -> Dict[str, int]:
    """Elle tanımlı beslemenin (ör. Marmaray) GTFS dosyalarını kural dosyasından üretir. Ağ gerekmez."""
    kaynak = BESLEMELER[besleme]
    if not kaynak.manuel:
        raise ValueError(f"'{besleme}' elle tanımlı bir besleme değil")
    hedef = klasor or kaynak.klasor
    modul = vapur if kaynak.bicim == "sefer" else manual
    sayim = modul.gtfs_uret(modul.tanim_oku(kaynak.manuel), hedef)
    log(f"  {kaynak.manuel} -> {hedef}: " + ", ".join(f"{a}={n}" for a, n in sayim.items()))
    return sayim


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
    if kaynak.manuel:
        manuel_uret(besleme, klasor, log=log)       # elle tanımlı: indirme yok, dosyalar üretilir
        return []
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
            "saatsiz_sefer_hatlari": sorted({f"{k or '?'} ({u or '?'})" for k, u in session.execute(
                select(GtfsRoute.short_name, GtfsRoute.long_name).join(GtfsTrip, GtfsTrip.route_id == GtfsRoute.id)
                .where(GtfsTrip.feed_id == feed_id, GtfsTrip.id.not_in(saatli_seferler)).distinct().limit(5))}),
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
        sat.append(f"  ! {u['saatsiz_sefer']} seferin durak saati yok (aralıklı şablon olabilir); hatlar: "
                   f"{', '.join(u['saatsiz_sefer_hatlari'])}")
    if u["supheli_karakter_durak"] or u["supheli_karakter_hat"]:
        sat.append(f"  ! bozuk karakter şüphesi: {u['supheli_karakter_durak']} durak, {u['supheli_karakter_hat']} hat adı "
                   f"(örnek: {u['supheli_ornekler']})")
    else:
        sat.append("  isim kontrolü: bozuk karakter şüphesi yok")
    if u["adsiz_durak"]:
        sat.append(f"  ! {u['adsiz_durak']} durağın adı boş")
    return "\n".join(sat)


def hat_ozeti(session: Session, feed_id: str, modlar: Optional[List[str]] = None) -> List[dict]:
    """Seçilen modlardaki her hat için temsilci bir seferin özeti: ilk durak -> son durak, durak sayısı
    ve yolculuk süresi (dk). Veriyi gerçek hayatla kıyaslamak (durak sırası, süre) için kullanılır.

    Temsilci sefer: hattın en çok durağı olan seferi (eşitlikte gidiş yönü, direction_id=0). `sefer` hattın yüklenen sefer sayısı, `aralikli`
    ise bunlardan kaçının `frequencies` ile tekrarlandığıdır."""
    sorgu = select(GtfsRoute).where(GtfsRoute.feed_id == feed_id)
    if modlar:
        sorgu = sorgu.where(GtfsRoute.mode.in_(modlar))
    sonuc = []
    for hat in session.scalars(sorgu.order_by(GtfsRoute.mode, GtfsRoute.short_name, GtfsRoute.id)):
        temsilci = session.execute(
            select(GtfsStopTime.trip_id, func.count().label("n")).join(GtfsTrip, GtfsTrip.id == GtfsStopTime.trip_id)
            .where(GtfsTrip.route_id == hat.id).group_by(GtfsStopTime.trip_id)
            .order_by(func.count().desc(), func.coalesce(GtfsTrip.direction_id, 0), GtfsStopTime.trip_id).limit(1)).first()
        sefer_sayisi = session.execute(select(func.count()).select_from(GtfsTrip).where(GtfsTrip.route_id == hat.id)).scalar_one()
        aralikli = session.execute(
            select(func.count(func.distinct(GtfsFrequency.trip_id))).join(GtfsTrip, GtfsTrip.id == GtfsFrequency.trip_id)
            .where(GtfsTrip.route_id == hat.id)).scalar_one()
        kayit = {"mod": hat.mode, "kisa_ad": hat.short_name, "uzun_ad": hat.long_name, "sefer": sefer_sayisi,
                 "aralikli": aralikli, "ilk_durak": None, "son_durak": None, "durak_sayisi": 0, "sure_dk": None}
        if temsilci:
            satirlar = session.execute(
                select(GtfsStopTime.stop_sequence, GtfsStopTime.arrival_secs, GtfsStopTime.departure_secs, GtfsStop.name)
                .join(GtfsStop, GtfsStop.id == GtfsStopTime.stop_id).where(GtfsStopTime.trip_id == temsilci[0])
                .order_by(GtfsStopTime.stop_sequence)).all()
            ilk, son = satirlar[0], satirlar[-1]
            kayit.update(ilk_durak=ilk[3], son_durak=son[3], durak_sayisi=len(satirlar))
            if ilk[2] is not None and son[1] is not None:
                kayit["sure_dk"] = round((son[1] - ilk[2]) / 60, 1)
        sonuc.append(kayit)
    return sonuc


def hat_ozeti_metni(kayitlar: List[dict]) -> str:
    if not kayitlar:
        return "  (seçilen modlarda hat yok)"
    sat = []
    for k in kayitlar:
        guzergah = f"{k['ilk_durak']} -> {k['son_durak']}" if k["ilk_durak"] else "(durak saati yok)"
        sure = f"{k['sure_dk']:g} dk" if k["sure_dk"] is not None else "?"
        sat.append(f"  {k['mod']:<9} {k['kisa_ad'] or '-':<8} {guzergah} | {k['durak_sayisi']} durak | {sure} | "
                   f"{k['sefer']} sefer" + (f" ({k['aralikli']} aralıklı)" if k["aralikli"] else ""))
    return "\n".join(sat)


# ---------------------------------------------------------------- sefer saatleri analizi
GUN_KISALTMA = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cts", "Paz")


def gun_etiketi(gunler) -> str:
    """Pazartesi..Pazar bayraklarından okunaklı etiket: "Pzt-Cum", "Cts", "Cts,Paz", "Her gün"."""
    g = [bool(x) for x in gunler]
    if all(g):
        return "Her gün"
    if not any(g):
        return "(günsüz)"
    parcalar, i = [], 0
    while i < 7:
        if g[i]:
            j = i
            while j + 1 < 7 and g[j + 1]:
                j += 1
            parcalar.append(GUN_KISALTMA[i] if i == j else f"{GUN_KISALTMA[i]}-{GUN_KISALTMA[j]}")
            i = j + 1
        else:
            i += 1
    return ",".join(parcalar)


def _saat(sn: int) -> str:
    return f"{sn // 3600:02d}:{sn % 3600 // 60:02d}"


def sefer_saatleri(session: Session, feed_id: str, *, hatlar: Optional[List[str]] = None,
                   modlar: Optional[List[str]] = None, en_az_sefer: int = 0) -> List[dict]:
    """Hatların gerçek sefer saatlerini (aralıklı tanımlar seferlere açılarak) yön ve gün tipine göre özetler.

    Her grup: (hat, yön, ilk durak -> son durak, gün etiketi). Grup başına sefer sayısı, ilk/son kalkış,
    en sık aralık (dk) ve payı, yolculuk süresi (ortanca ve en az/çok). Elle tanım yazmadan önce mevcut
    tarifeyi görmek ve şüpheli süreleri bulmak için kullanılır.
    """
    sorgu = select(GtfsRoute).where(GtfsRoute.feed_id == feed_id)
    if modlar:
        sorgu = sorgu.where(GtfsRoute.mode.in_(modlar))
    rotalar = list(session.scalars(sorgu.order_by(GtfsRoute.short_name, GtfsRoute.id)))
    if hatlar:
        istenen = {ascii_katla(h) for h in hatlar}
        rotalar = [r for r in rotalar if ascii_katla(r.short_name or "") in istenen]

    sonuc = []
    for hat in rotalar:
        seferler = session.execute(select(GtfsTrip.id, GtfsTrip.service_id, GtfsTrip.direction_id)
                                   .where(GtfsTrip.route_id == hat.id)).all()
        if len(seferler) < en_az_sefer or not seferler:
            continue
        takvim = {c.service_id: c for c in session.scalars(
            select(GtfsCalendar).where(GtfsCalendar.service_id.in_({sf[1] for sf in seferler})))}
        frekans: Dict[str, list] = {}
        for tid, b, e, h in session.execute(
                select(GtfsFrequency.trip_id, GtfsFrequency.start_secs, GtfsFrequency.end_secs, GtfsFrequency.headway_secs)
                .join(GtfsTrip, GtfsTrip.id == GtfsFrequency.trip_id).where(GtfsTrip.route_id == hat.id)):
            frekans.setdefault(tid, []).append((b, e, h))
        duraklar: Dict[str, list] = {}
        for tid, arr, dep, ad in session.execute(
                select(GtfsStopTime.trip_id, GtfsStopTime.arrival_secs, GtfsStopTime.departure_secs, GtfsStop.name)
                .join(GtfsTrip, GtfsTrip.id == GtfsStopTime.trip_id).join(GtfsStop, GtfsStop.id == GtfsStopTime.stop_id)
                .where(GtfsTrip.route_id == hat.id).order_by(GtfsStopTime.trip_id, GtfsStopTime.stop_sequence)):
            duraklar.setdefault(tid, []).append((arr, dep, ad))

        gruplar: Dict[tuple, dict] = {}
        for tid, servis, yon in seferler:
            st = duraklar.get(tid)
            if not st:
                continue
            ilk_kalkis = st[0][1] if st[0][1] is not None else st[0][0]
            son_varis = st[-1][0] if st[-1][0] is not None else st[-1][1]
            if ilk_kalkis is None or son_varis is None:
                continue
            sure = son_varis - ilk_kalkis
            cal = takvim.get(servis)
            etiket = gun_etiketi([getattr(cal, g) for g in ("monday", "tuesday", "wednesday", "thursday", "friday",
                                                           "saturday", "sunday")]) if cal else "(takvim yok)"
            baslangiclar = ([ilk_kalkis] if tid not in frekans else
                            sorted({x for (b, e, h) in frekans[tid] for x in expand_frequency_starts(b, e, h)}))
            g = gruplar.setdefault((yon if yon is not None else 0, st[0][2], st[-1][2], etiket),
                                   {"baslangic": [], "sureler": []})
            g["baslangic"].extend(baslangiclar)
            g["sureler"].extend([sure] * len(baslangiclar))

        for (yon, ilk_ad, son_ad, etiket), g in sorted(gruplar.items(), key=lambda kv: (kv[0][3], kv[0][0], kv[0][1])):
            b = sorted(g["baslangic"])
            farklar = Counter(round((y - x) / 60) for x, y in zip(b, b[1:]) if y > x)
            aralik, pay = (None, None)
            if farklar:
                aralik, adet = farklar.most_common(1)[0]
                pay = adet / sum(farklar.values())
            sureler = sorted(g["sureler"])
            sonuc.append({
                "hat": hat.short_name, "uzun_ad": hat.long_name, "mod": hat.mode, "yon": yon, "ilk_durak": ilk_ad,
                "son_durak": son_ad, "gun": etiket, "sefer": len(b), "ilk": b[0], "son": b[-1], "aralik_dk": aralik,
                "aralik_payi": pay, "sure_dk": round(statistics.median(sureler) / 60, 1),
                "sure_en_az": round(sureler[0] / 60, 1), "sure_en_cok": round(sureler[-1] / 60, 1),
            })
    return sonuc


def sefer_saatleri_metni(kayitlar: List[dict]) -> str:
    if not kayitlar:
        return "  (eşleşen hat/sefer yok)"
    sat, onceki = [], None
    for k in kayitlar:
        if k["hat"] != onceki:
            sat.append(f"{k['hat']}  [{k['mod']}]  {k['uzun_ad'] or ''}".rstrip())
            onceki = k["hat"]
        aralik = f"en sık aralık {k['aralik_dk']} dk (%{round(k['aralik_payi'] * 100)})" if k["aralik_dk"] is not None else "tek sefer"
        sure = f"{k['sure_dk']:g} dk" + (f" ({k['sure_en_az']:g}-{k['sure_en_cok']:g})" if k["sure_en_az"] != k["sure_en_cok"] else "")
        sat.append(f"   {k['gun']:<9} {k['ilk_durak']} -> {k['son_durak']} | {k['sefer']} sefer | "
                   f"{_saat(k['ilk'])} - {_saat(k['son'])} | {aralik} | süre {sure}")
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

"""Aktarma noktaları (#11): yakın duraklar arası yürüme kenarları ve istasyon kümeleri.

Aktarmalı rota motoru (RAPTOR) farklı hatların/modların duraklarının aynı yerde olup olmadığını
bilmek zorundadır. Bu modül, yüklenmiş tüm beslemelerin duraklarına bakıp iki şey üretir:

1. **Yürüme kenarları** (`gtfs_transfer`, `source="auto"`): birbirine `yaricap` metreden (varsayılan 150)
   yakın her durak çifti için iki yönlü kenar; ayrıca istasyon türü duraklar
   (metro, Marmaray, vapur iskelesi ...) için `istasyon_yaricap` (varsayılan 600 m; farklı beslemelerde her zaman,
   aynı beslemede yalnız ortak hat yoksa). Süre = mesafe × 1.3
   (kuş uçuşu düzeltmesi) / 4.8 km/s.
2. **İstasyon kümeleri**: metro, tramvay, füniküler, teleferik, raylı, metrobüs ve vapur durakları
   birbirine yakınsa tek bir üst istasyon (`location_type=1`, besleme `kume`, kimlik `kume:...`) altında
   toplanır; üyelerin `parent_station` alanı doldurulur. Otobüs durakları kümelenmez (yalnız kenar alır).

Önemli kurallar:
  * Birleştirme **yalnızca mesafeye** göre yapılır; **aynı isim hiçbir zaman birleştirme nedeni değildir**
    (farklı semtlerdeki aynı adlı duraklar karışmaz). İsim yalnız küme adını seçmekte kullanılır.
  * Kümelerin boyutu sınırlıdır (`kume_tavan`): zincirleme birleşmeyle koca bir mahalle tek istasyon olmaz.
  * Küme içi aktarma süresi `max(yürüme, kume_ici_en_az)`; bilinen büyük aktarma noktaları için elle
    tanımlı süreler `data/aktarma.json` dosyasından gelir (varsayım olarak işaretli).
  * Üretim **idempotenttir**: her çalışmada önceki `auto` kenarlar, kümeler ve `parent_station`
    atamaları silinip yeniden hesaplanır. Bir besleme yeniden yüklenirse `aktarma` komutu yeniden çalıştırılmalıdır.
"""
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.gtfs.models import GtfsFeed, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTransfer, GtfsTrip
from app.gtfs.textfix import ascii_katla

KUME_BESLEME = "kume"
YURUME_KATSAYISI = 1.3            # kuş uçuşu mesafeyi gerçek yürüme yoluna çevirir
YURUME_HIZI_MS = 4.8 / 3.6        # 4.8 km/s
VARSAYILAN_YARICAP_M = 150.0
# Farklı beslemelerin istasyon türü durakları (ör. Marmaray ↔ vapur iskelesi) gerçekte 150 m'den uzaktır:
# Üsküdar 236 m, Bostancı 262 m, Sirkeci-Eminönü 542 m (gerçek veri ölçümü). Bu çiftler için daha geniş yarıçap.
VARSAYILAN_ISTASYON_YARICAP_M = 600.0
VARSAYILAN_KUME_BAGLANTI_M = 120.0   # kümeye katılmak için komşu durağa en fazla bu kadar uzaklık
VARSAYILAN_KUME_TAVAN_M = 300.0      # bir kümenin en uzak iki üyesi arası
KUME_ICI_EN_AZ_SN = 120              # istasyon içi aktarmada en kısa süre
ISTASYON_MODLARI = frozenset({"metro", "tram", "funicular", "cable_car", "rail", "metrobus", "ferry"})
_MOD_ONCELIGI = ("rail", "metro", "metrobus", "tram", "funicular", "cable_car", "ferry")
KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VARSAYILAN_TANIM = os.path.join(KOK, "data", "aktarma.json")


# ---------------------------------------------------------------- geometri
def mesafe_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def yurume_suresi_sn(mesafe: float) -> int:
    """Mesafe (m) -> yürüme süresi (sn): mesafe × 1.3 / (4.8 km/s), yukarı yuvarlanır."""
    return math.ceil(mesafe * YURUME_KATSAYISI / YURUME_HIZI_MS)


class _Izgara:
    """Durakları ~yaricap boyutlu hücrelere böler; komşu sorgusu yalnızca 3×3 hücreye bakar."""

    def __init__(self, duraklar: List[dict], yaricap_m: float):
        self.d_lat = yaricap_m / 111_000.0
        ort = sum(d["lat"] for d in duraklar) / len(duraklar) if duraklar else 41.0
        self.d_lon = yaricap_m / (111_000.0 * math.cos(math.radians(ort)))
        self.hucre: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        self.duraklar = duraklar
        for i, d in enumerate(duraklar):
            self.hucre[self._anahtar(d["lat"], d["lon"])].append(i)

    def _anahtar(self, lat, lon):
        return (math.floor(lat / self.d_lat), math.floor(lon / self.d_lon))

    def komsular(self, i: int, yaricap_m: float) -> Iterable[Tuple[int, float]]:
        d = self.duraklar[i]
        ky, kx = self._anahtar(d["lat"], d["lon"])
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for j in self.hucre.get((ky + dy, kx + dx), ()):
                    if j == i:
                        continue
                    m = mesafe_m(d["lat"], d["lon"], self.duraklar[j]["lat"], self.duraklar[j]["lon"])
                    if m <= yaricap_m:
                        yield j, m


# ---------------------------------------------------------------- kümeleme
def kumeleri_bul(istasyonlar: List[dict], baglanti_m: float, tavan_m: float) -> List[List[int]]:
    """İstasyon türü duraklardan küme indeks listeleri üretir (yalnızca ≥2 üyeli kümeler).

    Önce `baglanti_m` içindeki komşular birleştirilir (union-find). Bileşenin en uzak iki üyesi
    `tavan_m`'i aşarsa bileşen açgözlü olarak bölünür: en çok farklı moda sahip durak tohum olur ve
    `tavan_m / 2` yarıçapındaki henüz atanmamış duraklar o kümeye girer. Sonuç belirlidir (sıra: kimlik)."""
    n = len(istasyonlar)
    if n == 0:
        return []
    ust = list(range(n))

    def bul(x):
        while ust[x] != x:
            ust[x] = ust[ust[x]]
            x = ust[x]
        return x

    izgara = _Izgara(istasyonlar, baglanti_m)
    for i in range(n):
        for j, _ in izgara.komsular(i, baglanti_m):
            a, b = bul(i), bul(j)
            if a != b:
                ust[max(a, b)] = min(a, b)
    bilesenler: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        bilesenler[bul(i)].append(i)

    sonuc: List[List[int]] = []
    for uyeler in bilesenler.values():
        if len(uyeler) < 2:
            continue
        if _cap(istasyonlar, uyeler) <= tavan_m:
            sonuc.append(sorted(uyeler))
            continue
        kalan = set(uyeler)
        while kalan:
            tohum = min(sorted(kalan), key=lambda i: (-len(istasyonlar[i]["modlar"]), i))
            grup = sorted(j for j in kalan if mesafe_m(istasyonlar[tohum]["lat"], istasyonlar[tohum]["lon"],
                                                        istasyonlar[j]["lat"], istasyonlar[j]["lon"]) <= tavan_m / 2)
            kalan -= set(grup)
            if len(grup) >= 2:
                sonuc.append(grup)
    return sorted(sonuc, key=lambda g: istasyonlar[g[0]]["id"])


def _cap(duraklar: List[dict], uyeler: List[int]) -> float:
    return max((mesafe_m(duraklar[a]["lat"], duraklar[a]["lon"], duraklar[b]["lat"], duraklar[b]["lon"])
                for k, a in enumerate(uyeler) for b in uyeler[k + 1:]), default=0.0)


def _kume_adi(uyeler: List[dict]) -> str:
    """En önemli moda ait duraklar arasında en sık geçen (eşitlikte en kısa) isim; isim yalnız etikettir."""
    for mod in _MOD_ONCELIGI:
        adaylar = [u["name"] for u in uyeler if mod in u["modlar"]]
        if adaylar:
            sayim = Counter(adaylar)
            return sorted(sayim, key=lambda ad: (-sayim[ad], len(ad), ad))[0]
    return uyeler[0]["name"]


def _kume_kimligi(ad: str, uye_idleri: List[str]) -> str:
    ozet = hashlib.sha1("|".join(sorted(uye_idleri)).encode("utf-8")).hexdigest()[:6]
    govde = "".join(c if c.isalnum() else "_" for c in ascii_katla(ad).lower()).strip("_")[:40] or "istasyon"
    return f"kume:{govde}-{ozet}"


# ---------------------------------------------------------------- tanım dosyası
def tanim_oku(yol: str = VARSAYILAN_TANIM) -> dict:
    with open(yol, encoding="utf-8") as f:
        t = json.load(f)
    h: List[str] = []
    for i, s in enumerate(t.get("sureler", [])):
        n = f"sureler[{i}] ({s.get('ad')})"
        for alan in ("enlem", "boylam", "yaricap_m", "sure_dk"):
            if not isinstance(s.get(alan), (int, float)) or s[alan] <= 0:
                h.append(f"{n}: {alan} pozitif sayı olmalı: {s.get(alan)!r}")
        if not (40.0 <= (s.get("enlem") or 0) <= 42.0 and 27.5 <= (s.get("boylam") or 0) <= 31.0):
            h.append(f"{n}: konum İstanbul bölgesinde değil")
    for i, b in enumerate(t.get("bilinen_noktalar", [])):
        n = f"bilinen_noktalar[{i}] ({b.get('ad')})"
        for alan in ("enlem", "boylam", "yaricap_m"):
            if not isinstance(b.get(alan), (int, float)):
                h.append(f"{n}: {alan} sayı olmalı")
    if h:
        raise ValueError("Aktarma tanımı geçersiz: " + "; ".join(h))
    return t


def _elle_sure(kume_lat: float, kume_lon: float, sureler: List[dict]) -> Optional[Tuple[int, str]]:
    """Küme merkezi tanımlı bir aktarma noktasının içindeyse (süre_sn, ad) döndürür (en yakın nokta kazanır)."""
    en_iyi = None
    for s in sureler:
        m = mesafe_m(kume_lat, kume_lon, s["enlem"], s["boylam"])
        if m <= s["yaricap_m"] and (en_iyi is None or m < en_iyi[0]):
            en_iyi = (m, int(round(s["sure_dk"] * 60)), s["ad"])
    return (en_iyi[1], en_iyi[2]) if en_iyi else None


# ---------------------------------------------------------------- üretim
def _toplu_ekle(session: Session, model, satirlar: List[dict], batch: int = 5000) -> int:
    for i in range(0, len(satirlar), batch):
        session.execute(insert(model), satirlar[i:i + batch])
    return len(satirlar)


def temizle(session: Session) -> None:
    """Önceki `auto` kenarları, kümeleri ve `parent_station` atamalarını siler."""
    session.execute(delete(GtfsTransfer).where(GtfsTransfer.source == "auto"))
    session.execute(update(GtfsStop).where(GtfsStop.parent_station.like(f"{KUME_BESLEME}:%"))
                    .values(parent_station=None))
    session.execute(delete(GtfsStop).where(GtfsStop.feed_id == KUME_BESLEME))
    session.execute(delete(GtfsFeed).where(GtfsFeed.id == KUME_BESLEME))


def durak_mod_ve_hatlari(session: Session) -> Tuple[Dict[str, set], Dict[str, set]]:
    """Durak -> uğrayan istasyon türü modlar ve hat kimlikleri. Yalnız otobüs dışı seferler taranır (hızlı)."""
    modlar: Dict[str, set] = defaultdict(set)
    hatlar: Dict[str, set] = defaultdict(set)
    q = (select(GtfsStopTime.stop_id, GtfsRoute.mode, GtfsRoute.id)
         .join(GtfsTrip, GtfsStopTime.trip_id == GtfsTrip.id)
         .join(GtfsRoute, GtfsTrip.route_id == GtfsRoute.id)
         .where(GtfsRoute.mode.in_(sorted(ISTASYON_MODLARI))).distinct())
    for stop_id, mod, rid in session.execute(q):
        modlar[stop_id].add(mod)
        hatlar[stop_id].add(rid)
    return modlar, hatlar


def durak_modlari(session: Session) -> Dict[str, set]:
    return durak_mod_ve_hatlari(session)[0]


def uret(session: Session, *, yaricap_m: float = VARSAYILAN_YARICAP_M,
         istasyon_yaricap_m: float = VARSAYILAN_ISTASYON_YARICAP_M,
         kume_baglanti_m: float = VARSAYILAN_KUME_BAGLANTI_M, kume_tavan_m: float = VARSAYILAN_KUME_TAVAN_M,
         tanim: Optional[dict] = None, log=lambda m: None) -> dict:
    """Yürüme kenarlarını ve istasyon kümelerini yeniden üretir. Özet sözlüğü döndürür."""
    tanim = tanim if tanim is not None else tanim_oku()
    temizle(session)
    session.flush()
    modlar, hatlar = durak_mod_ve_hatlari(session)
    satirlar = session.execute(
        select(GtfsStop.id, GtfsStop.feed_id, GtfsStop.name, GtfsStop.lat, GtfsStop.lon)
        .where(GtfsStop.location_type == 0).order_by(GtfsStop.id)).all()
    duraklar = [{"id": s.id, "feed": s.feed_id, "name": s.name, "lat": s.lat, "lon": s.lon,
                 "modlar": modlar.get(s.id, set()), "hatlar": hatlar.get(s.id, set())} for s in satirlar]
    log(f"{len(duraklar)} durak okundu")

    # 1) istasyon kümeleri
    ist_idx = [i for i, d in enumerate(duraklar) if d["modlar"]]
    ist = [duraklar[i] for i in ist_idx]
    kume_listesi = kumeleri_bul(ist, kume_baglanti_m, kume_tavan_m)
    kume_of: Dict[str, str] = {}
    kume_bilgi: Dict[str, dict] = {}
    ust_satirlar, atamalar = [], []
    for grup in kume_listesi:
        uyeler = [ist[i] for i in grup]
        ad = _kume_adi(uyeler)
        kid = _kume_kimligi(ad, [u["id"] for u in uyeler])
        lat = sum(u["lat"] for u in uyeler) / len(uyeler)
        lon = sum(u["lon"] for u in uyeler) / len(uyeler)
        ust_satirlar.append({"id": kid, "feed_id": KUME_BESLEME, "code": None, "name": ad, "lat": lat, "lon": lon,
                             "location_type": 1, "parent_station": None, "wheelchair_boarding": None})
        for u in uyeler:
            kume_of[u["id"]] = kid
            atamalar.append({"b_id": u["id"], "b_parent": kid})
        kume_bilgi[kid] = {"ad": ad, "lat": lat, "lon": lon, "uye": len(uyeler),
                           "modlar": sorted(set().union(*[u["modlar"] for u in uyeler])),
                           "elle": _elle_sure(lat, lon, tanim.get("sureler", []))}
    if ust_satirlar:
        session.add(GtfsFeed(id=KUME_BESLEME, name="Aktarma istasyon kümeleri (otomatik, #11)",
                             source_note="app/gtfs/transfers.py; mesafeye göre; `aktarma` komutuyla yeniden üretilir."))
        session.flush()
        _toplu_ekle(session, GtfsStop, ust_satirlar)
        for a in atamalar:
            session.execute(update(GtfsStop).where(GtfsStop.id == a["b_id"]).values(parent_station=a["b_parent"]))

    # 2) yürüme kenarları (tüm durak türleri, ≤ yaricap)
    izgara = _Izgara(duraklar, yaricap_m) if duraklar else None
    kenarlar, kume_ici, elle_sayi = [], 0, 0
    for i, d in enumerate(duraklar):
        if izgara is None:
            break
        for j, m in izgara.komsular(i, yaricap_m):
            e = duraklar[j]
            sn = yurume_suresi_sn(m)
            ayni_kume = kume_of.get(d["id"]) is not None and kume_of.get(d["id"]) == kume_of.get(e["id"])
            if ayni_kume:
                kume_ici += 1
                sn = max(sn, KUME_ICI_EN_AZ_SN)
                elle = kume_bilgi[kume_of[d["id"]]]["elle"]
                if elle:
                    sn, elle_sayi = max(sn, elle[0]), elle_sayi + 1
            kenarlar.append({"feed_id": None, "from_stop_id": d["id"], "to_stop_id": e["id"],
                             "transfer_type": 2, "min_transfer_secs": sn, "source": "auto"})
    # istasyon türü duraklar için geniş yarıçap: 150 m'den uzak çiftler; farklı beslemeler her zaman, aynı
    # beslemede yalnız ORTAK HAT YOKSA (ör. M2 Taksim ↔ F1 Taksim); ardışık duraklar birbirine bağlanmaz
    if len(ist) > 1 and istasyon_yaricap_m > yaricap_m:
        ig = _Izgara(ist, istasyon_yaricap_m)
        for i, d in enumerate(ist):
            for j, m in ig.komsular(i, istasyon_yaricap_m):
                e = ist[j]
                if m <= yaricap_m:
                    continue
                if d["feed"] == e["feed"] and d["hatlar"] & e["hatlar"]:
                    continue        # aynı beslemede ortak hat varsa ardışık duraktır, aktarma değil
                kenarlar.append({"feed_id": None, "from_stop_id": d["id"], "to_stop_id": e["id"],
                                 "transfer_type": 2, "min_transfer_secs": yurume_suresi_sn(m), "source": "auto"})
    _toplu_ekle(session, GtfsTransfer, kenarlar)
    session.commit()
    log(f"{len(kenarlar)} yürüme kenarı, {len(kume_listesi)} istasyon kümesi")

    kenar_cifti = Counter()
    feed_of = {d["id"]: d["feed"] for d in duraklar}
    for k in kenarlar:
        kenar_cifti[tuple(sorted((feed_of[k["from_stop_id"]], feed_of[k["to_stop_id"]])))] += 1
    return {"durak": len(duraklar), "istasyon_duragi": len(ist), "kenar": len(kenarlar), "kume_ici_kenar": kume_ici,
            "elle_sureli_kenar": elle_sayi, "kume": len(kume_listesi),
            "beslemeler_arasi_kenar": {f"{a}-{b}": n for (a, b), n in sorted(kenar_cifti.items())},
            "kumeler": kume_bilgi}


# ---------------------------------------------------------------- rapor
def bilinen_noktalar(session: Session, tanim: Optional[dict] = None) -> List[dict]:
    """Tanım dosyasındaki büyük aktarma noktaları için: yarıçap içindeki istasyon türü duraklar, bulunan modlar
    ve bu durakların kümeler/yürüme kenarlarıyla kaç ayrı gruba bölündüğü (1 = hepsi birbirine bağlı).
    Kabul kriteri (10 büyük noktada doğru kümeleme) bu rapor gözle doğrulanarak karşılanır."""
    tanim = tanim if tanim is not None else tanim_oku()
    modlar = durak_modlari(session)
    adaylar = session.execute(select(GtfsStop).where(GtfsStop.location_type == 0,
                                                     GtfsStop.id.in_(list(modlar) or [""]))).scalars().all()
    sonuc = []
    for b in tanim.get("bilinen_noktalar", []):
        icerde = [x for x in adaylar if mesafe_m(x.lat, x.lon, b["enlem"], b["boylam"]) <= b["yaricap_m"]]
        ids = {x.id for x in icerde}
        ust = {}
        def bul(x):
            while ust.setdefault(x, x) != x:
                ust[x] = ust[ust[x]]
                x = ust[x]
            return x
        for x in icerde:
            bul(x.id)
        if ids:
            for f, t in session.execute(select(GtfsTransfer.from_stop_id, GtfsTransfer.to_stop_id)
                                        .where(GtfsTransfer.from_stop_id.in_(ids), GtfsTransfer.to_stop_id.in_(ids))):
                ust[bul(f)] = bul(t)
        gruplar = len({bul(i) for i in ids})
        kumeler = sorted({x.parent_station for x in icerde if x.parent_station})
        sonuc.append({
            "ad": b["ad"], "beklenen_modlar": b.get("beklenen_modlar", []), "grup": gruplar if ids else 0,
            "kume_sayisi": len(kumeler),
            "bulunan_modlar": sorted({m for x in icerde for m in modlar.get(x.id, ())}),
            "duraklar": [{"ad": x.name, "besleme": x.feed_id, "modlar": sorted(modlar.get(x.id, [])),
                          "kume": x.parent_station} for x in icerde]})
    return sonuc


def ozet_metni(ozet: dict) -> str:
    s = [f"Durak: {ozet['durak']} (istasyon türü: {ozet['istasyon_duragi']})",
         f"Yürüme kenarı: {ozet['kenar']} (küme içi {ozet['kume_ici_kenar']}, elle süreli {ozet['elle_sureli_kenar']})",
         f"İstasyon kümesi: {ozet['kume']}"]
    for ad, n in ozet["beslemeler_arasi_kenar"].items():
        s.append(f"  kenar {ad}: {n}")
    return "\n".join(s)


def nokta_raporu_metni(noktalar: List[dict]) -> str:
    s = []
    for n in noktalar:
        eksik = sorted(set(n["beklenen_modlar"]) - set(n["bulunan_modlar"]))
        tamam = n["duraklar"] and not eksik and n["grup"] == 1
        s.append(f"{'OK ' if tamam else '!  '}{n['ad']}: modlar {n['bulunan_modlar'] or '-'}, "
                 f"{len(n['duraklar'])} durak, {n['kume_sayisi']} küme, {n['grup']} bağlı grup"
                 + (f" | EKSİK MOD: {eksik}" if eksik else "") + (" | DURAK YOK" if not n["duraklar"] else ""))
        for d in n["duraklar"]:
            s.append(f"     {d['ad']} [{d['besleme']}:{','.join(d['modlar']) or '-'}]" + (" *" if d["kume"] else ""))
    return "\n".join(s)

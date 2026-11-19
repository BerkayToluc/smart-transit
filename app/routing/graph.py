"""Rota motoru için bellek-içi sefer grafiği.

Veritabanındaki gtfs_* tabloları yalnızca KAYNAKTIR; planlama bellekte, kompakt dizilerle yapılır
(İETT tek başına ~6 milyon durak saati: Python nesneleriyle yüzlerce MB tutar, `array('i')` ile ~50 MB).

Yapı:
  * **Örüntü (pattern):** aynı hat + aynı durak dizisi + aynı biniş/iniş kuralları. Seferleri ilk kalkış
    saatine göre sıralıdır. Saatler SÜTUN-majör `array('i')` olarak tutulur (`kalkis[sira]`, `varis[sira]`):
    "şu durakta saat t'den sonraki ilk sefer" sorusu `bisect` ile yanıtlanır.
  * **Gün:** seferler hizmet gün maskesiyle (bit 0 = Pazartesi ... bit 6 = Pazar) saklanır; sorgu günü
    sorgu anında uygulanır, böylece 7 ayrı graf gerekmez. Gece yarısını aşan seferler (25:20 gibi) bir
    sonraki günün sorgusunda -86400 kaymasıyla görünür (bkz. raptor.py).
  * **Aralıklı (frequency) seferler** yüklemede somut seferlere açılır (şablon sefer + pencere).
  * **Yürüme:** `gtfs_transfer` kenarları (transfer_type 3 hariç) durak başına liste.
  * Önbellek: `kaydet`/`oku` pickle; parmak izi (besleme yüklenme zamanları + kenar sayısı) değişince yeniden kurulur.
"""
import math
import os
import pickle
from array import array
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.gtfs.models import (
    GtfsCalendar, GtfsFeed, GtfsFrequency, GtfsRoute, GtfsStop, GtfsStopTime, GtfsTransfer, GtfsTrip,
)

SURUM = 1                    # pickle düzeni değişince artırılır
GUN_SANIYE = 86400
_GUNLER = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
IZGARA_M = 500.0             # durak arama izgara_hucresı hücre boyutu


@dataclass
class Patern:
    hat: int                          # graf.hat_* indeksi
    mod: str
    duraklar: List[int]               # durak indeksleri (sırayla)
    biner: List[bool]                 # o durakta binilebilir mi
    iner: List[bool]                  # o durakta inilebilir mi
    kalkis: List[array]               # kalkis[sira][sefer] -> sn (sütun-majör)
    varis: List[array]
    maske: array                      # sefer başına gün maskesi
    meta: array                       # sefer başına graf.meta_* indeksi
    sefer_sayisi: int = 0


@dataclass
class Graf:
    durak_id: List[str] = field(default_factory=list)
    durak_ad: List[str] = field(default_factory=list)
    durak_lat: List[float] = field(default_factory=list)
    durak_lon: List[float] = field(default_factory=list)
    hat_id: List[str] = field(default_factory=list)
    hat_kisa: List[str] = field(default_factory=list)
    hat_uzun: List[str] = field(default_factory=list)
    hat_mod: List[str] = field(default_factory=list)
    meta_sefer_id: List[str] = field(default_factory=list)
    meta_baslik: List[str] = field(default_factory=list)
    paternler: List[Patern] = field(default_factory=list)
    durak_paternleri: List[List[Tuple[int, int]]] = field(default_factory=list)   # durak -> [(patern, sıra)]
    yurume: List[List[Tuple[int, int]]] = field(default_factory=list)             # durak -> [(durak, sn)]
    izgara_hucre: Dict[Tuple[int, int], List[int]] = field(default_factory=dict)
    parmak_izi: str = ""
    surum: int = SURUM

    @property
    def durak_sayisi(self) -> int:
        return len(self.durak_id)

    def sefer_sayisi(self) -> int:
        return sum(p.sefer_sayisi for p in self.paternler)

    def izgara_kur(self) -> None:
        self.izgara_hucre = defaultdict(list)
        for i, (la, lo) in enumerate(zip(self.durak_lat, self.durak_lon)):
            self.izgara_hucre[_hucre(la, lo)].append(i)

    def yakin_duraklar(self, lat: float, lon: float, yaricap_m: float) -> List[Tuple[int, float]]:
        """(durak, mesafe_m) listesi, yakından uzağa. Yalnız seferi olan duraklar."""
        r = int(yaricap_m // IZGARA_M) + 1
        cy, cx = _hucre(lat, lon)
        sonuc = []
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                for i in self.izgara_hucre.get((cy + dy, cx + dx), ()):
                    if not self.durak_paternleri[i]:
                        continue
                    m = mesafe_m(lat, lon, self.durak_lat[i], self.durak_lon[i])
                    if m <= yaricap_m:
                        sonuc.append((i, m))
        sonuc.sort(key=lambda x: x[1])
        return sonuc


def mesafe_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _hucre(lat: float, lon: float) -> Tuple[int, int]:
    return (math.floor(lat * 111_000.0 / IZGARA_M), math.floor(lon * 83_800.0 / IZGARA_M))   # 41° enleminde


# ---------------------------------------------------------------- veritabanından kurma
def parmak_izi(session: Session) -> str:
    """Beslemelerin yüklenme zamanları + aktarma kenarı sayısı: değişirse önbellek geçersiz."""
    f = session.execute(select(GtfsFeed.id, GtfsFeed.imported_at).order_by(GtfsFeed.id)).all()
    n = session.execute(select(func.count()).select_from(GtfsTransfer)).scalar_one()
    return f"v{SURUM}|" + ";".join(f"{i}@{t}" for i, t in f) + f"|tr={n}"


def _gun_maskesi(c: GtfsCalendar) -> int:
    return sum(1 << i for i, ad in enumerate(_GUNLER) if getattr(c, ad))


def _saatleri_tamamla(arr: list, dep: list) -> bool:
    """Boş (None) ara saatleri doğrusal enterpolasyonla doldurur; baş/son saat yoksa False."""
    n = len(arr)
    for i in range(n):
        if arr[i] is None and dep[i] is not None:
            arr[i] = dep[i]
        if dep[i] is None and arr[i] is not None:
            dep[i] = arr[i]
    if arr[0] is None or dep[-1] is None:
        return False
    zaman = [(a if a is not None else None) for a in arr]
    i = 0
    while i < n:
        if zaman[i] is None:
            j = i
            while j < n and zaman[j] is None:
                j += 1
            if j >= n:
                return False
            sol, sag = zaman[i - 1], zaman[j]
            for k in range(i, j):
                zaman[k] = sol + (sag - sol) * (k - i + 1) // (j - i + 1)
                arr[k] = dep[k] = zaman[k]
            i = j
        i += 1
    return True


def kur(session: Session, *, log=lambda m: None) -> Graf:
    """Veritabanından grafı kurar. (İETT dahil büyük veride bir kez birkaç saniye-dakika sürer; sonra pickle.)"""
    g = Graf()
    g.parmak_izi = parmak_izi(session)

    durak_idx: Dict[str, int] = {}
    for s in session.execute(select(GtfsStop.id, GtfsStop.name, GtfsStop.lat, GtfsStop.lon)
                             .where(GtfsStop.location_type == 0).order_by(GtfsStop.id)):
        durak_idx[s.id] = len(g.durak_id)
        g.durak_id.append(s.id); g.durak_ad.append(s.name); g.durak_lat.append(s.lat); g.durak_lon.append(s.lon)
    n_durak = len(g.durak_id)
    g.durak_paternleri = [[] for _ in range(n_durak)]
    g.yurume = [[] for _ in range(n_durak)]
    log(f"{n_durak} durak")

    hat_idx: Dict[str, int] = {}
    for r in session.execute(select(GtfsRoute.id, GtfsRoute.short_name, GtfsRoute.long_name, GtfsRoute.mode)
                             .order_by(GtfsRoute.id)):
        hat_idx[r.id] = len(g.hat_id)
        g.hat_id.append(r.id); g.hat_kisa.append(r.short_name or ""); g.hat_uzun.append(r.long_name or "")
        g.hat_mod.append(r.mode)

    maske_of = {c.service_id: _gun_maskesi(c) for c in session.execute(select(GtfsCalendar)).scalars()}
    sefer_bilgi: Dict[str, Tuple[int, int, str]] = {}
    for t in session.execute(select(GtfsTrip.id, GtfsTrip.route_id, GtfsTrip.service_id, GtfsTrip.headsign)):
        m = maske_of.get(t.service_id, 0)
        if m and t.route_id in hat_idx:              # günü olmayan hizmet planlamada çalışmaz
            sefer_bilgi[t.id] = (hat_idx[t.route_id], m, t.headsign or "")
    log(f"{len(sefer_bilgi)} sefer (günü olan)")

    aralik: Dict[str, List[Tuple[int, int, int]]] = defaultdict(list)
    for f in session.execute(select(GtfsFrequency.trip_id, GtfsFrequency.start_secs, GtfsFrequency.end_secs,
                                    GtfsFrequency.headway_secs)):
        aralik[f.trip_id].append((f.start_secs, f.end_secs, f.headway_secs))

    # örüntü kurucuları: anahtar -> satırlar [(ilk_kalkis, maske, meta, varis_listesi, kalkis_listesi)]
    kurucular: Dict[tuple, list] = defaultdict(list)

    def sefer_ekle(tid, hat, mask, baslik, duraklar, binme, inme, arr, dep, kayma):
        meta = len(g.meta_sefer_id)
        g.meta_sefer_id.append(tid if not kayma else f"{tid}@{kayma}")
        g.meta_baslik.append(baslik)
        a = array("i", [x + kayma for x in arr])       # kompakt: 6 milyon satırda Python int listeleri yüzlerce MB tutar
        d = array("i", [x + kayma for x in dep])
        kurucular[(hat, tuple(duraklar), tuple(binme), tuple(inme))].append((d[0], mask, meta, a, d))

    def sefer_isle(tid, satirlar):
        bilgi = sefer_bilgi.get(tid)
        if bilgi is None or len(satirlar) < 2:
            return
        hat, mask, baslik = bilgi
        duraklar, binme, inme, arr, dep = [], [], [], [], []
        for s_id, a, d, pk, dr in satirlar:
            i = durak_idx.get(s_id)
            if i is None:
                continue
            duraklar.append(i); binme.append(pk == 0); inme.append(dr == 0); arr.append(a); dep.append(d)
        if len(duraklar) < 2 or not _saatleri_tamamla(arr, dep):
            return
        # saatler artan olmalı (bozuk satırlar planlamayı bozmasın)
        for k in range(1, len(arr)):
            if arr[k] < dep[k - 1]:
                arr[k] = dep[k - 1]
            if dep[k] < arr[k]:
                dep[k] = arr[k]
        if tid in aralik:
            sifir = dep[0]
            for bas, bit, ar in aralik[tid]:
                for t0 in range(bas, bit, ar):
                    sefer_ekle(tid, hat, mask, baslik, duraklar, binme, inme, arr, dep, t0 - sifir)
        else:
            sefer_ekle(tid, hat, mask, baslik, duraklar, binme, inme, arr, dep, 0)

    q = (select(GtfsStopTime.trip_id, GtfsStopTime.stop_id, GtfsStopTime.arrival_secs, GtfsStopTime.departure_secs,
                GtfsStopTime.pickup_type, GtfsStopTime.drop_off_type)
         .order_by(GtfsStopTime.trip_id, GtfsStopTime.stop_sequence).execution_options(yield_per=200_000))
    onceki, satirlar, n = None, [], 0
    for r in session.execute(q):
        if r.trip_id != onceki:
            if onceki is not None:
                sefer_isle(onceki, satirlar)
            onceki, satirlar = r.trip_id, []
            n += 1
            if n % 20000 == 0:
                log(f"{n} sefer işlendi")
        satirlar.append((r.stop_id, r.arrival_secs, r.departure_secs, r.pickup_type, r.drop_off_type))
    if onceki is not None:
        sefer_isle(onceki, satirlar)

    for (hat, duraklar, binme, inme), satir in kurucular.items():
        satir.sort(key=lambda x: x[0])
        n_sefer = len(satir)
        p = Patern(hat=hat, mod=g.hat_mod[hat], duraklar=list(duraklar), biner=list(binme), iner=list(inme),
                   kalkis=[array("i", [s[4][i] for s in satir]) for i in range(len(duraklar))],
                   varis=[array("i", [s[3][i] for s in satir]) for i in range(len(duraklar))],
                   maske=array("i", [s[1] for s in satir]), meta=array("i", [s[2] for s in satir]),
                   sefer_sayisi=n_sefer)
        pi = len(g.paternler)
        g.paternler.append(p)
        for sira, d in enumerate(duraklar):
            g.durak_paternleri[d].append((pi, sira))
    kurucular.clear()
    log(f"{len(g.paternler)} örüntü, {g.sefer_sayisi()} sefer")

    for t in session.execute(select(GtfsTransfer.from_stop_id, GtfsTransfer.to_stop_id, GtfsTransfer.transfer_type,
                                    GtfsTransfer.min_transfer_secs)):
        a, b = durak_idx.get(t.from_stop_id), durak_idx.get(t.to_stop_id)
        if a is None or b is None or a == b or t.transfer_type == 3:
            continue
        g.yurume[a].append((b, int(t.min_transfer_secs) if t.min_transfer_secs is not None else 0))
    g.izgara_kur()
    return g


# ---------------------------------------------------------------- önbellek
def kaydet(g: Graf, yol: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(yol)), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "wb") as f:
        pickle.dump(g, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(gecici, yol)


def oku(yol: str) -> Optional[Graf]:
    try:
        with open(yol, "rb") as f:
            g = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
        return None
    return g if isinstance(g, Graf) and g.surum == SURUM else None


def yukle(session: Session, onbellek: Optional[str] = None, *, log=lambda m: None) -> Graf:
    """Önbellek geçerliyse pickle'dan, değilse veritabanından kurar (ve önbelleği yazar)."""
    iz = parmak_izi(session)
    if onbellek:
        g = oku(onbellek)
        if g is not None and g.parmak_izi == iz:
            log(f"graf önbellekten yüklendi ({onbellek})")
            return g
    g = kur(session, log=log)
    if onbellek:
        kaydet(g, onbellek)
        log(f"graf önbelleğe yazıldı ({onbellek})")
    return g

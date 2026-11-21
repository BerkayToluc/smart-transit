"""Resmî hat güzergah çizgileri (İETT Hat Güzergahları GeoJSON'u; metrobüs hatları dahil).

İETT'nin GTFS'inde `shapes` yoktur; İBB açık veri portalındaki `iett-hat-guzergahlari` GeoJSON'u her hat ve yön için gerçek
yol/şerit çizgisini verir. Rota planlayıcı, bir otobüs/metrobüs bacağı için ilgili hattın çizgisini bulur, biniş ve iniş
duraklarını çizgi üzerine izdüşürür ve aradaki parçayı kesip döndürür (Google'a hiç sormadan, yolu/şeridi tam izler).

Dosya: `gtfs_data/iett-hat-guzergahlari.geojson` (`python scripts/build_gtfs.py guzergah` indirir ve dizinler);
dizin: `gtfs_data/guzergah.pkl`.
"""
import math
import os
import pickle
from array import array
from typing import Dict, List, Optional, Tuple

SURUM = 1
KOD_ANAHTARLARI = ("HAT_KODU", "hat_kodu")
GUZERGAH_ANAHTARLARI = ("GUZERGAH_KODU", "guzergah_kodu")
EN_COK_SAPMA_M = 200.0        # durağın çizgiden en çok bu kadar uzakta olmasına izin verilir
EN_AZ_ILERI_M = 30.0          # iniş, binişten çizgi boyunca en az bu kadar ileride olmalı
_KY = 111_000.0


class Parca:
    """Bir hattın tek bir güzergah çizgisi (bir yön / varyant)."""

    __slots__ = ("kod", "lat", "lon", "kum")

    def __init__(self, kod: str, lat: array, lon: array):
        self.kod = kod
        self.lat, self.lon = lat, lon
        kx = 83_800.0
        kum = array("d", [0.0])
        for i in range(1, len(lat)):
            kum.append(kum[-1] + math.hypot((lat[i] - lat[i - 1]) * _KY, (lon[i] - lon[i - 1]) * kx))
        self.kum = kum

    def __getstate__(self):
        return (self.kod, self.lat, self.lon, self.kum)

    def __setstate__(self, d):
        self.kod, self.lat, self.lon, self.kum = d

    def proje(self, lat: float, lon: float) -> Tuple[float, float, int, float]:
        """(çizgiye uzaklık m, çizgi boyu konumu m, segment indeksi, segment içi t)."""
        kx = 83_800.0
        en = (1e18, 0.0, 0, 0.0)
        la, lo = self.lat, self.lon
        for i in range(len(la) - 1):
            ax, ay = (lo[i] - lon) * kx, (la[i] - lat) * _KY
            bx, by = (lo[i + 1] - lon) * kx, (la[i + 1] - lat) * _KY
            dx, dy = bx - ax, by - ay
            u = dx * dx + dy * dy
            t = 0.0 if u < 1e-9 else max(0.0, min(1.0, -(ax * dx + ay * dy) / u))
            px, py = ax + dx * t, ay + dy * t
            d2 = px * px + py * py
            if d2 < en[0]:
                en = (d2, self.kum[i] + t * (self.kum[i + 1] - self.kum[i]), i, t)
        return (math.sqrt(en[0]), en[1], en[2], en[3])

    def kes(self, bas: Tuple[int, float], bit: Tuple[int, float]) -> List[Tuple[float, float]]:
        (i1, t1), (i2, t2) = bas, bit
        la, lo = self.lat, self.lon

        def nokta(i, t):
            return (la[i] + (la[i + 1] - la[i]) * t, lo[i] + (lo[i + 1] - lo[i]) * t)

        yol = [nokta(i1, t1)]
        yol.extend((la[k], lo[k]) for k in range(i1 + 1, i2 + 1))
        yol.append(nokta(i2, t2))
        return yol


class Guzergah:
    def __init__(self, hatlar: Dict[str, List[Parca]]):
        self.hatlar = hatlar
        self.surum = SURUM
        self._onbellek: Dict[tuple, Optional[List[Tuple[float, float]]]] = {}

    def __getstate__(self):
        return {"hatlar": self.hatlar, "surum": self.surum}

    def __setstate__(self, d):
        self.hatlar, self.surum, self._onbellek = d["hatlar"], d["surum"], {}

    def dilimle(self, hat: Optional[str], bas: Tuple[float, float], bit: Tuple[float, float]) -> Optional[List[Tuple[float, float]]]:
        """`hat`ın çizgisinden biniş→iniş arası parça [(enlem, boylam), ...]; uygun çizgi yoksa None."""
        if not hat or hat not in self.hatlar:
            return None
        anahtar = (hat, round(bas[0], 5), round(bas[1], 5), round(bit[0], 5), round(bit[1], 5))
        if anahtar in self._onbellek:
            return self._onbellek[anahtar]
        en_iyi, en_iyi_puan = None, 1e18
        for p in self.hatlar[hat]:
            d1, s1, i1, t1 = p.proje(*bas)
            d2, s2, i2, t2 = p.proje(*bit)
            if d1 > EN_COK_SAPMA_M or d2 > EN_COK_SAPMA_M or s2 < s1 + EN_AZ_ILERI_M:
                continue
            if d1 + d2 < en_iyi_puan:
                en_iyi_puan, en_iyi = d1 + d2, p.kes((i1, t1), (i2, t2))
        if len(self._onbellek) > 5000:
            self._onbellek.clear()
        if en_iyi is not None:
            en_iyi = [bas] + en_iyi + [bit]          # uçlar tam durak konumu: rota çizgisiyle bitişik
        self._onbellek[anahtar] = en_iyi
        return en_iyi

    def ozet(self) -> Dict[str, int]:
        return {"hat": len(self.hatlar), "cizgi": sum(len(v) for v in self.hatlar.values()),
                "nokta": sum(len(p.lat) for v in self.hatlar.values() for p in v)}


def indeks_kur(geojson_yolu: str, log=lambda m: None) -> Guzergah:
    """GeoJSON'u akış halinde okuyup hat -> çizgi dizinini kurar (dosya yüzlerce MB olabilir)."""
    import ijson

    hatlar: Dict[str, List[Parca]] = {}
    n = 0
    with open(geojson_yolu, "rb") as f:
        for ozellik in ijson.items(f, "features.item", use_float=True):
            n += 1
            ozel = ozellik.get("properties") or {}
            hat = next((str(ozel[k]).strip() for k in KOD_ANAHTARLARI if ozel.get(k)), "")
            kod = next((str(ozel[k]).strip() for k in GUZERGAH_ANAHTARLARI if ozel.get(k)), "")
            geo = ozellik.get("geometry") or {}
            parcalar = geo.get("coordinates") or []
            if geo.get("type") == "LineString":
                parcalar = [parcalar]
            elif geo.get("type") != "MultiLineString":
                continue
            if not hat:
                continue
            for dizi in parcalar:
                if len(dizi) < 2:
                    continue
                hatlar.setdefault(hat, []).append(
                    Parca(kod, array("d", [float(p[1]) for p in dizi]), array("d", [float(p[0]) for p in dizi])))
            if n % 2000 == 0:
                log(f"{n} çizgi okundu")
    return Guzergah(hatlar)


def kaydet(g: Guzergah, yol: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(yol)), exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "wb") as f:
        pickle.dump(g, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(gecici, yol)


def oku(yol: str) -> Optional[Guzergah]:
    try:
        with open(yol, "rb") as f:
            g = pickle.load(f)
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
        return None
    return g if isinstance(g, Guzergah) and g.surum == SURUM else None

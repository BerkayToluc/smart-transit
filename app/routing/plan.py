"""Koordinattan koordinata planlama: erişim/çıkış yürümesi + RAPTOR + tercihe göre sıralama."""
import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from app.routing import raptor
from app.routing.graph import Graf, mesafe_m
from app.routing.raptor import Etap

YURUME_KATSAYISI = 1.3
YURUME_HIZI_MS = 4.8 / 3.6
TERCIHLER = ("hizli", "az_aktarma", "az_yuruyus")


def yurume_sn(mesafe: float) -> int:
    return math.ceil(mesafe * YURUME_KATSAYISI / YURUME_HIZI_MS)


@dataclass
class Secenek:
    kalkis: int                       # ilk etabın başlangıcı, sn
    varis: int                        # son etabın bitişi, sn
    aktarma: int
    yuruyus_m: float
    etaplar: List[Etap] = field(default_factory=list)

    @property
    def sure(self) -> int:
        return self.varis - self.kalkis


def _yuruyus_m(g: Graf, etaplar: List[Etap], bas_koord, bit_koord) -> float:
    toplam = 0.0
    for e in etaplar:
        if e.tip != "yurume":
            continue
        a = bas_koord if e.bas < 0 else (g.durak_lat[e.bas], g.durak_lon[e.bas])
        b = bit_koord if e.bit < 0 else (g.durak_lat[e.bit], g.durak_lon[e.bit])
        toplam += mesafe_m(a[0], a[1], b[0], b[1]) * YURUME_KATSAYISI
    return toplam


def planla(g: Graf, bas: tuple, bit: tuple, gun: int, saat_sn: int, *, izinli_modlar: Optional[Iterable[str]] = None,
           max_aktarma: int = 3, max_yurume_m: float = 800.0, tercih: str = "hizli", en_cok: int = 5,
           aktarma_payi_sn: int = 60, erisim_sayisi: int = 40) -> List[Secenek]:
    """`bas`/`bit` (enlem, boylam). `saat_sn`: kalkış anı (gece yarısından sn). Seçenekler tercihe göre sıralı."""
    if tercih not in TERCIHLER:
        raise ValueError(f"tercih {TERCIHLER} içinden olmalı: {tercih!r}")
    erisim = g.yakin_duraklar(bas[0], bas[1], max_yurume_m)[:erisim_sayisi]
    cikis = g.yakin_duraklar(bit[0], bit[1], max_yurume_m)[:erisim_sayisi]
    secenekler: List[Secenek] = []

    # yalnız yürüyüş (yakınsa)
    dogrudan_m = mesafe_m(bas[0], bas[1], bit[0], bit[1])
    if dogrudan_m * YURUME_KATSAYISI <= max_yurume_m * 1.5:
        sn = yurume_sn(dogrudan_m)
        e = Etap("yurume", -1, -1, saat_sn, saat_sn + sn)
        secenekler.append(Secenek(saat_sn, saat_sn + sn, 0, dogrudan_m * YURUME_KATSAYISI, [e]))

    if erisim and cikis:
        kaynaklar, hedefler, giris_sn = {}, {}, {}
        for i, m in erisim:
            sn = yurume_sn(m)
            kaynaklar[i] = saat_sn + sn
            giris_sn[i] = sn
        for i, m in cikis:
            hedefler[i] = yurume_sn(m)
        for y in raptor.ara(g, kaynaklar, hedefler, gun, max_aktarma=max_aktarma, izinli_modlar=izinli_modlar,
                            aktarma_payi_sn=aktarma_payi_sn):
            if not any(e.tip == "arac" for e in y.etaplar):
                continue                      # araçsız (yalnız yürüyüş) sonuç: doğrudan yürüyüş zaten ayrı eklendi
            etaplar = list(y.etaplar)
            ilk = Etap("yurume", -1, y.kaynak, saat_sn, saat_sn + giris_sn[y.kaynak])
            son_t = etaplar[-1].varis if etaplar else ilk.varis
            son = Etap("yurume", y.hedef, -1, son_t, son_t + hedefler[y.hedef])
            tam = [ilk] + etaplar + [son]
            secenekler.append(Secenek(saat_sn, son.varis, y.aktarma, _yuruyus_m(g, tam, bas, bit), tam))

    # aynı güzergâhı tekrarlayanları ele
    goruldu, tekil = set(), []
    for s in secenekler:
        iz = tuple((e.tip, e.bas, e.bit, e.meta) for e in s.etaplar if e.tip == "arac") or ("yaya",)
        if iz not in goruldu:
            goruldu.add(iz)
            tekil.append(s)
    anahtar = {"hizli": lambda s: (s.varis, s.aktarma, s.yuruyus_m),
               "az_aktarma": lambda s: (s.aktarma, s.varis, s.yuruyus_m),
               "az_yuruyus": lambda s: (s.yuruyus_m, s.varis, s.aktarma)}[tercih]
    tekil.sort(key=anahtar)
    return tekil[:en_cok]


# ---------------------------------------------------------------- metin çıktısı (CLI / hata ayıklama)
def saat_metni(sn: int) -> str:
    gun, sn = divmod(int(sn), 86400)
    s = f"{sn // 3600:02d}:{sn % 3600 // 60:02d}"
    return s + (f"+{gun}g" if gun else "")


def secenek_metni(g: Graf, s: Secenek, no: int = 1) -> str:
    satir = [f"Seçenek {no}: {s.sure // 60} dk, {s.aktarma} aktarma, {s.yuruyus_m:.0f} m yürüyüş "
             f"({saat_metni(s.kalkis)} → {saat_metni(s.varis)})"]
    for e in s.etaplar:
        zaman = f"{saat_metni(e.kalkis)}-{saat_metni(e.varis)}"
        if e.tip == "yurume":
            a = "başlangıç" if e.bas < 0 else g.durak_ad[e.bas]
            b = "varış" if e.bit < 0 else g.durak_ad[e.bit]
            satir.append(f"  {zaman}  yürü ({(e.varis - e.kalkis) // 60} dk): {a} → {b}")
        else:
            satir.append(f"  {zaman}  {e.mod} {g.hat_kisa[e.hat]}: {g.durak_ad[e.bas]} → {g.durak_ad[e.bit]} "
                         f"({e.durak_sayisi} durak) yön: {g.meta_baslik[e.meta]}")
    return "\n".join(satir)

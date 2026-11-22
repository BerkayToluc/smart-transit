"""RAPTOR (Round-bAsed Public Transit Routing) — Delling, Pajor, Werneck.

Tur k, en çok k araç kullanan en erken varışları hesaplar; her turda yalnızca bir önceki turda
iyileşen duraklardan geçen örüntüler taranır. Sonuç, (varış saati, aktarma sayısı) için PARETO kümesidir:
daha çok aktarma ancak daha erken varış sağlayan seçenekler birlikte döner.

Burada kullanılanlar:
  * Yürüme aktarmaları (`graf.yurume`), her turun sonunda yalnızca araçla iyileşen duraklardan, zincirleme olmadan.
  * Araca binerken `aktarma_payi_sn` (2. turdan itibaren; ilk binişte yok: yolcu zaten durakta bekler).
  * `izinli_modlar` süzgeci, `max_aktarma`, biniş/iniş yasakları (`biner`/`iner`).
  * Gün: `gun` 0=Pazartesi ... 6=Pazar. Önceki günün 24:00'ı aşan seferleri (25:20 gibi) bugünün
    erken saatlerinde -86400 kaymasıyla yakalanır; bugünün gece seferleri 24:00 sonrası saatlerle sürer.
  * Sefer sırası: örüntüdeki seferler ilk kalkışa göre sıralı kabul edilir (aralarında "geçme" yoksa
    ikili arama kesindir; varsa yalnızca küçük, nadir sapma olabilir).
"""
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from app.routing.graph import GUN_SANIYE, Graf

INF = 10 ** 9


@dataclass
class Etap:
    tip: str                       # "yurume" | "arac"
    bas: int                       # başlangıç durak indeksi (yürüme: -1 = koordinat)
    bit: int                       # bitiş durak indeksi
    kalkis: int                    # sn (gece yarısından)
    varis: int
    patern: int = -1
    hat: int = -1
    mod: str = ""
    meta: int = -1                 # graf.meta_* indeksi (sefer kimliği, yön başlığı)
    bas_sira: int = -1             # örüntüdeki biniş / iniş sırası
    bit_sira: int = -1

    @property
    def durak_sayisi(self) -> int:
        return self.bit_sira - self.bas_sira if self.tip == "arac" else 0


@dataclass
class Yolculuk:
    aktarma: int                   # araç etabı sayısı - 1
    varis: int                     # hedefe (çıkış yürümesi dahil) varış, sn
    kaynak: int
    hedef: int
    etaplar: List[Etap] = field(default_factory=list)


def _sonraki(p, sira: int, esik: int, gun: int):
    """`sira`daki durakta `esik` sn'den sonraki ilk uygun sefer: (kalkış_sn, satır, kayma) ya da None.
    kayma=1: önceki günün (24:00'ı aşan) seferi."""
    kol = p.kalkis[sira]
    n = p.sefer_sayisi
    bugun, dun = 1 << gun, 1 << ((gun - 1) % 7)
    en_iyi = None
    i = bisect_left(kol, esik)
    while i < n:
        if p.maske[i] & bugun:
            en_iyi = (kol[i], i, 0)
            break
        i += 1
    j = bisect_left(kol, esik + GUN_SANIYE)
    while j < n:
        if p.maske[j] & dun:
            if en_iyi is None or kol[j] - GUN_SANIYE < en_iyi[0]:
                en_iyi = (kol[j] - GUN_SANIYE, j, 1)
            break
        j += 1
    return en_iyi


def ara(g: Graf, kaynaklar: Dict[int, int], hedefler: Dict[int, int], gun: int, *, max_aktarma: int = 3,
        izinli_modlar: Optional[Iterable[str]] = None, aktarma_payi_sn: int = 60,
        yasak_hatlar: Optional[Iterable[int]] = None) -> List[Yolculuk]:
    """Kaynak duraklardan (durak -> oradaki varış saati, sn) hedef duraklara (durak -> çıkış yürümesi, sn).

    Pareto sonuçları (erken varış / az aktarma) döner; aktarma sayısına göre artan sıralıdır."""
    izinli = set(izinli_modlar) if izinli_modlar is not None else None
    yasak = set(yasak_hatlar) if yasak_hatlar else None       # bu hatlar (graf.hat_* indeksi) hiç kullanılmaz (alternatif arama)
    n = g.durak_sayisi
    tur_sayisi = max_aktarma + 1
    en_iyi = [INF] * n
    tau_onceki = [INF] * n
    arac: List[dict] = [dict() for _ in range(tur_sayisi + 1)]
    son: List[dict] = [dict() for _ in range(tur_sayisi + 1)]
    sinir = INF                                   # şimdiye dek hedefe en erken varış (çıkış yürümesi dahil)

    def hedefe_bak(s: int, t: int):
        nonlocal sinir
        e = hedefler.get(s)
        if e is not None and t + e < sinir:
            sinir = t + e

    def yuru(r: int, tau: list, anlik: List[Tuple[int, int]], isaretli: set) -> None:
        for s, t0 in anlik:
            for q, sn in g.yurume[s]:
                a = t0 + sn
                if a < en_iyi[q] and a < sinir:
                    tau[q] = a
                    en_iyi[q] = a
                    son[r][q] = ("y", s, sn)
                    isaretli.add(q)
                    hedefe_bak(q, a)

    # --- tur 0: kaynaklar (erişim yürümesi çağıran tarafça hesaplanmış)
    tau = [INF] * n
    isaretli: set = set()
    for s, t in kaynaklar.items():
        if t < tau[s]:
            tau[s] = t
            en_iyi[s] = t
            son[0][s] = ("k",)
            isaretli.add(s)
            hedefe_bak(s, t)
    yuru(0, tau, [(s, tau[s]) for s in list(isaretli)], isaretli)
    tau_onceki = tau

    sonuclar: List[Tuple[int, int, int]] = []      # (tur, hedef durak, toplam varış)
    en_iyi_toplam = INF
    for k in range(1, tur_sayisi + 1):
        tau = list(tau_onceki)
        kuyruk: Dict[int, int] = {}
        for s in isaretli:
            for p, sira in g.durak_paternleri[s]:
                if izinli is not None and g.paternler[p].mod not in izinli:
                    continue
                if yasak is not None and g.paternler[p].hat in yasak:
                    continue
                if p not in kuyruk or sira < kuyruk[p]:
                    kuyruk[p] = sira
        isaretli = set()
        arac_iyi: set = set()
        payi = aktarma_payi_sn if k >= 2 else 0
        for pi, bas in kuyruk.items():
            p = g.paternler[pi]
            duraklar, iner, biner, varis, kalkis = p.duraklar, p.iner, p.biner, p.varis, p.kalkis
            sefer = None                           # (satır, kayma)
            bin_sira = bin_kalkis = -1
            for sira in range(bas, len(duraklar)):
                s = duraklar[sira]
                if sefer is not None and iner[sira]:
                    a = varis[sira][sefer[0]] - sefer[1] * GUN_SANIYE
                    if a < en_iyi[s] and a < sinir:
                        tau[s] = a
                        en_iyi[s] = a
                        arac[k][s] = (pi, sefer[0], sefer[1], bin_sira, sira, bin_kalkis, a)
                        son[k][s] = ("a",)
                        arac_iyi.add(s)
                        isaretli.add(s)
                        hedefe_bak(s, a)
                onc = tau_onceki[s]
                if onc < INF and biner[sira]:
                    esik = onc + payi
                    burada = INF if sefer is None else kalkis[sira][sefer[0]] - sefer[1] * GUN_SANIYE
                    if esik <= burada:                 # bu durakta daha erken (ya da eşit) bir sefere binilebilir
                        yeni = _sonraki(p, sira, esik, gun)
                        if yeni is not None and (yeni[0] < burada or (k == 1 and (yeni[1], yeni[2]) == sefer)):
                            # k == 1: AYNI sefere hem önceki hem bu duraktan binilebiliyorsa (başlangıçtan yürüyerek) varış
                            # aynıdır; daha az yürütmek için sefere sonraki (başlangıca genelde daha yakın) duraktan bin
                            sefer, bin_sira, bin_kalkis = (yeni[1], yeni[2]), sira, yeni[0]
        yuru(k, tau, [(s, tau[s]) for s in arac_iyi], isaretli)

        en = None
        for h, e in hedefler.items():
            if tau[h] < INF and (en is None or tau[h] + e < en[0]):
                en = (tau[h] + e, h)
        if en is not None and en[0] < en_iyi_toplam:
            en_iyi_toplam = en[0]
            sonuclar.append((k, en[1], en[0]))
        tau_onceki = tau
        if not isaretli:
            break

    return [_yolu_kur(g, kaynaklar, son, arac, k, h, toplam) for k, h, toplam in sonuclar]


def _yolu_kur(g: Graf, kaynaklar: Dict[int, int], son: list, arac: list, k: int, h: int, toplam: int) -> Yolculuk:
    """Ebeveyn kayıtlarından geriye doğru etapları çıkarır; yürüme sürelerini ileri geçişte doldurur."""
    geri: List[tuple] = []
    r, s, kaynak = k, h, h
    zorunlu_arac = False
    while True:
        if not zorunlu_arac:
            while s not in son[r] and r > 0:
                r -= 1
            kayit = son[r].get(s)
        else:
            kayit = ("a",)
            zorunlu_arac = False
        if kayit is None or kayit[0] == "k":
            kaynak = s
            break
        if kayit[0] == "y":
            geri.append(("y", kayit[1], s, kayit[2]))
            s = kayit[1]
            if r > 0:
                zorunlu_arac = True               # yürümenin çıkış durağı o turda araçla iyileşmişti
            continue
        pi, satir, kayma, bin_sira, ind_sira, bin_kalkis, varis = arac[r][s]
        geri.append(("a", pi, satir, kayma, bin_sira, ind_sira, bin_kalkis, varis))
        s = g.paternler[pi].duraklar[bin_sira]
        r -= 1
    etaplar: List[Etap] = []
    simdi = kaynaklar.get(kaynak, 0)
    for e in reversed(geri):
        if e[0] == "y":
            _, a, b, sn = e
            etaplar.append(Etap("yurume", a, b, simdi, simdi + sn))
            simdi += sn
        else:
            _, pi, satir, kayma, bs, ds, bin_kalkis, varis = e
            p = g.paternler[pi]
            etaplar.append(Etap("arac", p.duraklar[bs], p.duraklar[ds], bin_kalkis, varis, patern=pi, hat=p.hat,
                                mod=p.mod, meta=p.meta[satir], bas_sira=bs, bit_sira=ds))
            simdi = varis
    arac_sayisi = sum(1 for e in etaplar if e.tip == "arac")
    return Yolculuk(aktarma=max(arac_sayisi - 1, 0), varis=toplam, kaynak=kaynak, hedef=h, etaplar=etaplar)

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
YAKIN_DURAK_SAYISI = 3        # "yakın duraklar" alternatifi için başlangıç/varışta en yakın durak sayısı


def yurume_sn(mesafe: float) -> int:
    return math.ceil(mesafe * YURUME_KATSAYISI / YURUME_HIZI_MS)


# --- Sıralama ve eleme (genelleştirilmiş maliyet; OpenTripPlanner'ın yaklaşımı) ---------------------------------
AKTARMA_CEZASI_SN = 480       # her aktarma, süreye eşdeğer ~8 dk "zahmet" ekler
YURUME_EK_KATSAYI = 0.5       # yürüme süresi 1,5 kat sayılır (süre + 0,5 × yürüme)
DEGER_ESIGI_SN = 300          # fazladan aktarma, varışı en az 5 dk öne çekmiyorsa seçenek elenir
BAN_SAYISI = 2                # çeşitlilik: en iyi rotanın ilk bu kadar hattı sırayla yasaklanıp yeniden aranır
SONRAKI_KALKIS_DK = (20,)     # çeşitlilik: bu kadar dk sonraki kalkışlar da aranır (farklı hat dizisi çıkarsa listelenir)


@dataclass
class Secenek:
    kalkis: int                       # ilk etabın başlangıcı, sn
    varis: int                        # son etabın bitişi, sn
    aktarma: int
    yuruyus_m: float
    etaplar: List[Etap] = field(default_factory=list)
    maliyet: int = 0                  # genelleştirilmiş maliyet (sn): sıralama için; sorgu anından varışa süre + cezalar
    yuruyus_sn: int = 0

    @property
    def sure(self) -> int:
        return self.varis - self.kalkis

    def imza(self) -> tuple:
        """Aynı hat dizisi = aynı seçenek (farklı durak/yürüyüşle yinelenmesin)."""
        araclar = tuple(e.hat for e in self.etaplar if e.tip == "arac")
        return araclar or ("yaya",)


def _maliyet(saat_sn: int, varis: int, aktarma: int, yuruyus_sn: int) -> int:
    return int((varis - saat_sn) + AKTARMA_CEZASI_SN * aktarma + YURUME_EK_KATSAYI * yuruyus_sn)


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
           aktarma_payi_sn: int = 60, erisim_sayisi: int = 40, cesitlilik: bool = True) -> List[Secenek]:
    """`bas`/`bit` (enlem, boylam). `saat_sn`: kalkış anı (gece yarısından sn). Seçenekler tercihe göre sıralı.

    Adaylar: (1) tüm yakın duraklarla arama, (2) yalnız en yakın duraklarla arama, (3) çeşitlilik: en iyi rotadaki hatlar sırayla
    yasaklanıp yeniden arama ve sonraki kalkış(lar). Sonra: aynı hat dizisinden en düşük maliyetli kalır, varışı belirgin
    öne çekmeyen fazladan aktarmalar elenir, tercihe göre (maliyet puanıyla) sıralanır."""
    if tercih not in TERCIHLER:
        raise ValueError(f"tercih {TERCIHLER} içinden olmalı: {tercih!r}")
    erisim = g.yakin_duraklar(bas[0], bas[1], max_yurume_m)[:erisim_sayisi]
    cikis = g.yakin_duraklar(bit[0], bit[1], max_yurume_m)[:erisim_sayisi]
    secenekler: List[Secenek] = []

    def ekle(kalkis, varis, aktarma, yuruyus_m, etaplar):
        yurusn = sum(e.varis - e.kalkis for e in etaplar if e.tip == "yurume")
        secenekler.append(Secenek(kalkis, varis, aktarma, yuruyus_m, etaplar, _maliyet(saat_sn, varis, aktarma, yurusn), yurusn))

    # yalnız yürüyüş (yakınsa)
    dogrudan_m = mesafe_m(bas[0], bas[1], bit[0], bit[1])
    if dogrudan_m * YURUME_KATSAYISI <= max_yurume_m * 1.5:
        sn = yurume_sn(dogrudan_m)
        ekle(saat_sn, saat_sn + sn, 0, dogrudan_m * YURUME_KATSAYISI, [Etap("yurume", -1, -1, saat_sn, saat_sn + sn)])

    def calistir(erisim_l, cikis_l, kalkis=None, yasak=None):
        kalkis = saat_sn if kalkis is None else kalkis
        kaynaklar, hedefler, giris_sn = {}, {}, {}
        for i, m in erisim_l:
            sn = yurume_sn(m)
            kaynaklar[i] = kalkis + sn
            giris_sn[i] = sn
        for i, m in cikis_l:
            hedefler[i] = yurume_sn(m)
        for y in raptor.ara(g, kaynaklar, hedefler, gun, max_aktarma=max_aktarma, izinli_modlar=izinli_modlar,
                            aktarma_payi_sn=aktarma_payi_sn, yasak_hatlar=yasak):
            if not any(e.tip == "arac" for e in y.etaplar):
                continue                      # araçsız (yalnız yürüyüş) sonuç: doğrudan yürüyüş zaten ayrı eklendi
            etaplar = list(y.etaplar)
            ilk = Etap("yurume", -1, y.kaynak, kalkis, kalkis + giris_sn[y.kaynak])
            son_t = etaplar[-1].varis if etaplar else ilk.varis
            son = Etap("yurume", y.hedef, -1, son_t, son_t + hedefler[y.hedef])
            tam = [ilk] + etaplar + [son]
            ekle(kalkis, son.varis, y.aktarma, _yuruyus_m(g, tam, bas, bit), tam)

    if erisim and cikis:
        calistir(erisim, cikis)
        # En erken varış bazen başlangıçtan uzak bir durağa yürütür (daha hızlı hat varyantı). Kullanıcı yakın durakları da
        # görsün: yalnızca en yakın birkaç durakla ikinci bir arama, sonuçlar birleştirilip yinelenenler elenir.
        if len(erisim) > YAKIN_DURAK_SAYISI or len(cikis) > YAKIN_DURAK_SAYISI:
            calistir(erisim[:YAKIN_DURAK_SAYISI], cikis[:YAKIN_DURAK_SAYISI])
        if cesitlilik:
            araclilar = [x for x in secenekler if any(e.tip == "arac" for e in x.etaplar)]
            if araclilar:
                en_iyi = min(araclilar, key=lambda x: (x.maliyet, x.varis))
                hatlar = []
                for e in en_iyi.etaplar:
                    if e.tip == "arac" and e.hat not in hatlar:
                        hatlar.append(e.hat)
                for h in hatlar[:BAN_SAYISI]:        # en iyi rotadaki hat olmadan ne var? (ör. otobüs yerine metro)
                    calistir(erisim, cikis, yasak={h})
                for dk in SONRAKI_KALKIS_DK:          # sonraki seferlerle (farklı hat dizisi çıkarsa listelenir)
                    calistir(erisim, cikis, kalkis=saat_sn + dk * 60)

    # aynı hat dizisinden en düşük maliyetli olan kalır
    en_iyi_imza = {}
    for x in secenekler:
        k = x.imza()
        if k not in en_iyi_imza or (x.maliyet, x.varis) < (en_iyi_imza[k].maliyet, en_iyi_imza[k].varis):
            en_iyi_imza[k] = x
    tekil = list(en_iyi_imza.values())
    # fazladan aktarma varışı en az DEGER_ESIGI_SN öne çekmiyorsa değmez (1 duraklık metrobüs hamlesi gibi)
    kalan = [x for x in tekil
             if not any(y.aktarma < x.aktarma and x.varis > y.varis - DEGER_ESIGI_SN for y in tekil)]
    anahtar = {"hizli": lambda x: (x.maliyet, x.varis),
               "az_aktarma": lambda x: (x.aktarma, x.maliyet),
               "az_yuruyus": lambda x: (x.yuruyus_m, x.maliyet)}[tercih]
    kalan.sort(key=anahtar)
    return kalan[:en_cok]


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


def durak_ozeti(g: Graf, metin: str, gun: Optional[int] = None, en_cok: int = 12,
                modlar: Optional[Iterable[str]] = None) -> str:
    """Ada göre durak arama (teşhis): hangi örüntüler/modlar uğruyor, kaç sefer, ilk/son kalkış, yürüme kenarı."""
    from app.gtfs.textfix import ascii_katla
    ara = ascii_katla(metin).lower()
    GUNLER = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
    mod_kumesi = set(modlar) if modlar else None
    bulunan = [i for i, ad in enumerate(g.durak_ad) if ara in ascii_katla(ad).lower()
               and (mod_kumesi is None or any(g.paternler[pi].mod in mod_kumesi for pi, _ in g.durak_paternleri[i]))]
    satir = [f"'{metin}' için {len(bulunan)} durak" + (f" (ilk {en_cok} gösteriliyor)" if len(bulunan) > en_cok else "")]
    for i in bulunan[:en_cok]:
        satir.append(f"{g.durak_id[i]}  {g.durak_ad[i]}  ({g.durak_lat[i]:.5f},{g.durak_lon[i]:.5f})  "
                     f"yürüme kenarı: {len(g.yurume[i])}")
        if not g.durak_paternleri[i]:
            satir.append("    (hiç seferi yok)")
        ilgili = [(pi, sira) for pi, sira in g.durak_paternleri[i]
                  if mod_kumesi is None or g.paternler[pi].mod in mod_kumesi]
        ilgili.sort(key=lambda x: (g.paternler[x[0]].mod == "bus", g.paternler[x[0]].mod, g.hat_kisa[g.paternler[x[0]].hat]))
        for pi, sira in ilgili[:20]:
            p = g.paternler[pi]
            gunluk = [sum(1 for m in p.maske if m >> d & 1) for d in range(7)]
            bu = ""
            if gun is not None and p.sefer_sayisi:
                kal = [p.kalkis[sira][r] for r in range(p.sefer_sayisi) if p.maske[r] >> gun & 1]
                if kal:
                    bu = f" | {GUNLER[gun]} ilk {saat_metni(min(kal))} son {saat_metni(max(kal))}"
            kural = ("" if p.biner[sira] else " [BİNİLMEZ]") + ("" if p.iner[sira] else " [İNİLMEZ]")
            satir.append(f"    {p.mod} {g.hat_kisa[p.hat]} sıra {sira + 1}/{len(p.duraklar)}{kural} "
                         f"seferler(Pzt..Paz): {'/'.join(map(str, gunluk))}{bu}")
        if len(ilgili) > 20:
            satir.append(f"    ... {len(ilgili) - 20} örüntü daha")
    return "\n".join(satir)

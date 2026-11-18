"""Planlama öncesi veri kuralları: aralıklı seferleri açma ve takvim.

Kaynak: docs/veri-kaynaklari.md ("Takvim kuralları", "Aralıklı seferler").
Bu modül veritabanına ya da dosyalara bağlı DEĞİLDİR; saf fonksiyonlardır.
"""
from typing import Iterable, List, Optional, Sequence, Tuple

GUN_ADLARI = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


# ---------------------------------------------------------------- aralıklı seferler
def expand_frequency_starts(start_secs: int, end_secs: int, headway_secs: int) -> List[int]:
    """[start, end) penceresindeki sefer BAŞLANGIÇ saatleri (saniye).

    GTFS kuralı: start'ta başlar, her `headway` saniyede bir tekrarlar, `end`'e ulaşınca durur
    (end dahil değil). Aralık pencereden uzunsa pencere başında TEK sefer çıkar
    (ör. 08:30-19:00 penceresi, 37800 sn aralık -> yalnızca 08:30).
    """
    if headway_secs <= 0:
        raise ValueError(f"headway_secs pozitif olmalı: {headway_secs}")
    if end_secs <= start_secs:
        return []
    return list(range(start_secs, end_secs, headway_secs))


def instantiate_trip_times(template: Sequence[Tuple[Optional[int], Optional[int]]],
                           start_secs: int) -> List[Tuple[Optional[int], Optional[int]]]:
    """Şablon seferin (varış, kalkış) saatlerini `start_secs`'te başlayacak şekilde kaydırır.

    Şablonun ilk durağının kalkışı (yoksa varışı) başlangıç kabul edilir; diğer duraklar bu
    başlangıca göre göreli kalır. Boş (None) saatler boş kalır.
    """
    if not template:
        return []
    ilk_varis, ilk_kalkis = template[0]
    taban = ilk_kalkis if ilk_kalkis is not None else ilk_varis
    if taban is None:
        raise ValueError("Şablonun ilk durağında hiç saat yok")
    kayma = start_secs - taban
    return [
        (None if v is None else v + kayma, None if k is None else k + kayma)
        for v, k in template
    ]


def expand_frequency_trips(template: Sequence[Tuple[Optional[int], Optional[int]]],
                           windows: Iterable[Tuple[int, int, int]]) -> List[List[Tuple[Optional[int], Optional[int]]]]:
    """Bir şablon sefer ve onun frequency pencerelerinden gerçek seferlerin saat listelerini üretir.

    windows: (start_secs, end_secs, headway_secs) üçlüleri. Aynı başlangıç saati birden çok
    pencerede çıkarsa tek kez sayılır (pencere uçlarında çift sefer olmasın).
    """
    baslangiclar = sorted({s for (b, e, h) in windows for s in expand_frequency_starts(b, e, h)})
    return [instantiate_trip_times(template, s) for s in baslangiclar]


# ---------------------------------------------------------------- takvim
def _gun_degeri(cal, ad):
    return bool(cal[ad]) if isinstance(cal, dict) else bool(getattr(cal, ad))


def has_any_weekday(cal) -> bool:
    """Hizmetin haftanın en az bir gününde çalışıp çalışmadığı."""
    return any(_gun_degeri(cal, g) for g in GUN_ADLARI)


def service_runs_on_weekday(cal, weekday: int) -> bool:
    """Hizmet verilen haftanın gününde (0=Pazartesi ... 6=Pazar) çalışır mı?

    Tarih aralıkları (start_date/end_date) BİLEREK dikkate alınmaz: kaynak beslemelerin
    çoğunda süresi dolmuş (31.12.2024) ve bugünün tarihiyle süzülürse hiçbir sefer kalmaz.
    Hiçbir günü işaretli olmayan hizmetler (ör. 2019 Ramazan gece seferleri) hiçbir gün çalışmaz.
    """
    if not 0 <= weekday <= 6:
        raise ValueError(f"weekday 0-6 olmalı: {weekday}")
    return _gun_degeri(cal, GUN_ADLARI[weekday])

"""Hat modunun (otobüs, metro, vapur ...) belirlenmesi.

Kaynaklardaki `route_type` güvenilir değil (docs/veri-kaynaklari.md):
  * Marmaray `1` (metro) olarak geliyor,
  * minibüs `9`, taksi dolmuş `10` gibi standart olmayan numaralar kullanıyor,
  * İETT'de metrobüs ayrı bir tip değil (hat koduyla ayrılacak).

Bu yüzden mod şu sırayla belirlenir:
  1. hat adı kuralları (`ModeRules.name_modes`, ör. metrobüs hat kodları),
  2. kurum kuralları (`ModeRules.agency_modes`, ör. TCDD -> rail),
  3. `route_type` (standart + genişletilmiş GTFS numaraları).
"""
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Tuple

MODES = (
    "bus", "metrobus", "minibus", "taxi",
    "metro", "tram", "funicular", "cable_car", "rail", "ferry", "other",
)

# Standart GTFS route_type + bu verilerde görülen standart dışı numaralar (9, 10)
_STANDART = {
    0: "tram", 1: "metro", 2: "rail", 3: "bus", 4: "ferry", 5: "tram",
    6: "cable_car", 7: "funicular", 9: "minibus", 10: "taxi", 11: "bus", 12: "rail",
}

# Genişletilmiş GTFS route_type aralıkları (başlangıç, bitiş, mod)
_GENISLETILMIS = (
    (100, 199, "rail"), (200, 299, "bus"), (400, 499, "metro"), (700, 799, "bus"),
    (800, 899, "bus"), (900, 999, "tram"), (1000, 1099, "ferry"), (1200, 1299, "ferry"),
    (1300, 1399, "cable_car"), (1400, 1499, "funicular"), (1500, 1599, "taxi"),
)


@dataclass(frozen=True)
class ModeRules:
    """Beslemeye özel mod kuralları.

    agency_modes: ham kurum kimliği -> mod (ör. {"4": "rail"}).
    name_modes:   (düzenli ifade, mod) listesi; hat KISA ADINA uygulanır, ilk eşleşen kazanır.
    """
    agency_modes: dict = field(default_factory=dict)
    name_modes: Tuple[Tuple[str, str], ...] = ()


def mode_from_route_type(route_type: Optional[int]) -> str:
    if route_type is None:
        return "other"
    if route_type in _STANDART:
        return _STANDART[route_type]
    for bas, bit, mod in _GENISLETILMIS:
        if bas <= route_type <= bit:
            return mod
    return "other"


def classify_mode(route_type: Optional[int], *, agency_id: Optional[str] = None,
                  short_name: Optional[str] = None, rules: Optional[ModeRules] = None) -> str:
    """Hattın normalleştirilmiş modunu döndürür (MODES içinden)."""
    rules = rules or ModeRules()
    ad = (short_name or "").strip()
    for kalip, mod in rules.name_modes:
        if re.search(kalip, ad):
            return mod
    if agency_id is not None and str(agency_id) in rules.agency_modes:
        return rules.agency_modes[str(agency_id)]
    return mode_from_route_type(route_type)


def validate_modes(modes: Iterable[str]) -> None:
    kotu = [m for m in modes if m not in MODES]
    if kotu:
        raise ValueError(f"Bilinmeyen mod(lar): {kotu}. Geçerli modlar: {MODES}")

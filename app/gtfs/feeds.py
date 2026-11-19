"""Besleme (veri kaynağı) ayarları.

Bir besleme: kimliği, kodlama/bozulma düzeltmeleri, mod kuralları ve hangi hatların
planlamadan dışarıda bırakılacağı. Önceden tanımlı ayarlar, `docs/veri-kaynaklari.md`'deki
araştırmaya dayanır.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from app.gtfs.modes import ModeRules, validate_modes
from app.gtfs.textfix import ascii_katla


@dataclass(frozen=True)
class FeedConfig:
    feed_id: str                                   # kimlik öneki: "iett", "ibb", ...
    name: str
    data_date: Optional[date] = None               # verinin KENDİ tarihi (biliniyorsa)
    source_note: Optional[str] = None
    fix_mojibake: bool = False                     # İETT'de isimlerde çift kodlama bozulması var
    mode_rules: ModeRules = field(default_factory=ModeRules)
    exclude_modes: frozenset = frozenset()         # bu modlardaki hatlar yüklenmez
    exclude_agencies: frozenset = frozenset()      # bu (ham) kurum kimliklerinin hatları yüklenmez
    # Normalleştirilmiş hat sözlüğü ({"short_name", "long_name", "mode", ...}) alıp True dönerse
    # hat yüklenmez (ör. turistik vapur seferleri).
    exclude_route: Optional[Callable[[dict], bool]] = None

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9_]{1,32}", self.feed_id):
            raise ValueError(f"feed_id küçük harf/rakam/alt çizgi olmalı: {self.feed_id!r}")
        validate_modes(self.exclude_modes)
        validate_modes(m for _, m in self.mode_rules.name_modes)
        validate_modes(self.mode_rules.agency_modes.values())

    def prefixed(self, ham_id: str) -> str:
        """Ham kimliğe kaynak öneki ekler: "292235" -> "iett:292235"."""
        return f"{self.feed_id}:{ham_id}"


# Turistik / özel vapur seferleri günlük yolculuk planına girmemeli (docs/veri-kaynaklari.md).
_TURISTIK = re.compile(r"BOGAZ(A|DAN)\s+(GIDIS|GELIS)|\bTURU\b|FESTIVAL")


def _turistik_vapur(hat: dict) -> bool:
    if hat.get("mode") != "ferry":
        return False
    metin = ascii_katla(f"{hat.get('short_name', '')} {hat.get('long_name', '')}")
    return bool(_TURISTIK.search(metin))


# İETT: otobüs + metrobüs. Tüm hatlar route_type=3; metrobüs hatları kısa adla ayrılır:
# gerçek veride "34" ile başlayan tüm hatlar metrobüstür (34, 34A, 34AS, 34B, 34BZ, 34C, 34G, 34T,
# 34U, 34Z) ve bu kalıba uyan başka hat yoktur. Adında "METROBÜS" geçen yüzlerce hat metrobüse
# bağlanan normal otobüslerdir. route_type'ı boş olan satırlar bozuk (sütunları kaymış) satırlardır
# ve yüklenmez. İsimlerde UTF-8 çift kodlama bozulması var.
IETT = FeedConfig(
    feed_id="iett",
    name="İETT GTFS (İBB Açık Veri Portalı)",
    data_date=date(2026, 4, 21),
    source_note="iett-gtfs-verisi; tarih portaldaki son güncelleme tarihidir.",
    fix_mojibake=True,
    mode_rules=ModeRules(name_modes=((r"^34[A-Z]*$", "metrobus"),)),
    exclude_modes=frozenset({"other"}),
)

# Çok modlu besleme: Metro İstanbul, Marmaray (TCDD), Şehir Hatları, İDO, Turyol, Dentur,
# minibüs, taksi dolmuş. Kodlama Windows-1254 (reader otomatik algılar).
# TCDD (agency 4) hatları YÜKLENMEZ: 2019 tarihli Marmaray verisi bugünkü hizmetle uyuşmuyor
# (Halkalı-Bahçeşehir, Söğütlüçeşme-Zeytinburnu kalıpları yok, Ataköy-Pendik kalıbı eksik);
# Marmaray, TCDD'nin resmi tarifesinden elle tanımlanır (MARMARAY, data/marmaray.json).
# Minibüs/taksi dolmuş ve tipi bilinmeyen hatlar ilk aşamada yüklenmez.
IBB_MULTIMODAL = FeedConfig(
    feed_id="ibb",
    name="İBB Toplu Ulaşım GTFS (çok modlu, 2018-2020)",
    source_note=(
        "public-transport-gtfs-data; güncellenmeyecek. Veri tarihleri: Metro İstanbul 09.07.2020, "
        "TCDD 16.10.2019 (yüklenmez, bkz. marmaray beslemesi), Şehir Hatları 25.09.2019, İDO 16.10.2019, "
        "Turyol 02.10.2019, Dentur 30.10.2019, Minibüs 20.02.2018, Taksi dolmuş 16.01.2018."
    ),
    mode_rules=ModeRules(agency_modes={"4": "rail"}),
    exclude_modes=frozenset({"minibus", "taxi", "other"}),
    exclude_agencies=frozenset({"4"}),
    exclude_route=_turistik_vapur,
)

# Marmaray: elle tanımlı (kurallardan üretilir, bkz. app/gtfs/manual.py). Veri tarihi: TCDD tarifesi.
MARMARAY = FeedConfig(
    feed_id="marmaray",
    name="Marmaray (TCDD, elle tanımlı)",
    data_date=date(2026, 5, 5),
    source_note=(
        "TCDD Taşımacılık Marmaray Günlük Tren Saatleri, 5 Mayıs 2026. Çizelge kurallardan üretilir "
        "(data/marmaray.json); istasyon konumları ve süreleri İBB çok modlu GTFS'ten (2019)."
    ),
)

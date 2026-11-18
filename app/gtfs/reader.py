"""GTFS dosyalarını (CSV) güvenle okuma.

Gerçek verideki sorunlar (docs/veri-kaynaklari.md):
  * kodlama: İETT UTF-8 (ama isimlerde çift kodlama bozulması), çok modlu besleme Windows-1254,
  * ayraç: İETT ';' ve çok modlu besleme ',',
  * İETT koordinatları bozuk ('410.191.700.005.564'),
  * saatler 24'ü aşabilir ('25:20:00').
"""
import codecs
import csv
import os
from datetime import date
from typing import Dict, Iterator, Optional

from app.gtfs.textfix import _koordinat_duzelt, _mojibake_duzelt

TURKCE_KODLAMA = "cp1254"      # UTF-8 olmayan dosyalar için yedek (Windows-1254)
_BLOK = 4 * 1024 * 1024


def detect_encoding(path: str) -> str:
    """Dosya UTF-8 (BOM'lu olabilir) olarak çözülebiliyorsa 'utf-8-sig', değilse 'cp1254'."""
    cozucu = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
    try:
        with open(path, "rb") as f:
            while True:
                blok = f.read(_BLOK)
                if not blok:
                    cozucu.decode(b"", final=True)
                    return "utf-8-sig"
                cozucu.decode(blok)
    except UnicodeDecodeError:
        return TURKCE_KODLAMA


def detect_delimiter(path: str, encoding: str) -> str:
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        ilk = f.readline()
    return ";" if ilk.count(";") > ilk.count(",") else ","


def iter_rows(path: str, *, encoding: Optional[str] = None) -> Iterator[Dict[str, str]]:
    """CSV satırlarını sözlük olarak akıtır. Başlıklar ve değerler kırpılır; dosya yoksa boş döner."""
    if not os.path.exists(path):
        return
    enc = encoding or detect_encoding(path)
    delim = detect_delimiter(path, enc)
    with open(path, encoding=enc, errors="replace", newline="") as f:
        okuyucu = csv.DictReader(f, delimiter=delim)
        okuyucu.fieldnames = [(a or "").strip().lstrip("﻿") for a in (okuyucu.fieldnames or [])]
        for satir in okuyucu:
            yield {k: (v.strip() if isinstance(v, str) else "") for k, v in satir.items() if k}


# ---------------------------------------------------------------- değer çözümleme
def parse_time(deger: Optional[str]) -> Optional[int]:
    """'H:MM:SS' -> gece yarısından beri saniye. 24 saati aşabilir ('25:20:00' = 91200). Boş -> None."""
    if not deger or not deger.strip():
        return None
    parcalar = deger.strip().split(":")
    if len(parcalar) not in (2, 3):
        return None
    try:
        sayilar = [int(p) for p in parcalar]
    except ValueError:
        return None
    s, d = sayilar[0], sayilar[1]
    sn = sayilar[2] if len(sayilar) == 3 else 0
    if s < 0 or not (0 <= d < 60) or not (0 <= sn < 60):
        return None
    return s * 3600 + d * 60 + sn


def parse_date(deger: Optional[str]) -> Optional[date]:
    """'20221231' -> date. Geçersiz/boş -> None."""
    if not deger or len(deger.strip()) != 8:
        return None
    try:
        s = deger.strip()
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None


def parse_int(deger: Optional[str], varsayilan: Optional[int] = None) -> Optional[int]:
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return varsayilan


def parse_coord(ham: Optional[str], *, sinir: float) -> Optional[float]:
    """Koordinatı çözer. Normal bir sayıysa ve |değer| <= sinir ise aynen alınır; değilse
    İETT'deki bozuk biçim ('410.191.700.005.564') düzeltilir. Çözülemezse None."""
    if ham is None or not str(ham).strip():
        return None
    if "e" in str(ham).lower():
        # "4,12E+14" gibi bilimsel gösterim Excel bozulmasıdır; hassasiyet kaybolmuş, güvenilmez
        return None
    try:
        v = float(str(ham).strip().replace(",", "."))
        if abs(v) <= sinir:
            return v
    except ValueError:
        pass
    v = _koordinat_duzelt(ham)
    if v is not None and abs(v) <= sinir:
        return v
    return None


def parse_lat(ham):
    return parse_coord(ham, sinir=90.0)


def parse_lon(ham):
    return parse_coord(ham, sinir=180.0)


def temizle_metin(metin: Optional[str], *, fix_mojibake: bool) -> str:
    metin = (metin or "").strip()
    if fix_mojibake:
        metin = _mojibake_duzelt(metin)
    return " ".join(metin.split())     # art arda boşlukları tek boşluğa indir

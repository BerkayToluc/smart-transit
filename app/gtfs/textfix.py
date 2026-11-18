"""GTFS metin / koordinat / ayraç temizleme yardımcıları.

`app/gtfs_admin.py` içinden taşındı (davranış değişmeden); hem yönetici uç noktaları hem de
`app/gtfs/reader.py` aynı kodu kullanır. Eski adlar `app.gtfs_admin` ve `main` üzerinden de
erişilebilir kalır.
"""

# =====================================================================
# 🔤 METİN/KOORDİNAT TEMİZLEME YARDIMCILARI (TEK VE GÜNCEL SÜRÜM)
# =====================================================================

_MOJIBAKE_ESLESTIRME = [
    ("Ã‡", "Ç"), ("Ã§", "ç"),
    ("Äž", "Ğ"), ("ÄŸ", "ğ"),
    ("Ä±", "ı"), ("Ä°", "İ"),
    ("Ã–", "Ö"), ("Ã¶", "ö"),
    ("Åž", "Ş"), ("ÅŸ", "ş"),
    ("Ãœ", "Ü"), ("Ã¼", "ü"),
    ("Ã¢", "â"), ("Ã®", "î"), ("Ã»", "û"),
]


def _mojibake_duzelt(metin: str) -> str:
    """
    routes.csv / trips.csv / stops.csv içindeki isimlerdeki bozuk karakterleri
    düzeltir. Bilinen bozuk-karakter KALIPLARINI tek tek değiştirir (encode/decode
    DEĞİL) — böylece bir karakter kaynakta zaten hasarlıysa bile diğerleri etkilenmez.
    """
    if not metin:
        return metin
    for bozuk, dogru in _MOJIBAKE_ESLESTIRME:
        metin = metin.replace(bozuk, dogru)
    # 🩹 Partneri kaynak veride ZATEN KAYBOLMUŞ, tek başına "yetim" kalmış "Ä"
    # karakterleri için en olası aday "Ğ" (Türkçe'de en sık rastlanan durum).
    metin = metin.replace("Ä", "Ğ")
    return metin


def _koordinat_duzelt(ham):
    """
    stops.csv'deki '410.191.700.005.564' tipi bozulmuş sayıları gerçek
    koordinata çevirir: tüm noktaları atıp rakamları birleştiriyoruz, ilk 2
    rakam tam kısım (41 ya da 28), geri kalanı ondalık kısım oluyor.
    """
    if not ham:
        return None
    s = str(ham).strip().replace(",", ".")
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 3:
        return None
    tam = digits[:2]
    ondalik = digits[2:]
    try:
        return float(f"{tam}.{ondalik}")
    except ValueError:
        return None


def _ayrac_tespit_et(dosya_yolu: str) -> str:
    """CSV'nin ',' mi ';' mi ile ayrıldığını ilk satıra bakarak otomatik tespit eder."""
    with open(dosya_yolu, encoding="utf-8-sig") as f:
        ilk_satir = f.readline()
    return ";" if ilk_satir.count(";") > ilk_satir.count(",") else ","


_ASCII_KATLA = str.maketrans({
    "İ": "I", "ı": "I", "i": "I", "Ş": "S", "ş": "S", "Ğ": "G", "ğ": "G",
    "Ü": "U", "ü": "U", "Ö": "O", "ö": "O", "Ç": "C", "ç": "C",
})


def ascii_katla(metin: str) -> str:
    """Büyük harfe ve ASCII'ye çevirir (Türkçe karakterler katlanır): "Boğaza Gidiş" -> "BOGAZA GIDIS".
    İ/ı sorunlarına (Python'ın 'İ'.lower() davranışı) takılmadan ad eşleştirmek için."""
    return (metin or "").translate(_ASCII_KATLA).upper()

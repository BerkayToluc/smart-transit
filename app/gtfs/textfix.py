"""GTFS metin / koordinat / ayraç temizleme yardımcıları.

`app/gtfs_admin.py` içinden taşındı (davranış değişmeden); hem yönetici uç noktaları hem de
`app/gtfs/reader.py` aynı kodu kullanır. Eski adlar `app.gtfs_admin` ve `main` üzerinden de
erişilebilir kalır.
"""

# =====================================================================
# 🔤 METİN/KOORDİNAT TEMİZLEME YARDIMCILARI (TEK VE GÜNCEL SÜRÜM)
# =====================================================================

def _mojibake_tablosu():
    """Türkçe harflerin UTF-8 baytlarının YANLIŞ okunmuş hallerini üretir.

    Kaynak verideki bozulma iki türlü: Windows-1252 okuması ("Åž" = Ş) ve Latin-1 okuması
    ("Å\x9e" = Ş; 0x80-0x9F baytları kontrol karakteri olarak kalır). İkisi de aynı dosyada
    karışık görülebiliyor, o yüzden ikisi için de eşleme üretilir.
    """
    ciftler = []
    for harf in "ÇçĞğİıÖöŞşÜüâîû":
        for kodlama in ("cp1252", "latin-1"):
            try:
                bozuk = harf.encode("utf-8").decode(kodlama)
            except UnicodeDecodeError:
                continue
            if bozuk != harf and (bozuk, harf) not in ciftler:
                ciftler.append((bozuk, harf))
    return ciftler


_MOJIBAKE_ESLESTIRME = _mojibake_tablosu()


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
    # Bozuk "bölünmez boşluk" (C2 A0): "Â\xa0" -> boşluk
    metin = metin.replace("Â\xa0", " ").replace("\xa0", " ")
    # 🩹 Partneri kaynak veride ZATEN KAYBOLMUŞ, tek başına "yetim" kalmış karakterler:
    # "Ä" için en olası aday "Ğ", "Å" için "Ş" (gerçek veride hepsi Ş: SÖĞÜTLÜÇEŞME, YEŞİLTEPE ...).
    metin = metin.replace("Ä", "Ğ").replace("Å", "Ş")
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

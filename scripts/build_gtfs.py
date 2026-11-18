"""GTFS verisini indirir, veritabanına yükler ve rapor verir.

Proje KÖK klasöründen çalıştırın (portal bulut sunucularından açılmaz, yerel makinede çalıştırın):

    python scripts/build_gtfs.py indir iett ibb                 # gtfs_data/ altına indir
    python scripts/build_gtfs.py yukle iett --hedef sqlite:///gtfs_data/gtfs.db
    python scripts/build_gtfs.py rapor iett --hedef sqlite:///gtfs_data/gtfs.db
    python scripts/build_gtfs.py hepsi iett ibb --hedef sqlite:///gtfs_data/gtfs.db

Beslemeler: iett (otobüs + metrobüs), ibb (çok modlu: metro, tramvay, vapur, Marmaray portal verisi).

--hedef verilmezse .env'deki DATABASE_URL (Neon) kullanılır ve `--evet` istenir: İETT'nin
durak saatleri yaklaşık bir milyon satırdır, ücretsiz Neon planının yer sınırına yaklaşabilir.
Güvenli yol: önce yerel bir SQLite dosyasına yükleyip `rapor` ile boyutu görmek.
"""
import argparse
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)


def _maskele(url: str) -> str:
    """Bağlantı adresindeki parolayı gizler."""
    if "@" in url and "://" in url:
        sema, geri = url.split("://", 1)
        kimlik, ev = geri.rsplit("@", 1)
        return f"{sema}://{kimlik.split(':')[0]}:****@{ev}"
    return url


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("komut", choices=["indir", "yukle", "rapor", "hepsi"])
    ap.add_argument("beslemeler", nargs="+", help="iett, ibb")
    ap.add_argument("--hedef", help="veritabanı adresi (örn. sqlite:///gtfs_data/gtfs.db); yoksa .env DATABASE_URL")
    ap.add_argument("--klasor", help="yerel GTFS klasörü (yalnızca tek besleme verildiğinde)")
    ap.add_argument("--evet", action="store_true", help="--hedef olmadan (.env'deki canlı veritabanına) yüklemeyi onayla")
    a = ap.parse_args(argv)

    if a.hedef:
        os.environ["DATABASE_URL"] = a.hedef          # app.db içe aktarılmadan ÖNCE
        if a.hedef.startswith("sqlite:///"):
            klasor = os.path.dirname(a.hedef[len("sqlite:///"):])
            if klasor:
                os.makedirs(klasor, exist_ok=True)

    from app.gtfs import build                          # noqa: E402  (DATABASE_URL ayarlandıktan sonra)
    bilinmeyen = [b for b in a.beslemeler if b not in build.BESLEMELER]
    if bilinmeyen:
        ap.error(f"bilinmeyen besleme(ler): {bilinmeyen}; geçerli: {sorted(build.BESLEMELER)}")
    if a.klasor and len(a.beslemeler) != 1:
        ap.error("--klasor yalnızca tek besleme verildiğinde kullanılabilir")

    klasor_of = lambda b: a.klasor or build.BESLEMELER[b].klasor

    if a.komut in ("indir", "hepsi"):
        for b in a.beslemeler:
            print(f"== {b}: portaldan indiriliyor -> {klasor_of(b)}")
            build.indir(b, klasor_of(b))

    if a.komut in ("yukle", "hepsi", "rapor"):
        from app.db import SessionLocal, engine
        from app.db import Base
        from app.gtfs import models  # noqa: F401
        hedef_adi = _maskele(str(engine.url))
        if a.komut != "rapor" and not a.hedef and not a.evet:
            print(f"Hedef: {hedef_adi}\n"
                  "Bu, .env'deki (canlı) veritabanıdır ve İETT yüklemesi çok büyük olabilir.\n"
                  "Önce --hedef sqlite:///gtfs_data/gtfs.db ile yerelde deneyin; "
                  "canlı veritabanına yüklemek için --evet ekleyin.")
            return 2
        # gtfs_* tabloları (boş tablolar uygulama açılışında da oluşur; idempotent)
        gtfs_tablolari = [t for t in Base.metadata.sorted_tables if t.name.startswith("gtfs_")]
        Base.metadata.create_all(bind=engine, tables=gtfs_tablolari)
        with SessionLocal() as oturum:
            if a.komut in ("yukle", "hepsi"):
                from app.gtfs.loader import load_feed
                for b in a.beslemeler:
                    print(f"== {b}: yükleniyor -> {hedef_adi}")
                    ozet = load_feed(oturum, klasor_of(b), build.BESLEMELER[b].config,
                                     progress=lambda m: print("  " + m))
                    print("  özet:", ozet)
            for b in a.beslemeler:
                print(build.rapor_metni(build.rapor(oturum, build.BESLEMELER[b].config.feed_id)))
            boyutlar = build.boyut_bilgisi(oturum)
            if boyutlar:
                print("Boyut:", ", ".join(f"{ad}={b / 1048576:.1f} MB" for ad, b in sorted(boyutlar.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

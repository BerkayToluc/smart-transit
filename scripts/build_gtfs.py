"""GTFS verisini indirir, veritabanına yükler ve rapor verir.

Proje KÖK klasöründen çalıştırın (portal bulut sunucularından açılmaz, yerel makinede çalıştırın):

    python scripts/build_gtfs.py indir iett ibb                 # gtfs_data/ altına indir
    python scripts/build_gtfs.py yukle iett --hedef sqlite:///gtfs_data/gtfs.db
    python scripts/build_gtfs.py rapor iett --hedef sqlite:///gtfs_data/gtfs.db
    python scripts/build_gtfs.py hepsi iett ibb marmaray --hedef sqlite:///gtfs_data/gtfs.db
    python scripts/build_gtfs.py hatlar ibb marmaray --hedef sqlite:///gtfs_data/gtfs.db   # hat/süre özeti

Beslemeler: iett (otobüs + metrobüs), ibb (çok modlu: metro, tramvay, füniküler; 2019 vapurları yüklenmez),
marmaray (elle tanımlı: data/marmaray.json'daki kurallardan üretilir, indirme gerekmez),
vapur (elle tanımlı: data/vapur.json, Şehir Hatları kış tarifesi; indirme gerekmez).
`hatlar`: her hattın ilk/son durağı, durak sayısı ve yolculuk süresi (veriyi doğrulamak için);
`--modlar metro tram ...` ile süzülür (varsayılan: otobüs ve minibüs dışındakiler).
`aktarma`: yüklü tüm beslemelerin duraklarından yürüme kenarları (≤150 m; farklı beslemelerin istasyon türü durakları için ≤600 m) ve istasyon kümeleri üretir
(`python scripts/build_gtfs.py aktarma --hedef ...`); beslemeler yüklendikten SONRA ve her yeniden yüklemeden sonra çalıştırılır.
`rota`: iki koordinat arası aktarmalı rota (`--nereden 40.99,29.02 --nereye 41.04,28.98 --saat 08:30 --gun 1`);
grafı ilk seferde kurar ve `gtfs_data/graf.pkl`e yazar, sonraki sorgular hızlı açılır.
`saatler`: hatların gerçek sefer saatleri (yön ve gün tipine göre: sefer sayısı, ilk/son sefer, en sık aralık,
süre). `--hat KDK-EMN ...` ya da `--modlar ferry` (varsayılan) ve `--en-az-sefer 20` ile süzülür.

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


def _rota(a, oturum) -> int:
    """Örnek rota sorgusu (doğrulama ve süre ölçümü için)."""
    import time
    from datetime import datetime
    if not a.nereden or not a.nereye:
        print("--nereden ve --nereye gerekli (\"enlem,boylam\")")
        return 2
    bas = tuple(float(x) for x in a.nereden.split(","))
    bit = tuple(float(x) for x in a.nereye.split(","))
    simdi = datetime.now()
    gun = a.gun if a.gun is not None else simdi.weekday()
    saat = a.saat or simdi.strftime("%H:%M")
    sa, dk = (int(x) for x in saat.split(":")[:2])
    from app.routing import graph, plan
    t0 = time.time()
    g = graph.yukle(oturum, a.graf, log=lambda m: print("  " + m))
    t1 = time.time()
    print(f"Graf hazır: {g.durak_sayisi} durak, {len(g.paternler)} örüntü, {g.sefer_sayisi()} sefer ({t1 - t0:.1f} sn)")
    sonuc = plan.planla(g, bas, bit, gun, sa * 3600 + dk * 60, izinli_modlar=a.modlar, max_aktarma=a.max_aktarma,
                        max_yurume_m=a.max_yurume, tercih=a.tercih)
    t2 = time.time()
    if not sonuc:
        print("Rota bulunamadı.")
    for i, s in enumerate(sonuc, 1):
        print(plan.secenek_metni(g, s, i))
    print(f"Sorgu süresi: {(t2 - t1) * 1000:.0f} ms  (gün={gun}, saat={saat})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("komut", choices=["indir", "yukle", "rapor", "hepsi", "hatlar", "saatler", "aktarma", "rota"])
    ap.add_argument("beslemeler", nargs="*", help="iett, ibb, marmaray, vapur (`aktarma` ve `rota` için gerekmez)")
    ap.add_argument("--nereden", help="`rota`: başlangıç \"enlem,boylam\" (örn. 40.9903,29.0260)")
    ap.add_argument("--nereye", help="`rota`: varış \"enlem,boylam\"")
    ap.add_argument("--saat", help="`rota`: kalkış saati SS:DD (varsayılan: şimdi)")
    ap.add_argument("--gun", type=int, help="`rota`: 0=Pazartesi ... 6=Pazar (varsayılan: bugün)")
    ap.add_argument("--max-aktarma", type=int, default=3, help="`rota`: en çok aktarma")
    ap.add_argument("--max-yurume", type=float, default=800.0, help="`rota`: başlangıç/varışta en çok yürüme (m)")
    ap.add_argument("--tercih", default="hizli", help="`rota`: hizli | az_aktarma | az_yuruyus")
    ap.add_argument("--graf", default=os.path.join("gtfs_data", "graf.pkl"), help="`rota`: graf önbellek dosyası")
    ap.add_argument("--yaricap", type=float, default=150.0, help="`aktarma`: yürüme kenarı için en çok mesafe (m)")
    ap.add_argument("--istasyon-yaricap", type=float, default=600.0,
                    help="`aktarma`: farklı beslemelerin istasyon türü durakları (metro, Marmaray, iskele) için en çok mesafe (m)")
    ap.add_argument("--hedef", help="veritabanı adresi (örn. sqlite:///gtfs_data/gtfs.db); yoksa .env DATABASE_URL")
    ap.add_argument("--klasor", help="yerel GTFS klasörü (yalnızca tek besleme verildiğinde)")
    ap.add_argument("--modlar", nargs="+", help="`hatlar` için mod süzgeci (örn. metro tram ferry)")
    ap.add_argument("--hat", nargs="+", help="`saatler` için hat kısa adları (örn. KDK-EMN KRK-KDK)")
    ap.add_argument("--en-az-sefer", type=int, default=0, help="`saatler`: bundan az seferli hatları gösterme")
    ap.add_argument("--evet", action="store_true", help="--hedef olmadan (.env'deki canlı veritabanına) yüklemeyi onayla")
    a = ap.parse_args(argv)

    if a.hedef:
        os.environ["DATABASE_URL"] = a.hedef          # app.db içe aktarılmadan ÖNCE
        if a.hedef.startswith("sqlite:///"):
            klasor = os.path.dirname(a.hedef[len("sqlite:///"):])
            if klasor:
                os.makedirs(klasor, exist_ok=True)

    from app.gtfs import build                          # noqa: E402  (DATABASE_URL ayarlandıktan sonra)
    if a.komut not in ("aktarma", "rota") and not a.beslemeler:
        ap.error("en az bir besleme adı gerekli")
    bilinmeyen = [b for b in a.beslemeler if b not in build.BESLEMELER]
    if bilinmeyen:
        ap.error(f"bilinmeyen besleme(ler): {bilinmeyen}; geçerli: {sorted(build.BESLEMELER)}")
    if a.klasor and len(a.beslemeler) != 1:
        ap.error("--klasor yalnızca tek besleme verildiğinde kullanılabilir")

    klasor_of = lambda b: a.klasor or build.BESLEMELER[b].klasor

    if a.komut in ("indir", "hepsi"):
        for b in a.beslemeler:
            if build.BESLEMELER[b].manuel:     # elle tanımlı besleme: indirme yok, kurallardan üretilir
                print(f"== {b}: kurallardan GTFS dosyaları üretiliyor -> {klasor_of(b)}")
                build.manuel_uret(b, klasor_of(b))
            else:
                print(f"== {b}: portaldan indiriliyor -> {klasor_of(b)}")
                build.indir(b, klasor_of(b))

    if a.komut == "yukle":
        for b in a.beslemeler:                 # `yukle` indirme yapmaz; elle tanımlı dosyalar yine de güncel üretilir
            if build.BESLEMELER[b].manuel:
                print(f"== {b}: kurallardan GTFS dosyaları üretiliyor -> {klasor_of(b)}")
                build.manuel_uret(b, klasor_of(b))

    if a.komut in ("yukle", "hepsi", "rapor", "hatlar", "saatler", "aktarma", "rota"):
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
            if a.komut == "rota":
                return _rota(a, oturum)
            if a.komut == "aktarma":
                from app.gtfs import transfers
                print(f"== aktarma noktaları üretiliyor -> {hedef_adi} (yürüme ≤ {a.yaricap:g} m; istasyonlar arası ≤ {a.istasyon_yaricap:g} m)")
                ozet = transfers.uret(oturum, yaricap_m=a.yaricap, istasyon_yaricap_m=a.istasyon_yaricap, log=lambda m: print("  " + m))
                print(transfers.ozet_metni(ozet))
                print("Bilinen büyük aktarma noktaları:")
                print(transfers.nokta_raporu_metni(transfers.bilinen_noktalar(oturum)))
                return 0
            if a.komut == "saatler":
                modlar = a.modlar or (None if a.hat else ["ferry"])
                for b in a.beslemeler:
                    fid = build.BESLEMELER[b].config.feed_id
                    print(f"[{fid}] sefer saatleri:")
                    print(build.sefer_saatleri_metni(build.sefer_saatleri(
                        oturum, fid, hatlar=a.hat, modlar=modlar, en_az_sefer=a.en_az_sefer)))
                return 0
            if a.komut == "hatlar":
                varsayilan = [m for m in ("metrobus", "metro", "tram", "funicular", "cable_car", "rail", "ferry")]
                for b in a.beslemeler:
                    fid = build.BESLEMELER[b].config.feed_id
                    print(f"[{fid}] hatlar:")
                    print(build.hat_ozeti_metni(build.hat_ozeti(oturum, fid, a.modlar or varsayilan)))
                return 0
            for b in a.beslemeler:
                print(build.rapor_metni(build.rapor(oturum, build.BESLEMELER[b].config.feed_id)))
            boyutlar = build.boyut_bilgisi(oturum)
            if boyutlar:
                print("Boyut:", ", ".join(f"{ad}={b / 1048576:.1f} MB" for ad, b in sorted(boyutlar.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

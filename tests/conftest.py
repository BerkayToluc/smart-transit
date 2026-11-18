"""Test ortamı.

Gerçek Neon veritabanına ve İETT servisine ASLA dokunulmaz:
  * DATABASE_URL, main import edilmeden ÖNCE geçici bir SQLite dosyasına yönlendirilir.
  * İETT SOAP çağrısı, requests.post seviyesinde taklit edilir (bu sayede main.py
    modüllere bölündüğünde de testler aynen çalışır).
"""
import os
import re
import tempfile
from types import SimpleNamespace
from xml.sax.saxutils import escape
import json

# --- main import edilmeden önce ayarlanmalı -----------------------------------
_TEST_DB_DIZINI = tempfile.mkdtemp(prefix="smarttransit-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TEST_DB_DIZINI, 'test.db')}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from sqlalchemy import event  # noqa: E402


# SQLite varsayılan olarak yabancı anahtarları denetlemez; PostgreSQL (Neon) denetler.
# Yükleme sırası hatalarını testte yakalamak için SQLite'ta da açıyoruz.
@event.listens_for(main.engine, "connect")
def _sqlite_fk_ac(dbapi_baglanti, _kayit):
    dbapi_baglanti.execute("PRAGMA foreign_keys=ON")


# --- Sahte İETT servisi -------------------------------------------------------
# hat kodu -> araç listesi. Testler kendi hat kodlarını kullanır (önbellek çakışmasın).
IETT_ARACLARI: dict[str, list[dict]] = {}
# True olursa İETT "erişilemiyor" gibi davranır.
IETT_COKUK = {"acik": False}


def _sahte_requests_post(url, data=None, headers=None, **kwargs):
    if IETT_COKUK["acik"]:
        raise ConnectionError("İETT erişilemiyor (test)")
    eslesme = re.search(r"<HatKodu>(.*?)</HatKodu>", data or "")
    hat_kodu = eslesme.group(1) if eslesme else ""
    araclar = IETT_ARACLARI.get(hat_kodu, [])
    govde = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        '<GetHatOtoKonum_jsonResponse xmlns="http://tempuri.org/">'
        f"<GetHatOtoKonum_jsonResult>{escape(json.dumps(araclar))}</GetHatOtoKonum_jsonResult>"
        "</GetHatOtoKonum_jsonResponse></soap:Body></soap:Envelope>"
    )
    return SimpleNamespace(text=govde, raise_for_status=lambda: None)


@pytest.fixture(autouse=True)
def sahte_iett(monkeypatch):
    IETT_ARACLARI.clear()
    IETT_COKUK["acik"] = False
    monkeypatch.setattr("requests.post", _sahte_requests_post)
    yield IETT_ARACLARI


@pytest.fixture(scope="session")
def client():
    # with bloğu uygulamanın startup olayını çalıştırır (tabloları oluşturur)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="session")
def db():
    oturum = main.SessionLocal()
    try:
        yield oturum
    finally:
        oturum.close()


# --- Örnek veri: T100 hattı ---------------------------------------------------
# İki yön, her birinde 20 durak, aynı doğru üzerinde (boylam 29.0, enlem 41.00 -> 41.19,
# durak aralığı ~1.11 km).  ETA mantığı "son 15 durak adı" ile yön eşleştirdiği için
# 20 durak gerekli; yön adları son duraklarda geçiyor.
KUZEY = "KUZEYSON"   # güney -> kuzey yönü
GUNEY = "GUNEYSON"   # kuzey -> güney yönü
ENLEM_BASI = 41.00
ADIM = 0.01


@pytest.fixture(scope="session")
def ornek_hat(client, db):
    hat = main.Hat(hat_kodu="T100", hat_adi="TEST HATTI - KUZEY GUNEY")
    db.add(hat)
    db.commit()
    db.refresh(hat)

    kuzey, guney = [], []
    for i in range(20):
        ad = f"DURAK {i:02d}" if i < 19 else KUZEY
        d = main.Durak(hat_id=hat.id, durak_adi=ad, latitude=ENLEM_BASI + ADIM * i,
                       longitude=29.0, sira_no=i + 1, yon=KUZEY)
        db.add(d)
        kuzey.append(d)
    for j in range(20):
        ad = f"DURAK {j:02d} G" if j < 19 else GUNEY
        d = main.Durak(hat_id=hat.id, durak_adi=ad, latitude=ENLEM_BASI + ADIM * (19 - j),
                       longitude=29.0, sira_no=j + 1, yon=GUNEY)
        db.add(d)
        guney.append(d)
    db.commit()
    for d in kuzey + guney:
        db.refresh(d)
    return SimpleNamespace(hat=hat, kuzey=kuzey, guney=guney)

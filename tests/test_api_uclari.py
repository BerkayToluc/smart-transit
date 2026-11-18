"""Mevcut HTTP uç noktalarının yanıt BİÇİMİNİ ve temel davranışını sabitler.

Amaç: main.py üzerinde yapılacak refaktörlerde (#4) hiçbir şeyin değişmediğini görmek.
"""
import pytest

from tests.conftest import GUNEY, KUZEY


def _arac(kapino, enlem, boylam, yon):
    return {"kapino": kapino, "enlem": enlem, "boylam": boylam, "yon": yon}


# --- GET / --------------------------------------------------------------------
def test_ana_sayfa(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"mesaj": "SmartTransit API Tıkır Tıkır Çalışıyor"}


# --- GET /api/hatlar ----------------------------------------------------------
def test_hatlar_listesi(client, ornek_hat):
    r = client.get("/api/hatlar")
    assert r.status_code == 200
    hatlar = r.json()
    assert isinstance(hatlar, list)
    bizim = [h for h in hatlar if h["hat_kodu"] == "T100"]
    assert len(bizim) == 1
    assert set(bizim[0]) == {"id", "hat_kodu", "hat_adi"}
    assert bizim[0]["id"] == ornek_hat.hat.id


# --- GET /api/duraklar/{hat_id} -----------------------------------------------
def test_duraklar_sema_ve_siralama(client, ornek_hat):
    r = client.get(f"/api/duraklar/{ornek_hat.hat.id}")
    assert r.status_code == 200
    duraklar = r.json()
    assert len(duraklar) == 40  # iki yön x 20 durak
    assert set(duraklar[0]) == {"id", "durak_adi", "latitude", "longitude", "sira_no", "yon"}
    siralar = [d["sira_no"] for d in duraklar]
    assert siralar == sorted(siralar)
    assert {d["yon"] for d in duraklar} == {KUZEY, GUNEY}


def test_duraklar_olmayan_hat_bos_liste(client):
    r = client.get("/api/duraklar/999999")
    assert r.status_code == 200
    assert r.json() == []


# --- GET /api/canli-otobus/{hat_kodu} -----------------------------------------
def test_canli_otobus_arac_var(client, sahte_iett):
    sahte_iett["C1"] = [_arac("A-1", "41,01", "29,0", "X"), _arac("A-2", "41,02", "29,0", "X")]
    r = client.get("/api/canli-otobus/C1")
    assert r.status_code == 200
    govde = r.json()
    assert govde["mesaj"] == "C1 hattında 2 araç bulundu"
    assert [a["kapino"] for a in govde["araclar"]] == ["A-1", "A-2"]


def test_canli_otobus_arac_yok(client):
    r = client.get("/api/canli-otobus/C2")
    assert r.status_code == 200
    assert r.json() == {"mesaj": "Aktif araç bulunamadı", "araclar": []}


def test_canli_otobus_iett_erisilemiyor_bos_doner(client):
    # Mevcut davranış: servis çökse bile 200 ve boş liste (hata ayrıştırılmıyor, bkz. #30)
    from tests.conftest import IETT_COKUK
    IETT_COKUK["acik"] = True
    r = client.get("/api/canli-otobus/C3")
    assert r.status_code == 200
    assert r.json()["araclar"] == []


# --- POST /api/en-yakin-durak -------------------------------------------------
def _istek(hat, bas_lat, hedef_lat):
    return {"hat_kodu": hat, "baslangic_lat": bas_lat, "baslangic_lng": 29.0,
            "hedef_lat": hedef_lat, "hedef_lng": 29.0}


def test_en_yakin_durak_guney_kuzey_yonu(client, ornek_hat):
    r = client.post("/api/en-yakin-durak", json=_istek("T100", 41.0025, 41.1475))
    assert r.status_code == 200
    g = r.json()
    assert g["mesaj"] == "Evrensel durak ve yön başarıyla hesaplandı!"
    assert g["hesaplanan_yon"] == KUZEY
    assert g["durak_id"] == ornek_hat.kuzey[0].id
    assert g["durak_adi"] == "DURAK 00"
    assert g["durak_lat"] == pytest.approx(41.00)
    assert g["yurume_mesafesi_km"] == pytest.approx(0.28, abs=0.02)
    assert set(g) == {"mesaj", "durak_id", "durak_adi", "durak_lat", "durak_lon",
                      "hesaplanan_yon", "yurume_mesafesi_km"}


def test_en_yakin_durak_ters_yon(client, ornek_hat):
    r = client.post("/api/en-yakin-durak", json=_istek("T100", 41.1475, 41.0025))
    assert r.status_code == 200
    assert r.json()["hesaplanan_yon"] == GUNEY


def test_en_yakin_durak_hat_kodu_kucuk_harf(client, ornek_hat):
    r = client.post("/api/en-yakin-durak", json=_istek("t100", 41.0025, 41.1475))
    assert r.json()["hesaplanan_yon"] == KUZEY


def test_en_yakin_durak_bilinmeyen_hat(client):
    r = client.post("/api/en-yakin-durak", json=_istek("YOKTUR", 41.0, 41.1))
    assert r.status_code == 200
    assert r.json() == {"hata": "YOKTUR hattı veritabanında bulunamadı."}


def test_en_yakin_durak_eksik_alan_422(client):
    r = client.post("/api/en-yakin-durak", json={"hat_kodu": "T100"})
    assert r.status_code == 422


# --- GET /api/moovit/{hat}/{durak_id}/{yon} -----------------------------------
# NOT: İETT yanıtı 15 sn önbelleğe alınıyor ve araç geçmişi hat koduna göre tutuluyor.
# Testler birbirine sızmasın diye her test URL'de farklı bir hat kodu (M1, M2, ...) kullanır;
# URL'deki hat kodu yalnızca İETT sorgusu içindir, durak verisi durak_id'den gelir.
def test_moovit_yaklasan_arac(client, ornek_hat, sahte_iett):
    yolcu = ornek_hat.kuzey[10]   # enlem 41.10
    sahte_iett["M1"] = [
        _arac("K1", "41,0625", "29,0", KUZEY),   # yolcudan ~4.2 km geride, doğru yönde
        _arac("K2", "41,1055", "29,0", KUZEY),   # durağı geçmiş -> listede olmamalı
        _arac("K3", "41,0625", "29,0", GUNEY),   # ters yön -> listede olmamalı
    ]
    r = client.get(f"/api/moovit/M1/{yolcu.id}/{KUZEY}")
    assert r.status_code == 200
    g = r.json()
    assert g["sorgulanan_durak"] == yolcu.durak_adi
    assert g["secilen_hedef"] == KUZEY
    bilgi = g["yolcuya_bilgi"]
    assert [a["kapi_no"] for a in bilgi] == ["K1"]
    arac = bilgi[0]
    assert set(arac) == {"kapi_no", "mesafe_km", "tahmini_varis_dakika", "gittigi_yon", "hiz_kmh"}
    assert arac["mesafe_km"] == pytest.approx(4.16, abs=0.15)
    assert arac["hiz_kmh"] == 25.0          # geçmişi olmayan araç: varsayılan hız
    assert 9 <= arac["tahmini_varis_dakika"] <= 11
    assert arac["gittigi_yon"] == KUZEY


def test_moovit_sonuclar_dakikaya_gore_sirali(client, ornek_hat, sahte_iett):
    yolcu = ornek_hat.kuzey[15]   # enlem 41.15
    sahte_iett["M2"] = [
        _arac("UZAK", "41,0525", "29,0", KUZEY),
        _arac("YAKIN", "41,1325", "29,0", KUZEY),
    ]
    r = client.get(f"/api/moovit/M2/{yolcu.id}/{KUZEY}")
    bilgi = r.json()["yolcuya_bilgi"]
    assert [a["kapi_no"] for a in bilgi] == ["YAKIN", "UZAK"]
    dakikalar = [a["tahmini_varis_dakika"] for a in bilgi]
    assert dakikalar == sorted(dakikalar)


def test_moovit_aktif_arac_yok(client, ornek_hat):
    yolcu = ornek_hat.kuzey[10]
    r = client.get(f"/api/moovit/M3/{yolcu.id}/{KUZEY}")
    assert r.json() == {"mesaj": "Bu hatta şu an aktif araç bulunamadı."}


def test_moovit_olmayan_durak(client):
    r = client.get(f"/api/moovit/T100/999999/{KUZEY}")
    assert r.status_code == 200
    assert r.json() == {"hata": "999999 ID numaralı durak veritabanında bulunamadı!"}


def test_moovit_olmayan_yon(client, ornek_hat):
    yolcu = ornek_hat.kuzey[10]
    r = client.get(f"/api/moovit/T100/{yolcu.id}/OLMAYAN")
    assert r.json() == {"hata": "Bu yöne ait yeterli durak bulunamadı."}


# --- GET /api/guzergah/{hat_id}/{yon} -----------------------------------------
def test_guzergah_sirali_nokta_listesi(client, db, ornek_hat):
    import main
    # Bilerek karışık sırada ekle; uç nokta sira_no'ya göre sıralamalı
    for sira, lat in [(2, 41.02), (0, 41.00), (1, 41.01)]:
        db.add(main.Guzergah(hat_id=ornek_hat.hat.id, yon="GZR", sira_no=sira,
                             latitude=lat, longitude=29.0))
    db.commit()
    r = client.get(f"/api/guzergah/{ornek_hat.hat.id}/GZR")
    assert r.status_code == 200
    assert r.json() == [{"lat": 41.00, "lng": 29.0}, {"lat": 41.01, "lng": 29.0},
                        {"lat": 41.02, "lng": 29.0}]


def test_guzergah_bulunamayan_bos_liste(client, ornek_hat):
    r = client.get(f"/api/guzergah/{ornek_hat.hat.id}/YOK")
    assert r.json() == []

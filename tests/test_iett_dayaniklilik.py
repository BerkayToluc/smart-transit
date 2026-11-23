"""#30: İETT SOAP zaman aşımı, yeniden deneme, loglama ve "servis erişilemiyor" ayrımı."""
import json
import logging
from xml.sax.saxutils import escape

import pytest
import requests

from app import live


class Yanit:
    def __init__(self, araclar):
        self.text = ('<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
                     '<r xmlns="http://tempuri.org/"><GetHatOtoKonum_jsonResult>' + escape(json.dumps(araclar))
                     + "</GetHatOtoKonum_jsonResult></r></soap:Body></soap:Envelope>")

    def raise_for_status(self):
        pass


@pytest.fixture
def hizli(monkeypatch):
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    live.iett_cache.clear()
    yield
    live.iett_cache.clear()


def test_zaman_asimi_istege_verilir(monkeypatch, hizli):
    gorulen = {}

    def post(url, data=None, headers=None, timeout=None, **kw):
        gorulen["timeout"] = timeout
        return Yanit([])

    monkeypatch.setattr(live.requests, "post", post)
    live.iett_durum("ZA1")
    assert gorulen["timeout"] == live.SOAP_ZAMAN_ASIMI and gorulen["timeout"] is not None


def test_gecici_hata_yeniden_denenir_ve_basarir(monkeypatch, hizli):
    cagri = []

    def post(*a, **k):
        cagri.append(1)
        if len(cagri) < 3:
            raise requests.ConnectionError("kesildi")
        return Yanit([{"kapino": "A1"}])

    monkeypatch.setattr(live.requests, "post", post)
    d = live.iett_durum("TK1")
    assert d["erisilemiyor"] is False and d["araclar"] == [{"kapino": "A1"}] and len(cagri) == 3


def test_surekli_hata_erisilemiyor_isaretlenir_loglanir_ve_kisa_onbelleklenir(monkeypatch, hizli, caplog):
    cagri = []

    def post(*a, **k):
        cagri.append(1)
        raise requests.Timeout("zaman aşımı")

    monkeypatch.setattr(live.requests, "post", post)
    with caplog.at_level(logging.WARNING, logger="app.live"):
        d = live.iett_durum("SH1")
    assert d == {"araclar": [], "erisilemiyor": True, "an": d["an"]}
    assert len(cagri) == live.SOAP_DENEME
    assert any("İETT SOAP hatası" in m for m in caplog.messages)
    live.iett_durum("SH1")                                 # fırtına önleme: hata birkaç sn tekrarlanmaz
    assert len(cagri) == live.SOAP_DENEME
    # hata önbelleği dolunca yeniden denenir
    monkeypatch.setattr(live, "HATA_ONBELLEK_SN", -1)
    live.iett_durum("SH1")
    assert len(cagri) == 2 * live.SOAP_DENEME


def test_bozuk_yanit_hata_sayilir(monkeypatch, hizli):
    class Bozuk:
        text = "<<>>bu xml degil"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(live.requests, "post", lambda *a, **k: Bozuk())
    assert live.iett_durum("BZ1")["erisilemiyor"] is True


def test_aktif_arac_yok_ile_servis_yok_ayri(client, monkeypatch, hizli):
    monkeypatch.setattr(live.requests, "post", lambda *a, **k: Yanit([]))
    assert client.get("/api/canli-otobus/AY1").json() == {"mesaj": "Aktif araç bulunamadı", "araclar": []}
    live.iett_cache.clear()

    def coktu(*a, **k):
        raise requests.ConnectionError("yok")

    monkeypatch.setattr(live.requests, "post", coktu)
    j = client.get("/api/canli-otobus/AY2").json()
    assert j["servis_erisilemiyor"] is True and j["araclar"] == []

import requests
import xml.etree.ElementTree as ET

API_URLS = {
    "1. Filo (Canlı Otobüs) Servisi": "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx?WSDL",
    "2. Ana Veri (Durak/Hat/Sefer) Servisi": "https://api.ibb.gov.tr/iett/UlasimAnaVeri/DataOdata.asmx?WSDL",
    "3. Dinamik Veri (Duyurular) Servisi": "https://api.ibb.gov.tr/iett/UlasimDinamikVeri/Duyurular.asmx?WSDL"
}

print("🕵️‍♂️ İETT Sunucuları Taranıyor... (Bu işlem birkaç saniye sürebilir)\n")

for isim, url in API_URLS.items():
    print(f"--- {isim} ---")
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            metotlar = set()
            for elem in root.iter():
                # XML içindeki 'operation' (fonksiyon) isimlerini çekiyoruz
                if 'operation' in elem.tag and elem.attrib.get('name'):
                    metotlar.add(elem.attrib.get('name'))

            for m in sorted(metotlar):
                print(f" ✔ {m}")
        else:
            print(f" ❌ Sunucu çökmüş veya yanıt vermedi (Kod: {res.status_code})")
    except Exception as e:
        print(f" ❌ Bağlantı hatası: {e}")
    print("\n")

print("🔍 Arama Tamamlandı!")
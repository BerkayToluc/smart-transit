import json

print("\n🔬 --- GUZERGAH.CSV (JSON) OTOPSİSİ ---")
try:
    with open('guzergah.csv', 'r', encoding='utf-8-sig') as f:
        veri = json.load(f)

        # İçindeki ilk durağın tüm bilgilerini ekrana basıyoruz
        if "features" in veri:
            print(json.dumps(veri["features"][0]["properties"], indent=4, ensure_ascii=False))
        elif isinstance(veri, list):
            print(json.dumps(veri[0], indent=4, ensure_ascii=False))
        else:
            print("Farklı bir JSON yapısı geldi:", type(veri))
except Exception as e:
    print(f"Hata oluştu: {e}")
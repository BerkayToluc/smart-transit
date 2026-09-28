from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
# Next.js'in bu sunucuya erişip veri alabilmesi için güvenlik duvarını (CORS) açıyoruz
CORS(app)


@app.route('/api/python/canli-otobus/<hat_kodu>', methods=['GET'])
def canli_otobus_getir(hat_kodu):
    # İleride buraya gerçek İETT/Moovit anlık konum botunu entegre edeceğiz.
    # Şimdilik bağlantının kusursuz olduğunu görmek için sanal araçlar gönderiyoruz.

    if hat_kodu == "522":
        araclar = [
            {"kapino": "O-1001", "enlem": 41.0630, "boylam": 28.9920, "yon": "ALEMDAĞ"},  # Mecidiyeköy civarı
            {"kapino": "O-1002", "enlem": 41.0250, "boylam": 29.1150, "yon": "MECİDİYEKÖY"},  # Çamlıca civarı
            {"kapino": "O-1003", "enlem": 41.0370, "boylam": 29.2150, "yon": "ALEMDAĞ"},  # Çekmeköy civarı
            {"kapino": "O-1004", "enlem": 41.0500, "boylam": 29.1700, "yon": "MECİDİYEKÖY"}  # Dudullu civarı
        ]
    elif hat_kodu == "401":
        araclar = [
            {"kapino": "O-4001", "enlem": 41.1400, "boylam": 28.4600, "yon": "AVCILAR"},  # Çatalca civarı
            {"kapino": "O-4002", "enlem": 41.0400, "boylam": 28.5500, "yon": "ÇATALCA"}  # Büyükçekmece civarı
        ]
    else:
        araclar = []

    return jsonify({"araclar": araclar})


# React'in çökmemesi için Rota Hesaplama butonuna boş bir yanıt dönen geçici köprü
@app.route('/api/python/en-yakin-durak', methods=['POST'])
def en_yakin_durak():
    return jsonify({"hata": "Rota hesaplama motoru henüz aktif değil."})


if __name__ == '__main__':
    print("🚀 SmartTransit Python Motoru Başlatıldı! Port: 5000")
    app.run(port=5000, debug=True)
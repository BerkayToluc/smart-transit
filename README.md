# SmartTransit

İstanbul için canlı otobüs takibi ve durak bazlı varış tahmini. Hedef: otobüs, metro,
tramvay, metrobüs ve vapuru birleştiren aktarmalı rota planlayıcı (yol haritası için
[issue listesine](../../issues) bakın).

## Yapı

| Klasör / dosya | Ne işe yarıyor |
|---|---|
| `main.py` | FastAPI backend: hat/durak listesi, İETT canlı araç konumu, varış tahmini (ETA), GTFS aktarım uç noktaları |
| `frontend/` | Next.js arayüzü (harita, hat arama, yaklaşan araçlar) |
| `routes.csv`, `stops.csv`, `trips.csv` | İETT GTFS verisinin bir kısmı (`;` ile ayrılmış, karakterleri bozuk, bkz. `main.py` içindeki düzeltme yardımcıları) |
| `gtfs_*.py`, `hat_ekleyici.py`, `veri_yukle.py` | Tek seferlik veri yükleme betikleri (aşağıdaki uyarıya bakın) |
| `tests/` | Otomatik testler (`pytest`). Gerçek veritabanına ve İETT'ye dokunmaz |
| `scripts/` | İETT servislerini / veri dosyalarını yoklamak için deneme betikleri (test değil); kök klasörden çalıştırın, örn. `python scripts/iett_servis_yokla.py` |

## Gereksinimler
- Python 3.12 veya üzeri
- Node.js 22 veya üzeri
- Bir Neon.tech (PostgreSQL) veritabanı
- Google Maps JavaScript API anahtarı (Maps JavaScript, Places ve Directions API'leri açık olmalı)

## Kurulum

### 1) Ayar dosyaları
Gizli bilgiler koda yazılmaz, `.env` dosyalarından okunur. İkisi de git'e eklenmez.

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```
Windows PowerShell'de `cp` yerine `Copy-Item` da kullanılabilir.

- `.env` içinde `DATABASE_URL` değerini doldurun (Neon panelindeki bağlantı adresi).
- `frontend/.env.local` içinde `DATABASE_URL`, `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` ve gerekirse `NEXT_PUBLIC_API_URL` değerlerini doldurun.

### 2) Backend
```bash
python -m venv venv
```
Sanal ortamı etkinleştirin (Windows: `venv\Scripts\Activate.ps1`, Linux/macOS: `source venv/bin/activate`), sonra:
```bash
pip install -r requirements.txt
```
```bash
uvicorn main:app --port 8000
```
Açılışta `Veritabanı bağlandı ve tablolar oluşturuldu` yazısını görmelisiniz.

### 3) Frontend
```bash
cd frontend
```
```bash
npm install
```
```bash
npm run dev
```
Tarayıcıda <http://localhost:3000> adresini açın. Backend adresi varsayılan olarak
`http://localhost:8000`; başka bir adres için `NEXT_PUBLIC_API_URL` kullanın
(değiştirdikten sonra `npm run dev` yeniden başlatılmalı).

## Geliştirme
```bash
pip install -r requirements-dev.txt
```
```bash
pytest
```
Testler geçici bir SQLite veritabanı ve sahte İETT yanıtı kullanır; `.env` dosyanıza veya
canlı veritabanına dokunmaz.
```bash
ruff check --select E9,F63,F7,F82 .
```
```bash
cd frontend && npm run build
```
Aynı kontrolleri GitHub Actions (`.github/workflows/ci.yml`) her push ve pull request'te çalıştırır.

## Veri yükleme betikleri hakkında uyarı
`gtfs_yukle.py` ve `veri_yukle.py`, çalıştırıldığında `DATABASE_URL`'in gösterdiği veritabanında
`hatlar`, `duraklar` ve `otobusler` tablolarını **siler** (`DROP TABLE ... CASCADE`) ve yeniden kurar.
Gerçek verinin bulunduğu veritabanına karşı çalıştırmayın. Hat bazlı güvenli aktarım için
`main.py` içindeki `/api/admin/gtfs-aktar/{hat_kodu}` uç noktası kullanılabilir.
Bu betikler `from main import ...` kullandığı için proje kök klasöründen çalıştırılmalıdır.

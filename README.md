# SmartTransit

İstanbul için canlı otobüs takibi ve durak bazlı varış tahmini. Hedef: otobüs, metro,
tramvay, metrobüs ve vapuru birleştiren aktarmalı rota planlayıcı (yol haritası için
[issue listesine](../../issues) bakın).

## Yapı

| Klasör / dosya | Ne işe yarıyor |
|---|---|
| `main.py` | FastAPI uygulamasının giriş noktası (`uvicorn main:app`): router'ları bağlar. Eski betikler için `Hat`, `Durak`, `SessionLocal` gibi adları yeniden dışa aktarır |
| `app/db.py` | Veritabanı bağlantısı, modeller (`Hat`, `Durak`, `Guzergah`, ...), `get_db` |
| `app/catalog.py` | `/`, `/api/hatlar`, `/api/duraklar`, `/api/guzergah` |
| `app/live.py` | İETT canlı araç konumu ve durak bazlı varış tahmini (`/api/canli-otobus`, `/api/moovit`) |
| `app/nearest.py` | `/api/en-yakin-durak` |
| `app/gtfs_admin.py` | GTFS aktarım uç noktaları (`/api/admin/*`) ve metin/koordinat düzeltme yardımcıları |
| `app/utils.py` | Ortak yardımcılar (mesafe hesabı) |
| `app/gtfs/` | Çok modlu GTFS şeması (`gtfs_*` tabloları), okuyucu, mod eşleme, yükleyici ve planlama kuralları; bkz. `docs/schema.md` |
| `docs/` | Veri kaynakları (`veri-kaynaklari.md`) ve şema (`schema.md`) |
| `frontend/` | Next.js arayüzü (harita, hat arama, yaklaşan araçlar) |
| `routes.csv`, `stops.csv`, `trips.csv` | İETT GTFS verisinin bir kısmı (`;` ile ayrılmış, karakterleri bozuk, bkz. `main.py` içindeki düzeltme yardımcıları) |
| `gtfs_*.py`, `hat_ekleyici.py`, `veri_yukle.py` | Tek seferlik veri yükleme betikleri (aşağıdaki uyarıya bakın) |
| `tests/` | Otomatik testler (`pytest`). Gerçek veritabanına ve İETT'ye dokunmaz |
| `scripts/` | `build_gtfs.py` (GTFS indirme/yükleme/rapor) ve İETT servislerini yoklamak için deneme betikleri (test değil); kök klasörden çalıştırın |

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

## Toplu taşıma verisini indirme ve yükleme
İBB Açık Veri Portalı'ndan GTFS verisini indirip yüklemek için (**kendi bilgisayarınızda**, portal bulut
sunucularından açılmıyor; ayrıntı: `docs/schema.md`):
```bash
python scripts/build_gtfs.py hepsi iett ibb --hedef sqlite:///gtfs_data/gtfs.db
```
`--hedef` yazmazsanız `.env`'deki canlı veritabanı kullanılır ve `--evet` istenir.

## Veri yükleme betikleri hakkında uyarı
`gtfs_yukle.py` ve `veri_yukle.py`, çalıştırıldığında `DATABASE_URL`'in gösterdiği veritabanında
`hatlar`, `duraklar` ve `otobusler` tablolarını **siler** (`DROP TABLE ... CASCADE`) ve yeniden kurar.
Gerçek verinin bulunduğu veritabanına karşı çalıştırmayın. Hat bazlı güvenli aktarım için
`main.py` içindeki `/api/admin/gtfs-aktar/{hat_kodu}` uç noktası kullanılabilir.
Bu betikler `from main import ...` kullandığı için proje kök klasöründen çalıştırılmalıdır.

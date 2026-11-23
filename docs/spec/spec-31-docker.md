# Spec #31: Docker compose ve opsiyonel salt-okunur graf modu

## Problem
Kurulum elle yapılıyor (Python + Node + GTFS veri hazırlığı); yeni geliştirici ya da barındırma için tekrarlanabilir paket yok. İBB portalı bulut IP'lerini engellediği için veri yerelde hazırlanıyor.

## Hedefler
- `docker compose up` ile api + web ayağa kalksın (veri hazırsa).
- Salt-okunur mod: Neon/SQLite bağlantısı olmadan hazır `graf.pkl` + `guzergah.pkl` ile rota servisi.

## Hedef dışı
- Kubernetes, otomatik ölçekleme. Veri indirme işini konteynerde çalıştırmak (yerelde kalır).

## Gereksinimler
**P0**
- `Dockerfile` (api), `frontend/Dockerfile`, `docker-compose.yml`; `.env` değişkenleri (`CORS_ORIGINS`, `ADMIN_API_KEY`, `NEXT_PUBLIC_API_URL`) belgeli, sırlar imaja girmez.
  - Kabul: temiz makinede `compose up` sonrası `/health` 200 ve ön yüz açılır.
- Salt-okunur graf modu: `ROTA_GRAF_ONBELLEK` ile yalnızca pickle'dan yükle; veritabanı yoksa `/health` `degraded` ama `/api/plan` çalışır.
**P1**
- Sağlık kontrolü (`HEALTHCHECK`), küçük imaj, CI'da imaj derleme.
**P2**
- Veri hazırlama için ayrı "builder" servisi (yerelde çalıştırılan).

## Başarı ölçütleri
- Sıfırdan kurulum 15 dk altında; imaj derleme CI'da yeşil.

## Açık sorular
- (Ürün, **engelleyici**) Yayın hedefi var mı (A2)? Yoksa bu iş yalnızca geliştirici deneyimi olarak önceliklenir.
- (Mühendislik) Graf pickle sürümü ile imaj sürümü uyumu: sürüm uyuşmazlığında net hata.

## Zamanlama
Yayın kararına bağlı. Orta iş (2–3 gün).

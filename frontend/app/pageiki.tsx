"use client";
import { useEffect, useRef, useState } from "react";
import { GoogleMap, useJsApiLoader, Marker, Autocomplete, Polyline, InfoWindow } from "@react-google-maps/api";

const containerStyle = {
  width: "100%",
  height: "100%",
};

const center = {
  lat: 41.0400,
  lng: 28.5500,
};

const libraries: any = ["places"];

// 📍 TEMİZLEYİCİ
const turkceKarakterDuzelt = (metin: string) => {
  if (!metin) return "";
  return metin
    .replace(/Ã‡/g, "Ç").replace(/Ã§/g, "ç")
    .replace(/Äž/g, "Ğ").replace(/ÄŸ/g, "ğ")
    .replace(/Ä±/g, "ı").replace(/Ä°/g, "İ")
    .replace(/Ã–/g, "Ö").replace(/Ã¶/g, "ö")
    .replace(/Åž/g, "Ş").replace(/ÅŸ/g, "ş")
    .replace(/Ãœ/g, "Ü").replace(/Ã¼/g, "ü")
    .replace(/Ð/g, "Ğ").replace(/ð/g, "ğ")
    .replace(/Ã/g, "Ğ").replace(/Ã°/g, "ğ")
    .replace(/Ý/g, "İ").replace(/ý/g, "ı")
    .replace(/Þ/g, "Ş").replace(/þ/g, "ş")
    .replace(/Å/g, "Ş")
    .replace(/[\uFFFD\u0080-\u009F\u200B-\u200D\uFEFF]/g, "");
};

// 📍 REACT İÇİ VERİTABANI KOORDİNAT TAMİRCİSİ
const fixCoord = (val: any) => {
  if (!val) return 0.0;
  let v = parseFloat(String(val).replace(',', '.'));
  if (isNaN(v)) return 0.0;
  if (Math.abs(v) > 90) {
    const s = String(Math.floor(Math.abs(v)));
    if (s.length >= 2) {
      v = parseFloat(s.substring(0, 2) + '.' + s.substring(2));
    }
  }
  return v;
};

// 🚀 AKILLI TAHMİN ALGORİTMASI (kuş uçuşu mesafe - fallback için)
const getDistanceFromLatLonInKm = (lat1: number, lon1: number, lat2: number, lon2: number) => {
  const R = 6371;
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(lat1 * (Math.PI / 180)) * Math.cos(lat2 * (Math.PI / 180)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
};

// 🚗 Google Directions API tek seferde en fazla 23 ara nokta (waypoint) kabul ediyor.
// 50+ duraklı bir hattı tek istekte gönderemeyiz, bu yüzden parçalara (chunk) bölüp
// sonuçları uç uca ekliyoruz. Böylece çizgi sadece asfalttan geçer.
const MAX_NOKTA_PER_ISTEK = 25; // 1 başlangıç + 23 ara nokta + 1 bitiş

async function kesintisizYolRotasiHesapla(koordinatlar: { lat: number; lng: number }[]) {
  if (!window.google || koordinatlar.length < 2) return koordinatlar;

  const directionsService = new window.google.maps.DirectionsService();
  let tumNoktalar: { lat: number; lng: number }[] = [];
  let baslangicIndex = 0;

  while (baslangicIndex < koordinatlar.length - 1) {
    const bitisIndex = Math.min(baslangicIndex + MAX_NOKTA_PER_ISTEK - 1, koordinatlar.length - 1);
    const parca = koordinatlar.slice(baslangicIndex, bitisIndex + 1);

    if (parca.length < 2) break;

    const origin = parca[0];
    const destination = parca[parca.length - 1];
    const waypoints = parca.slice(1, -1).map((p) => ({ location: p, stopover: false }));

    try {
      const sonuc: any = await new Promise((resolve, reject) => {
        directionsService.route(
          {
            origin,
            destination,
            waypoints,
            travelMode: window.google.maps.TravelMode.DRIVING,
            optimizeWaypoints: false,
          },
          (result: any, status: any) => {
            if (status === "OK" && result) resolve(result);
            else reject(status);
          }
        );
      });

      const yol = sonuc.routes[0].overview_path.map((p: any) => ({ lat: p.lat(), lng: p.lng() }));
      tumNoktalar = tumNoktalar.concat(yol);
    } catch (err) {
      console.warn("Directions API parçası hesaplanamadı, bu parça için düz çizgiye dönülüyor:", err);
      tumNoktalar = tumNoktalar.concat(parca);
    }

    baslangicIndex = bitisIndex; // bir sonraki parça buradan devam etsin (kesintisiz bağlantı)
  }

  return tumNoktalar;
}

export default function CanliHarita() {
  const [otobusler, setOtobusler] = useState<any[]>([]);
  const otobuslerRef = useRef<any[]>([]);

  const [sistemdekiHatlar, setSistemdekiHatlar] = useState<any[]>([]);
  const [secilenHat, setSecilenHat] = useState("");
  const [beklenenAraclar, setBeklenenAraclar] = useState<any[]>([]);
  const [hesaplaniyor, setHesaplaniyor] = useState(false);
  const [hataMesaji, setHataMesaji] = useState("");
  const [bulunanDurakMesaji, setBulunanDurakMesaji] = useState("");

  const [autocompleteBaslangic, setAutocompleteBaslangic] = useState<any>(null);
  const [autocompleteHedef, setAutocompleteHedef] = useState<any>(null);

  const [baslangicKoordinat, setBaslangicKoordinat] = useState({ lat: 0, lng: 0 });
  const [hedefKoordinat, setHedefKoordinat] = useState({ lat: 0, lng: 0 });
  const baslangicKoordinatRef = useRef({ lat: 0, lng: 0 });

  const [baslangicMetni, setBaslangicMetni] = useState("");
  const [hedefMetni, setHedefMetni] = useState("");

  const [bulunanDurakKoordinat, setBulunanDurakKoordinat] = useState<{ lat: number; lng: number; adi: string } | null>(null);

  const [rotaDuraklari, setRotaDuraklari] = useState<any[]>([]);
  const [yolCizgisi, setYolCizgisi] = useState<{ lat: number; lng: number }[]>([]); // 🚗 asfalta oturan gerçek rota
  const [panelAcik, setPanelAcik] = useState(true);
  const [seciliOtobus, setSeciliOtobus] = useState<any>(null);

  const [aramaMetni, setAramaMetni] = useState("");
  const [dropdownAcik, setDropdownAcik] = useState(false);

  // 📍 2. SORUN İÇİN: son hesapladığımız durak + yön bilgisini saklıyoruz ki
  // 10 saniyede bir arka planda otomatik tazeleyebilelim (buton olmadan).
  const [aktifDurakBilgisi, setAktifDurakBilgisi] = useState<{ durakId: number; yon: string } | null>(null);
  const aktifDurakBilgisiRef = useRef<{ durakId: number; yon: string } | null>(null);

  const { isLoaded } = useJsApiLoader({
    id: "google-map-script",
    googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
    libraries: libraries,
    // 📍 3. SORUN İÇİN: dil ve bölge parametresi olmayınca Google sunucu/tarayıcı
    // varsayılanı olan İngilizce'ye düşüyordu ("Atirus AVM" -> "Atirus Shopping Center").
    language: "tr",
    region: "TR",
  });

  // refs'leri her state değiştiğinde güncel tut (setInterval içindeki "stale closure" sorununu önler)
  useEffect(() => {
    otobuslerRef.current = otobusler;
  }, [otobusler]);

  useEffect(() => {
    baslangicKoordinatRef.current = baslangicKoordinat;
  }, [baslangicKoordinat]);

  useEffect(() => {
    aktifDurakBilgisiRef.current = aktifDurakBilgisi;
  }, [aktifDurakBilgisi]);

  useEffect(() => {
    const hatlariCek = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/hatlar");
        if (response.ok) {
          const data = await response.json();

          const temizlenmisHatlar = data.map((h: any) => ({
            ...h,
            hat_kodu: turkceKarakterDuzelt(h.hat_kodu),
            hat_adi: turkceKarakterDuzelt(h.hat_adi),
          }));

          const siraliHatlar = temizlenmisHatlar.sort((a: any, b: any) =>
            a.hat_kodu.localeCompare(b.hat_kodu, undefined, { numeric: true, sensitivity: "base" })
          );

          setSistemdekiHatlar(siraliHatlar);

          if (siraliHatlar.length > 0) {
            setSecilenHat(siraliHatlar[0].hat_kodu);
            setAramaMetni(siraliHatlar[0].hat_kodu);
          }
        }
      } catch (error) {
        console.error("FastAPI sunucusuna bağlanılamadı:", error);
      }
    };
    hatlariCek();
  }, []);

  const otobusleriGetir = async () => {
    if (!secilenHat) return;
    try {
      const response = await fetch(`http://localhost:8000/api/canli-otobus/${secilenHat}`);
      const data = await response.json();
      if (data.araclar) setOtobusler(data.araclar);
      else setOtobusler([]);
    } catch (error) {
      console.error("Harita verisi çekilirken hata:", error);
    }
  };

  // 📍 Fallback "akıllı tahmin" listesini üretir (Moovit/IETT verisi boş dönerse kullanılır)
  const akilliTahminListesiUret = (araclar: any[]) => {
    const akilliListe = araclar
      .map((o: any) => {
        const lat_str = fixCoord(o.enlem);
        const lon_str = fixCoord(o.boylam);
        const mesafe = getDistanceFromLatLonInKm(
          lat_str,
          lon_str,
          Number(baslangicKoordinatRef.current.lat),
          Number(baslangicKoordinatRef.current.lng)
        );
        const tahminiSure = Math.max(1, Math.round(mesafe * 4));
        return {
          kapi_no: o.kapino,
          gittigi_yon: turkceKarakterDuzelt(o.yon),
          tahmini_varis_dakika: tahminiSure,
          mesafe_km: mesafe.toFixed(2),
        };
      })
      .filter((a) => Number(a.mesafe_km) < 15);

    akilliListe.sort((a, b) => parseFloat(a.mesafe_km) - parseFloat(b.mesafe_km));
    return akilliListe;
  };

  // 📍 2. SORUN İÇİN ÇEKİRDEK FONKSİYON:
  // Hesapla butonuna tekrar basmaya gerek kalmadan, 10 saniyede bir bu fonksiyon çalışır.
  // - Moovit/IETT verisiyle tekrar sorgular (backend zaten geçmiş otobüsleri sira_no'ya göre eliyor)
  // - Moovit boşsa, güncel otobüs konumlarıyla akıllı tahmini yeniden hesaplar
  // Böylece dakikalar gerçek zamanlı iner ve durağı geçen otobüs listeden otomatik düşer.
  const canliAraclariGuncelle = async () => {
    const aktifDurak = aktifDurakBilgisiRef.current;
    if (!aktifDurak || !secilenHat) return;

    let apiBasarili = false;
    try {
      const moovitResponse = await fetch(
        `http://localhost:8000/api/moovit/${secilenHat}/${aktifDurak.durakId}/${aktifDurak.yon}`
      );
      if (moovitResponse.ok) {
        const data = await moovitResponse.json();
        if (data.yolcuya_bilgi) {
          apiBasarili = true;
          if (data.yolcuya_bilgi.length > 0) {
            setBeklenenAraclar(data.yolcuya_bilgi);
            setHataMesaji("");
          } else {
            // Otobüsler durağı geçmiş ya da henüz yola çıkmamış
            setBeklenenAraclar([]);
            setHataMesaji(`Şu an ${secilenHat} hattında durağınıza yaklaşan araç yok.`);
          }
        }
      }
    } catch (e) {
      console.warn("Canlı güncelleme sırasında Moovit'e ulaşılamadı, akıllı algoritmaya geçiliyor.");
    }

    if (!apiBasarili) {
      const guncelOtobusler = otobuslerRef.current;
      if (guncelOtobusler.length > 0) {
        const akilliListe = akilliTahminListesiUret(guncelOtobusler);
        if (akilliListe.length > 0) {
          setBeklenenAraclar(akilliListe);
          setHataMesaji("");
        } else {
          setBeklenenAraclar([]);
          setHataMesaji(`Yakınınızda ve doğru yönde (15km altı) aktif araç bulunamadı.`);
        }
      } else {
        setBeklenenAraclar([]);
        setHataMesaji(`Seçtiğiniz ${secilenHat} rotasında şu an aktif hareket eden bir araç bulunamadı.`);
      }
    }
  };

  const onBaslangicLoad = (autoC: any) => setAutocompleteBaslangic(autoC);
  const onBaslangicChanged = () => {
    if (autocompleteBaslangic !== null) {
      const place = autocompleteBaslangic.getPlace();
      if (place.geometry) {
        setBaslangicKoordinat({
          lat: place.geometry.location.lat(),
          lng: place.geometry.location.lng(),
        });
        setBaslangicMetni(place.name || place.formatted_address || "");
      }
    }
  };

  const onHedefLoad = (autoC: any) => setAutocompleteHedef(autoC);
  const onHedefChanged = () => {
    if (autocompleteHedef !== null) {
      const place = autocompleteHedef.getPlace();
      if (place.geometry) {
        setHedefKoordinat({
          lat: place.geometry.location.lat(),
          lng: place.geometry.location.lng(),
        });
        setHedefMetni(place.name || place.formatted_address || "");
      }
    }
  };

  const konumlariDegistir = () => {
    const geciciKoordinat = baslangicKoordinat;
    setBaslangicKoordinat(hedefKoordinat);
    setHedefKoordinat(geciciKoordinat);

    const geciciMetin = baslangicMetni;
    setBaslangicMetni(hedefMetni);
    setHedefMetni(geciciMetin);
  };

  const hatDegistir = (hatKodu: string) => {
    setSecilenHat(hatKodu);
    setAramaMetni(hatKodu);
    setDropdownAcik(false);
    // Yeni hat seçildiğinde eski hesaplamalar geçersiz olur, temizle
    setBeklenenAraclar([]);
    setHataMesaji("");
    setBulunanDurakMesaji("");
    setBulunanDurakKoordinat(null);
    setRotaDuraklari([]);
    setYolCizgisi([]);
    setAktifDurakBilgisi(null);
  };

  const varisSuresiniHesapla = async () => {
    setHesaplaniyor(true);
    setBeklenenAraclar([]);
    setHataMesaji("");
    setBulunanDurakMesaji("");
    setBulunanDurakKoordinat(null);
    setRotaDuraklari([]);
    setYolCizgisi([]);
    setAktifDurakBilgisi(null);

    try {
      if (baslangicKoordinat.lat === 0 || hedefKoordinat.lat === 0) {
        throw new Error("Lütfen adresi yazdıktan sonra açılan Google alt listesinden bir konuma tıklayın.");
      }

      const durakResponse = await fetch("http://localhost:8000/api/en-yakin-durak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hat_kodu: secilenHat,
          baslangic_lat: Number(baslangicKoordinat.lat),
          baslangic_lng: Number(baslangicKoordinat.lng),
          hedef_lat: Number(hedefKoordinat.lat),
          hedef_lng: Number(hedefKoordinat.lng),
        }),
      });

      if (!durakResponse.ok) throw new Error("Sunucuya ulaşılamadı (Bağlantı hatası).");

      const durakData = await durakResponse.json();
      if (durakData.hata) throw new Error(durakData.hata);

      const bulunanDurakId = String(durakData.durak_id);
      const hesaplananEvrenselYon = String(durakData.hesaplanan_yon);

      let safeDurakLat = fixCoord(durakData.durak_lat);
      let safeDurakLon = fixCoord(durakData.durak_lon);

      const gercekYurumeKusUcusu = getDistanceFromLatLonInKm(
        Number(baslangicKoordinat.lat),
        Number(baslangicKoordinat.lng),
        safeDurakLat,
        safeDurakLon
      );

      let durakUyariText = `(${gercekYurumeKusUcusu.toFixed(2)} km yürüme)`;
      if (gercekYurumeKusUcusu > 100) {
        durakUyariText = `(SİZE olan mesafe ölçülüyor)`;
      }

      setBulunanDurakMesaji(`🚶‍♂️ En yakın durak: ${turkceKarakterDuzelt(durakData.durak_adi)} ${durakUyariText}`);

      setBulunanDurakKoordinat({
        lat: safeDurakLat,
        lng: safeDurakLon,
        adi: turkceKarakterDuzelt(durakData.durak_adi),
      });

      // 📍 MAVİ ÇİZGİ İÇİN DURAK LİSTESİNİ HAZIRLA (yol hesaplaması ayrı bir useEffect'te tetiklenecek)
      try {
        const secilenHatObj = sistemdekiHatlar.find(
          (h: any) => turkceKarakterDuzelt(String(h.hat_kodu)) === turkceKarakterDuzelt(String(secilenHat))
        );

        if (secilenHatObj) {
          const duraklarRes = await fetch(`http://localhost:8000/api/duraklar/${secilenHatObj.id}`);
          if (duraklarRes.ok) {
            const duraklarData = await duraklarRes.json();

            const gecerliDuraklar = duraklarData.filter((d: any) => {
              const lat = fixCoord(d.latitude || d.enlem);
              const lon = fixCoord(d.longitude || d.boylam);
              return lat !== 0 && lon !== 0;
            });

            const hedefDuraklar = gecerliDuraklar.filter((d: any) => String(d.yon) === hesaplananEvrenselYon);
            const binisIndex = hedefDuraklar.findIndex((d: any) => String(d.id) === bulunanDurakId);

            let inisIndex = -1;
            let minHedefMesafe = Infinity;

            hedefDuraklar.forEach((d: any, index: number) => {
              const dLat = fixCoord(d.latitude || d.enlem);
              const dLon = fixCoord(d.longitude || d.boylam);
              const mesafe = getDistanceFromLatLonInKm(Number(hedefKoordinat.lat), Number(hedefKoordinat.lng), dLat, dLon);
              if (mesafe < minHedefMesafe) {
                minHedefMesafe = mesafe;
                inisIndex = index;
              }
            });

            if (binisIndex !== -1 && inisIndex !== -1) {
              const baslangic = Math.min(binisIndex, inisIndex);
              const bitis = Math.max(binisIndex, inisIndex);
              setRotaDuraklari(hedefDuraklar.slice(baslangic, bitis + 1));
            } else if (binisIndex !== -1) {
              setRotaDuraklari(hedefDuraklar.slice(binisIndex));
            }
          }
        }
      } catch (err) {
        console.warn("Duraklar haritaya dizilirken ufak bir sorun oldu:", err);
      }

      // Canlı güncelleme döngüsünün kullanacağı durak/yön bilgisini kaydet (2. sorun)
      setAktifDurakBilgisi({ durakId: Number(durakData.durak_id), yon: hesaplananEvrenselYon });

      let apiBasarili = false;
      try {
        const moovitResponse = await fetch(
          `http://localhost:8000/api/moovit/${secilenHat}/${durakData.durak_id}/${durakData.hesaplanan_yon}`
        );
        if (moovitResponse.ok) {
          const data = await moovitResponse.json();
          if (data.yolcuya_bilgi && data.yolcuya_bilgi.length > 0) {
            setBeklenenAraclar(data.yolcuya_bilgi);
            apiBasarili = true;
          }
        }
      } catch (e) {
        console.warn("Moovit API'ye ulaşılamadı, Akıllı Algoritma'ya geçiliyor.");
      }

      if (!apiBasarili) {
        if (otobusler.length > 0) {
          const akilliListe = akilliTahminListesiUret(otobusler);
          if (akilliListe.length > 0) {
            setBeklenenAraclar(akilliListe);
            setBulunanDurakMesaji((onceki) => onceki + " · 🤖 Akıllı Tahmin devrede");
          } else {
            setHataMesaji(`Aktif araçlar var ancak size yakın ve doğru yönde (15km altı) araç bulunamadı.`);
          }
        } else {
          setHataMesaji(`Seçtiğiniz ${secilenHat} rotasında şu an aktif hareket eden bir araç bulunamadı.`);
        }
      }
    } catch (error: any) {
      console.error("Varış süresi hesaplanırken hata:", error);
      setHataMesaji(error.message || "Arka uca ulaşılamıyor.");
    }
    setHesaplaniyor(false);
  };

  // 🚌 Canlı otobüs konumları + 🕐 2 numaralı sorun için canlı dakika/geçmiş-araç güncellemesi.
  // Her 10 saniyede: önce otobüs konumlarını tazele, sonra (bir hesaplama yapılmışsa)
  // beklenenAraclar listesini otomatik güncelle. Kullanıcının tekrar butona basmasına gerek yok.
  useEffect(() => {
    otobusleriGetir();
    const interval = setInterval(async () => {
      await otobusleriGetir();
      if (aktifDurakBilgisiRef.current) {
        canliAraclariGuncelle();
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [secilenHat]);

  // 🚗 1 numaralı sorun: rotaDuraklari değiştiğinde (yeni hesaplama yapıldığında)
  // durak koordinatlarını Google Directions API'ye gönderip gerçek asfalt rotasını çiziyoruz.
  useEffect(() => {
    const rotaKoordinatlariHesapla = rotaDuraklari
      .map((durak: any) => ({
        lat: fixCoord(durak.latitude || durak.enlem),
        lng: fixCoord(durak.longitude || durak.boylam),
      }))
      .filter((coord: any) => coord.lat !== 0 && coord.lng !== 0);

    if (!isLoaded || rotaKoordinatlariHesapla.length < 2) {
      setYolCizgisi([]);
      return;
    }

    let iptalEdildi = false;
    kesintisizYolRotasiHesapla(rotaKoordinatlariHesapla).then((yol) => {
      if (!iptalEdildi) setYolCizgisi(yol);
    });

    return () => {
      iptalEdildi = true;
    };
  }, [rotaDuraklari, isLoaded]);

  const filtrelenmisHatlar = sistemdekiHatlar.filter(
    (hat) =>
      hat.hat_kodu.toLowerCase().includes(aramaMetni.toLowerCase()) ||
      hat.hat_adi.toLowerCase().includes(aramaMetni.toLowerCase())
  );

  // Google Directions henüz sonuç vermediyse (veya API kısıtlıysa) düz durak çizgisine geri düş
  const rotaKoordinatlariDuz = rotaDuraklari
    .map((durak: any) => ({
      lat: fixCoord(durak.latitude || durak.enlem),
      lng: fixCoord(durak.longitude || durak.boylam),
    }))
    .filter((coord: any) => coord.lat !== 0 && coord.lng !== 0);

  const cizilecekYol = yolCizgisi.length > 0 ? yolCizgisi : rotaKoordinatlariDuz;

  if (!isLoaded) return <div className="p-10 text-xl font-bold flex justify-center items-center h-screen bg-gray-50">🌍 Harita Yükleniyor...</div>;

  return (
    <div className="relative h-screen w-full bg-gray-50 overflow-hidden font-sans">

      {/* --- SOL PANEL --- */}
      <div
        className={`absolute top-0 left-0 h-full w-[26rem] bg-white/80 backdrop-blur-xl shadow-[20px_0_40px_-15px_rgba(0,0,0,0.3)] z-20 flex flex-col transition-transform duration-500 ease-in-out border-r border-white/40
        ${panelAcik ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <button
          onClick={() => setPanelAcik(!panelAcik)}
          className="absolute -right-12 top-6 bg-white/90 backdrop-blur-md w-12 h-14 rounded-r-xl shadow-[5px_5px_15px_rgba(0,0,0,0.15)] flex items-center justify-center border border-l-0 border-white/50 hover:bg-white transition-colors cursor-pointer"
        >
          <svg className={`w-6 h-6 text-blue-600 transform transition-transform duration-300 ${panelAcik ? 'rotate-180' : 'rotate-0'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7"></path>
          </svg>
        </button>

        <div className="p-6 bg-gradient-to-r from-blue-700/90 to-blue-500/90 text-white shadow-md">
          <h1 className="text-3xl font-extrabold tracking-tight">SmartTransit</h1>
          <p className="text-sm text-blue-100 mt-1 font-medium opacity-90">Akıllı Durak ve Araç Takibi</p>
        </div>

        <div className="p-6 flex-1 overflow-y-auto custom-scrollbar">
          <div className="bg-white/50 p-4 rounded-xl border border-white/60 shadow-sm mb-6">
            <h2 className="text-sm font-bold text-gray-700 mb-4 uppercase tracking-wider">Yolculuk Planla</h2>

            <div className="space-y-4">

              {/* 📍 ARAMA MENÜSÜ */}
              <div>
                <label className="block text-xs font-bold text-gray-500 mb-1">OTOBÜS HATTI ARA VEYA SEÇ</label>
                <div className="relative">
                  <input
                    type="text"
                    value={aramaMetni}
                    onChange={(e) => {
                      setAramaMetni(e.target.value);
                      setDropdownAcik(true);
                    }}
                    onFocus={() => setDropdownAcik(true)}
                    onBlur={() => setTimeout(() => setDropdownAcik(false), 200)}
                    placeholder="Hat ara (Örn: 500T)"
                    className="w-full border-2 border-gray-200 rounded-lg p-3 text-gray-800 font-bold focus:outline-none focus:border-blue-500 transition-colors bg-white/80"
                  />
                  <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-gray-400">
                    <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
                       <path d="M12.9 14.32a8 8 0 1 1 1.41-1.41l5.35 5.33-1.42 1.42-5.33-5.34zM8 14A6 6 0 1 0 8 2a6 6 0 0 0 0 12z"/>
                    </svg>
                  </div>

                  {dropdownAcik && (
                    <ul className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-2xl max-h-48 overflow-y-auto custom-scrollbar">
                      {filtrelenmisHatlar.length > 0 ? (
                        filtrelenmisHatlar.map((hat, i) => (
                          <li
                            key={i}
                            onClick={() => hatDegistir(hat.hat_kodu)}
                            className="p-2.5 border-b border-gray-100 hover:bg-blue-50 cursor-pointer flex items-center transition-colors"
                          >
                            <span className="text-xs font-black text-blue-600 mr-2 min-w-[35px]">{hat.hat_kodu}</span>
                            <span className="text-[11px] font-semibold text-gray-600 leading-tight truncate">{hat.hat_adi}</span>
                          </li>
                        ))
                      ) : (
                        <li className="p-3 text-xs text-gray-500 font-medium text-center">Hat bulunamadı</li>
                      )}
                    </ul>
                  )}
                </div>
              </div>

              {/* 📍 SWAP BUTONU VE İKİ ADRES INPUT'U */}
              <div className="relative flex flex-col gap-3 pt-2 pb-2">
                <div className="relative z-10 pr-10">
                  <label className="block text-xs font-bold text-gray-500 mb-1">ŞU AN NEREDESİNİZ?</label>
                  <Autocomplete
                    onLoad={onBaslangicLoad}
                    onPlaceChanged={onBaslangicChanged}
                    options={{ componentRestrictions: { country: "tr" } }}
                  >
                    <input
                      type="text"
                      value={baslangicMetni}
                      onChange={(e) => setBaslangicMetni(e.target.value)}
                      placeholder="Örn: Çatalca Pazar Yeri"
                      className="w-full border-2 border-gray-200 rounded-lg p-3 text-gray-700 font-medium focus:outline-none focus:border-blue-500 transition-colors bg-white/80"
                    />
                  </Autocomplete>
                </div>

                <div className="absolute right-0 top-[50%] -translate-y-[50%] z-20 flex flex-col justify-center h-full">
                  <button
                    onClick={(e) => {
                       e.preventDefault();
                       konumlariDegistir();
                    }}
                    title="Konumları Yer Değiştir"
                    className="bg-white p-2 rounded-full border border-gray-200 shadow hover:shadow-md hover:bg-blue-50 transition-all text-blue-600 active:scale-90 flex items-center justify-center mr-1"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="7 16 12 21 17 16"></polyline>
                      <line x1="12" y1="21" x2="12" y2="9"></line>
                      <polyline points="17 8 12 3 7 8"></polyline>
                      <line x1="12" y1="3" x2="12" y2="15"></line>
                    </svg>
                  </button>
                </div>

                <div className="relative z-10 pr-10">
                  <label className="block text-xs font-bold text-gray-500 mb-1">NEREYE GİDECEKSİNİZ?</label>
                  <Autocomplete
                    onLoad={onHedefLoad}
                    onPlaceChanged={onHedefChanged}
                    options={{ componentRestrictions: { country: "tr" } }}
                  >
                    <input
                      type="text"
                      value={hedefMetni}
                      onChange={(e) => setHedefMetni(e.target.value)}
                      placeholder="Örn: Avcılar Kampüsü"
                      className="w-full border-2 border-gray-200 rounded-lg p-3 text-gray-700 font-medium focus:outline-none focus:border-blue-500 transition-colors bg-white/80"
                    />
                  </Autocomplete>
                </div>
              </div>
              <p className="text-[10px] text-gray-400 font-medium -mt-1">* Çıkan listeden seçmeniz zorunludur.</p>

              <button
                onClick={varisSuresiniHesapla}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-lg transition-all shadow-md hover:shadow-lg active:scale-[0.98] flex justify-center items-center mt-2"
              >
                {hesaplaniyor ? (
                  <span className="flex items-center">
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Hesaplanıyor...
                  </span>
                ) : "Rota ve Süreyi Hesapla"}
              </button>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-end mb-4">
              <h2 className="text-lg font-bold text-gray-800">Yaklaşan Araçlar</h2>
              <span className="text-xs font-semibold text-gray-400 bg-gray-100 px-2 py-1 rounded">Canlı · 10sn</span>
            </div>

            {bulunanDurakMesaji && (
              <div className="mb-4 p-3 bg-blue-50/80 border border-blue-200 text-blue-800 text-sm font-semibold rounded-lg shadow-sm">
                {bulunanDurakMesaji}
              </div>
            )}

            {hataMesaji && (
              <div className="text-center text-red-500 font-medium text-sm mt-4 p-3 bg-red-50/80 rounded-lg">
                {hataMesaji}
              </div>
            )}

            {beklenenAraclar.length === 0 && !hesaplaniyor && !hataMesaji && (
              <div className="text-center text-gray-500 text-sm mt-4 p-6 border-2 border-dashed border-gray-200/80 rounded-xl bg-gray-50/50">
                Lütfen adresinizi ve yönü seçip hesapla butonuna tıklayın.
              </div>
            )}

            <div className="space-y-3">
              {beklenenAraclar.map((arac, index) => (
                <div key={index} className="bg-white/80 backdrop-blur-sm border border-gray-200 p-4 rounded-xl shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
                  <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500 rounded-l-xl"></div>
                  <div className="flex justify-between items-center ml-2">
                    <div>
                      <span className="font-extrabold text-gray-800 text-lg">Hat {secilenHat}</span>
                      <p className="text-xs text-gray-500 font-medium mt-0.5">Kapı No: {arac.kapi_no}</p>
                      <p className="text-[10px] text-gray-400 mt-1 uppercase tracking-wider">{turkceKarakterDuzelt(arac.gittigi_yon)}</p>
                    </div>
                    <div className="flex flex-col items-end">
                      <span className={`font-bold text-lg px-3 py-1 rounded-lg shadow-sm ${arac.tahmini_varis_dakika < 5 ? 'bg-red-100 text-red-600 animate-pulse border border-red-200' : 'bg-green-100 text-green-700'}`}>
                        {arac.tahmini_varis_dakika} Dk
                      </span>
                      <span className="text-xs text-gray-400 font-medium mt-1">{arac.mesafe_km} km mesafe</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* --- SAĞ KISIM: HARİTA --- */}
      <div className="absolute inset-0 w-full h-full z-0">

        <div className="absolute top-6 right-6 z-10 bg-white/90 backdrop-blur-sm p-4 rounded-xl shadow-[0_8px_30px_rgb(0,0,0,0.12)] border border-gray-100">
          <h1 className="text-lg font-black text-gray-800 uppercase tracking-wide">Hat {secilenHat} Canlı Takip</h1>
          <div className="flex items-center mt-1">
            <div className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse mr-2"></div>
            <p className="text-gray-600 text-sm font-medium">Aktif Araç: <span className="font-bold text-blue-600">{otobusler.length}</span></p>
          </div>
        </div>

        <GoogleMap mapContainerStyle={containerStyle} center={center} zoom={11}>

          {cizilecekYol.length > 0 && (
            <Polyline
              path={cizilecekYol}
              options={{
                strokeColor: "#3b82f6",
                strokeOpacity: 0.85,
                strokeWeight: 6,
                geodesic: false,
              }}
            />
          )}

          {rotaDuraklari.map((durak: any, index: number) => {
            const lat = fixCoord(durak.latitude || durak.enlem);
            const lng = fixCoord(durak.longitude || durak.boylam);
            if (lat === 0 || lng === 0) return null;
            return (
              <Marker
                key={`rota-durak-${index}`}
                position={{ lat, lng }}
                icon={window.google ? {
                  url: "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(`
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <circle cx="12" cy="12" r="8" fill="#ffffff" stroke="#000000" stroke-width="2.5"/>
                      <circle cx="12" cy="12" r="3" fill="#3b82f6"/>
                    </svg>
                  `),
                  scaledSize: new window.google.maps.Size(16, 16),
                  anchor: new window.google.maps.Point(8, 8),
                  labelOrigin: new window.google.maps.Point(8, 24)
                } : undefined}
                label={{
                  text: turkceKarakterDuzelt(durak.durak_adi) || "",
                  color: "#111827",
                  fontSize: "11px",
                  fontWeight: "800",
                }}
                title={turkceKarakterDuzelt(durak.durak_adi) || "Durak"}
                zIndex={40}
              />
            );
          })}

          {bulunanDurakKoordinat && bulunanDurakKoordinat.lat !== 0 && (
            <Marker
              position={{ lat: bulunanDurakKoordinat.lat, lng: bulunanDurakKoordinat.lng }}
              icon={{
                url: "http://maps.google.com/mapfiles/ms/icons/green-dot.png"
              }}
              label={{
                text: "SİZİN DURAĞINIZ",
                color: "#166534",
                fontSize: "13px",
                fontWeight: "900"
              }}
              title={`Sizin Durağınız: ${bulunanDurakKoordinat.adi}`}
              zIndex={50}
            />
          )}

          {otobusler.map((otobus: any, index: number) => {
            const lat = fixCoord(otobus.enlem);
            const lng = fixCoord(otobus.boylam);
            if (lat === 0 || lng === 0) return null;

            return (
              <Marker
                key={`otobus-${index}`}
                position={{ lat, lng }}
                onClick={() => setSeciliOtobus(otobus)}
                icon={{
                  url: "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(`
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#F59E0B" width="26px" height="26px">
                      <path d="M4 16c0 .88.39 1.67 1 2.22V19.5C5 20.33 5.67 21 6.5 21S8 20.33 8 19.5V19h8v.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5v-1.28c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z"/>
                    </svg>
                  `),
                  scaledSize: window.google ? new window.google.maps.Size(26, 26) : undefined,
                  anchor: window.google ? new window.google.maps.Point(13, 13) : undefined,
                }}
                label={{
                  text: otobus.kapino,
                  color: "#000000",
                  fontSize: "11px",
                  fontWeight: "900"
                }}
                title={`Kapı No: ${otobus.kapino} | Yön: ${turkceKarakterDuzelt(otobus.yon)}`}
                zIndex={100}
              />
            );
          })}

          {seciliOtobus && (
            <InfoWindow
              position={{
                lat: fixCoord(seciliOtobus.enlem),
                lng: fixCoord(seciliOtobus.boylam)
              }}
              onCloseClick={() => setSeciliOtobus(null)}
              options={{ pixelOffset: window.google ? new window.google.maps.Size(0, -15) : undefined }}
            >
              <div className="p-2 min-w-[140px] bg-white rounded-lg">
                <h3 className="font-black text-blue-700 text-sm mb-2 border-b pb-1 border-gray-200">
                  Hat {secilenHat}
                </h3>
                <div className="text-xs text-gray-700 space-y-1.5">
                  <p className="flex justify-between"><span className="font-bold text-gray-500">Kapı No:</span> <span className="font-extrabold">{seciliOtobus.kapino}</span></p>
                  <p className="border-t pt-1 mt-1 text-[10px] text-gray-500 uppercase tracking-wider text-center">{turkceKarakterDuzelt(seciliOtobus.yon)}</p>
                </div>
              </div>
            </InfoWindow>
          )}

        </GoogleMap>
      </div>

    </div>
  );
}

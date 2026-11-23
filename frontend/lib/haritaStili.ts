// Google Haritalar stilleri: arayüz renk belirteçleriyle uyumlu iki harita (gündüz "Sis", gece "Liman").
// Amaç: kara/su/yol hiyerarşisi sakin kalsın, üstündeki rota çizgisi ve rozetler öne çıksın; iş yeri ve otobüs durağı
// gürültüsü kapalı (durakları rota zaten gösteriyor).
export const GUNDUZ_STILI: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#eaf0ee" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#4a6573" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#f6f9f9" }, { weight: 3 }] },
  { featureType: "administrative.locality", elementType: "labels.text.fill", stylers: [{ color: "#27424f" }] },
  { featureType: "administrative", elementType: "geometry.stroke", stylers: [{ color: "#c8d6db" }] },
  { featureType: "landscape.natural", elementType: "geometry", stylers: [{ color: "#e3ece8" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#d3e5d2" }] },
  { featureType: "poi.park", elementType: "labels.text.fill", stylers: [{ color: "#4f7a5d" }] },
  { featureType: "poi.business", stylers: [{ visibility: "off" }] },
  { featureType: "poi.medical", stylers: [{ visibility: "off" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
  { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#dbe5e8" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#fbe6bb" }] },
  { featureType: "road.highway", elementType: "geometry.stroke", stylers: [{ color: "#ecd197" }] },
  { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#5d7886" }] },
  { featureType: "transit.station.bus", stylers: [{ visibility: "off" }] },
  { featureType: "transit.line", elementType: "geometry", stylers: [{ color: "#cfdbe0" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#bcd8e4" }] },
  { featureType: "water", elementType: "labels.text.fill", stylers: [{ color: "#4d7f93" }] },
];

export const GECE_STILI: google.maps.MapTypeStyle[] = [
  { elementType: "geometry", stylers: [{ color: "#0d2029" }] },
  { elementType: "labels.text.fill", stylers: [{ color: "#8fa9b5" }] },
  { elementType: "labels.text.stroke", stylers: [{ color: "#0a1a22" }, { weight: 3 }] },
  { featureType: "administrative.locality", elementType: "labels.text.fill", stylers: [{ color: "#c3d5dc" }] },
  { featureType: "administrative", elementType: "geometry.stroke", stylers: [{ color: "#1e3946" }] },
  { featureType: "landscape.natural", elementType: "geometry", stylers: [{ color: "#0b1c25" }] },
  { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#0f2a27" }] },
  { featureType: "poi.park", elementType: "labels.text.fill", stylers: [{ color: "#5f9a86" }] },
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "road", elementType: "geometry", stylers: [{ color: "#1a3646" }] },
  { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#0d2029" }] },
  { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#2b4c5d" }] },
  { featureType: "road.highway", elementType: "geometry.stroke", stylers: [{ color: "#102631" }] },
  { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#7f9aa8" }] },
  { featureType: "transit", stylers: [{ visibility: "off" }] },
  { featureType: "water", elementType: "geometry", stylers: [{ color: "#06121a" }] },
  { featureType: "water", elementType: "labels.text.fill", stylers: [{ color: "#5a7d8d" }] },
];

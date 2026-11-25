// Yürüyüş yolunun makullüğü (saf mantık; node ile test edilir). Google yürüyüş rotası kuş uçuşu mesafeden çok farklıysa
// (yanlış eşleşme, çok uzak bir köprü/alt geçit dolambacı) güvenilmez sayılır ve düz çizgi kalır.

/** Gerçek yürüyüş mesafesi, kuş uçuşuna göre makul mü? (Kuş uçuşundan kısa olamaz; 3 katı + 300 m'yi geçmemeli.) */
export function makulYurume(duzMetre: number, gercekMetre: number): boolean {
  if (!(duzMetre >= 0) || !(gercekMetre > 0)) return false;
  return gercekMetre >= duzMetre * 0.8 && gercekMetre <= duzMetre * 3 + 300;
}

/** Bu kadar kısa yürüyüşler (istasyon içi aktarma, aynı nokta) için yol aranmaz. */
export const EN_KISA_YURUME_M = 40;

/** Gerçek yürüyüşün planlanandan belirgin uzun olup olmadığı (≥ %30 ve ≥ 1 dk fazla). */
export function planlandanUzun(planlananSn: number, gercekSn: number): boolean {
  return gercekSn > planlananSn * 1.3 && gercekSn - planlananSn >= 60;
}

// node --experimental-strip-types --test lib/*.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  bos, bosDepo, depoCoz, EN_COK_FAVORI, EN_COK_SON, evKaydet, favoriEkle, favoriMi, favoriSil, isKaydet, mesafeM, sonEkle, sonlariSil, yerOlustur,
} from "./yerlerMantik.ts";

const kabatas = yerOlustur("Kabataş", 41.0366, 29.0006);
const taksim = yerOlustur("Taksim", 41.037, 28.985);

test("yerOlustur: id koordinattan, ad kırpılır", () => {
  assert.equal(kabatas.id, "41.03660,29.00060");
  assert.equal(yerOlustur("  x ".repeat(60), 41, 29).ad.length <= 80, true);
});

test("sonEkle: aynı yer başa taşınır, en çok 5", () => {
  let d = bosDepo();
  for (let i = 0; i < 8; i++) d = sonEkle(d, yerOlustur(`Yer ${i}`, 41 + i * 0.01, 29));
  assert.equal(d.son.length, EN_COK_SON);
  assert.equal(d.son[0].ad, "Yer 7");
  d = sonEkle(d, yerOlustur("Yer 5 (yeniden)", 41.05, 29)); // Yer 5 ile aynı koordinat
  assert.equal(d.son.length, EN_COK_SON);
  assert.equal(d.son[0].ad, "Yer 5 (yeniden)");
  assert.equal(d.son.filter((y) => y.ad.startsWith("Yer 5")).length, 1);
});

test("favoriler: ekle, tekrar ekleme tekilleştirir, sil, üst sınır", () => {
  let d = favoriEkle(bosDepo(), kabatas);
  d = favoriEkle(d, taksim);
  d = favoriEkle(d, yerOlustur("Kabataş (iskele)", 41.03662, 29.00062)); // ~3 m: aynı yer
  assert.equal(d.favoriler.length, 2);
  assert.equal(favoriMi(d, kabatas), true);
  d = favoriSil(d, kabatas);
  assert.equal(favoriMi(d, kabatas), false);
  let f = bosDepo();
  for (let i = 0; i < EN_COK_FAVORI + 5; i++) f = favoriEkle(f, yerOlustur(`F${i}`, 40.8 + i * 0.02, 29));
  assert.equal(f.favoriler.length, EN_COK_FAVORI);
  assert.equal(f.favoriler[0].ad, `F${EN_COK_FAVORI + 4}`); // en yeni başta, en eskiler düştü
});

test("ev/iş kaydı, silme ve boşluk", () => {
  let d = evKaydet(bosDepo(), kabatas);
  d = isKaydet(d, taksim);
  assert.equal(d.ev?.ad, "Kabataş");
  assert.equal(d.is?.ad, "Taksim");
  assert.equal(bos(d), false);
  d = isKaydet(evKaydet(d, null), null);
  assert.equal(bos(d), true);
  assert.equal(bos(sonlariSil(sonEkle(bosDepo(), taksim))), true);
});

test("depoCoz: bozuk, eksik ve İstanbul dışı kayıtlar atılır", () => {
  assert.deepEqual(depoCoz(null), bosDepo());
  assert.deepEqual(depoCoz("{bozuk"), bosDepo());
  assert.deepEqual(depoCoz("[1,2]"), bosDepo());
  const d = depoCoz(JSON.stringify({
    ev: { ad: "Ev", lat: 41.0, lng: 29.0 },
    is: { ad: "Uzak", lat: 10, lng: 29 }, // İstanbul dışı
    favoriler: [{ ad: "A", lat: 41.0, lng: 29.0 }, { ad: "", lat: 41, lng: 29 }, null, { ad: "B", lat: "41", lng: 29 }],
    son: "yanlış tür",
  }));
  assert.equal(d.ev?.ad, "Ev");
  assert.equal(d.is, null);
  assert.equal(d.favoriler.length, 1);
  assert.deepEqual(d.son, []);
});

test("depoCoz: yazılan depo geri okunur", () => {
  let d = favoriEkle(evKaydet(bosDepo(), kabatas), taksim);
  d = sonEkle(d, taksim);
  assert.deepEqual(depoCoz(JSON.stringify(d)), d);
});

test("mesafeM makul", () => {
  const m = mesafeM(kabatas, taksim);
  assert.ok(m > 1200 && m < 1400, String(m));
});

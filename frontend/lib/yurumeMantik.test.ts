// node --experimental-strip-types --test lib/*.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { EN_KISA_YURUME_M, makulYurume, planlandanUzun } from "./yurumeMantik.ts";

test("makulYurume: kuş uçuşundan kısa ya da çok uzun yollar reddedilir", () => {
  assert.equal(makulYurume(200, 260), true); // sokaktan dolaşma
  assert.equal(makulYurume(200, 200), true);
  assert.equal(makulYurume(200, 150), false); // kuş uçuşundan çok kısa: eşleşme hatası
  assert.equal(makulYurume(200, 900), true); // sınır: 3 katı + 300 m
  assert.equal(makulYurume(200, 901), false);
  assert.equal(makulYurume(200, 899), true);
  assert.equal(makulYurume(0, 0), false);
  assert.equal(makulYurume(50, Number.NaN), false);
});

test("planlandanUzun: yalnızca belirgin farkta", () => {
  assert.equal(planlandanUzun(180, 200), false);
  assert.equal(planlandanUzun(180, 260), true); // +80 sn, %44
  assert.equal(planlandanUzun(600, 700), false); // %17
  assert.equal(planlandanUzun(30, 70), false); // oran var ama fark 40 sn
  assert.ok(EN_KISA_YURUME_M > 0);
});

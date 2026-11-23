// node --experimental-strip-types --test lib/*.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { baglantiCoz, baglantiOlustur, GECERLI_MODLAR, type UrlDurum } from "./baglanti.ts";

const temel = (): UrlDurum => ({
  bas: { lat: 41.037, lng: 28.985, ad: "Taksim" },
  bit: { lat: 40.99, lng: 29.02, ad: "Kadıköy, İskele" },
  zaman: { tip: "simdi", deger: "" },
  tercih: "fastest",
  modlar: null,
  maxYurume: 800,
});

test("varsayılan durum: yalnızca yerler yazılır", () => {
  const s = baglantiOlustur(temel());
  assert.ok(s.startsWith("?from=41.03700%2C28.98500&fn=Taksim&to=40.99000%2C29.02000&tn="));
  assert.ok(!s.includes("&t=") && !s.includes("tercih") && !s.includes("modlar") && !s.includes("yurume"));
  assert.equal(baglantiOlustur({ ...temel(), bas: null, bit: null }), "");
});

test("gidiş-dönüş: tüm alanlar korunur", () => {
  const d: UrlDurum = {
    ...temel(),
    zaman: { tip: "varis", deger: "2026-11-24T10:30" },
    tercih: "fewest_transfers",
    modlar: ["metro", "ferry"],
    maxYurume: 1200,
  };
  assert.deepEqual(baglantiCoz(baglantiOlustur(d)), d);
  const k = { ...temel(), zaman: { tip: "kalkis" as const, deger: "2026-11-24T08:05" } };
  assert.deepEqual(baglantiCoz(baglantiOlustur(k)), k);
  assert.deepEqual(baglantiCoz(baglantiOlustur(temel())), temel());
});

test("Konumum başlangıcı bağlantıya yazılmaz (konum gizliliği)", () => {
  const s = baglantiOlustur({ ...temel(), bas: { lat: 41.01, lng: 29.0, ad: "Konumum" } });
  assert.ok(!s.includes("from=") && s.includes("to="));
  assert.equal(baglantiCoz(s).bas, null);
});

test("geçersiz parametreler sessizce yok sayılır", () => {
  const d = baglantiCoz("?from=abc&to=10.0,29.0&t=x&d=bozuk&tercih=hizli&modlar=uçak,bus&yurume=99999&fn=%00x");
  assert.equal(d.bas, null);
  assert.equal(d.bit, null); // İstanbul dışı
  assert.deepEqual(d.zaman, { tip: "simdi", deger: "" });
  assert.equal(d.tercih, "fastest");
  assert.deepEqual(d.modlar, ["bus"]);
  assert.equal(d.maxYurume, 800);
  assert.deepEqual(baglantiCoz(""), { bas: null, bit: null, zaman: { tip: "simdi", deger: "" }, tercih: "fastest", modlar: null, maxYurume: 800 });
});

test("ad temizlenir ve kısaltılır; tüm modlar seçiliyse modlar yazılmaz", () => {
  const d = baglantiCoz(`?from=41.0,29.0&fn=${encodeURIComponent("a\u0001b".repeat(60))}`);
  assert.ok((d.bas?.ad.length ?? 0) <= 80 && !/[\u0000-\u001f]/.test(d.bas?.ad ?? ""));
  assert.ok(!baglantiOlustur({ ...temel(), modlar: [...GECERLI_MODLAR] }).includes("modlar="));
  assert.equal(baglantiCoz(`?modlar=${GECERLI_MODLAR.join(",")}`).modlar, null);
});

test("geçersiz tarih/saat zamanı yok sayar", () => {
  assert.deepEqual(baglantiCoz("?t=k&d=2026-13-45T25:61").zaman.tip, "simdi");
});

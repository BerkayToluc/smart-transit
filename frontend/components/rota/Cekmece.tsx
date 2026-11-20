"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMedya, usePencereYuksekligi } from "@/lib/hooks";

const ORANLAR = [0.3, 0.58, 0.92]; // telefonda çekmecenin ekran yüksekliğine oranı (üç duruş)
export const PANEL_GENISLIK = 416; // masaüstü paneli, px (26rem)

export interface Olcu {
  sol: number; // haritanın solda kapalı kalan kısmı, px
  alt: number; // haritanın altta kapalı kalan kısmı, px
}

/** Masaüstünde sol panel; telefonda sürüklenebilir alt çekmece. */
export default function Cekmece({ children, onOlcu }: { children: React.ReactNode; onOlcu: (o: Olcu) => void }) {
  const [adim, setAdim] = useState(1);
  const [surukle, setSurukle] = useState<number | null>(null); // sürüklerken anlık yükseklik (px)
  const pencereY = usePencereYuksekligi();
  const mobil = useMedya("(max-width: 767px)");
  const baslangic = useRef<{ y: number; yukseklik: number } | null>(null);

  const yukseklik = surukle ?? ORANLAR[adim] * pencereY;

  const bildir = useCallback(() => {
    const m = window.innerWidth < 768;
    onOlcu(m ? { sol: 0, alt: Math.round(ORANLAR[adim] * window.innerHeight) } : { sol: PANEL_GENISLIK, alt: 0 });
  }, [adim, onOlcu]);
  useEffect(() => {
    bildir();
    window.addEventListener("resize", bildir);
    return () => window.removeEventListener("resize", bildir);
  }, [bildir]);

  const basla = (e: React.PointerEvent) => {
    baslangic.current = { y: e.clientY, yukseklik };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const tasi = (e: React.PointerEvent) => {
    if (!baslangic.current) return;
    const yeni = baslangic.current.yukseklik + (baslangic.current.y - e.clientY);
    setSurukle(Math.min(Math.max(yeni, pencereY * 0.2), pencereY * 0.95));
  };
  const birak = () => {
    if (surukle != null) {
      const oran = surukle / pencereY;
      let en = 0;
      ORANLAR.forEach((o, i) => {
        if (Math.abs(o - oran) < Math.abs(ORANLAR[en] - oran)) en = i;
      });
      setAdim(en);
    }
    setSurukle(null);
    baslangic.current = null;
  };

  return (
    <aside
      aria-label="Rota planlayıcı"
      className="fixed inset-x-0 bottom-0 z-30 flex flex-col rounded-t-[28px] bg-sis shadow-[var(--gol)] md:inset-y-0 md:left-0 md:right-auto md:w-[26rem] md:rounded-none md:!h-auto"
      style={{ height: mobil ? yukseklik : undefined, transition: surukle == null ? "height 260ms cubic-bezier(0.2,0.7,0.2,1)" : "none" }}
    >
      <div
        className="grid h-8 shrink-0 cursor-grab touch-none place-items-center md:hidden"
        onPointerDown={basla}
        onPointerMove={tasi}
        onPointerUp={birak}
        onPointerCancel={birak}
      >
        <button
          type="button"
          aria-label="Paneli büyüt ya da küçült"
          onClick={() => setAdim((a) => (a + 1) % ORANLAR.length)}
          className="h-1.5 w-12 rounded-full bg-cizgi"
        />
      </div>
      {children}
    </aside>
  );
}

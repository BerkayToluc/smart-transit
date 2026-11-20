"use client";
import { useState } from "react";
import HatTakibi from "@/components/HatTakibi";
import RotaPlanla from "@/components/rota/RotaPlanla";

type Sekme = "rota" | "hat";

/** Üstte yüzen iki sekme: "Rota planla" (yeni) ve "Hat takibi" (canlı otobüs; eskisi aynen). */
export default function Uygulama() {
  const [sekme, setSekme] = useState<Sekme>("rota");
  const secenekler: { id: Sekme; ad: string }[] = [
    { id: "rota", ad: "Rota planla" },
    { id: "hat", ad: "Hat takibi" },
  ];
  return (
    <main className="relative h-dvh w-full overflow-hidden">
      <div
        role="tablist"
        aria-label="Ekran"
        className="absolute left-1/2 top-3 z-40 flex -translate-x-1/2 gap-1 md:left-[calc(50%+13rem)] rounded-full bg-yuzey/95 p-1 shadow-[var(--gol)] backdrop-blur"
      >
        {secenekler.map((s) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={sekme === s.id}
            onClick={() => setSekme(s.id)}
            className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-semibold transition-colors ${
              sekme === s.id ? "bg-murekkep text-yuzey" : "text-murekkep-2 hover:text-murekkep"
            }`}
          >
            {s.ad}
          </button>
        ))}
      </div>
      {sekme === "rota" ? <RotaPlanla /> : <HatTakibi />}
    </main>
  );
}

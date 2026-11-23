"use client";
import { useRef } from "react";
import { Ay, Gunes, Otomatik } from "@/components/rota/Ikonlar";
import { useTema, type TemaSecimi } from "@/lib/tema";

const SECENEKLER: { id: TemaSecimi; ad: string; Ikon: typeof Gunes }[] = [
  { id: "acik", ad: "Açık tema", Ikon: Gunes },
  { id: "sistem", ad: "Sistem teması", Ikon: Otomatik },
  { id: "koyu", ad: "Koyu tema", Ikon: Ay },
];

/** Açık / sistem / koyu seçici. Radyo grubu: ok tuşlarıyla gezilir, seçili durum ekran okuyucuya bildirilir. */
export default function TemaSecici() {
  const { secim, sec } = useTema();
  const kapsayici = useRef<HTMLDivElement>(null);

  const tusa = (e: React.KeyboardEvent, i: number) => {
    const yon = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!yon) return;
    e.preventDefault();
    const sonraki = (i + yon + SECENEKLER.length) % SECENEKLER.length;
    sec(SECENEKLER[sonraki].id);
    kapsayici.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[sonraki]?.focus();
  };

  return (
    <div
      ref={kapsayici}
      role="radiogroup"
      aria-label="Görünüm teması"
      className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-yuzey-2 p-0.5"
    >
      {SECENEKLER.map(({ id, ad, Ikon }, i) => {
        const secili = secim === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={secili}
            aria-label={ad}
            title={ad}
            tabIndex={secili ? 0 : -1}
            onClick={() => sec(id)}
            onKeyDown={(e) => tusa(e, i)}
            className={`grid h-8 w-8 place-items-center rounded-full text-[17px] transition-colors ${
              secili ? "bg-yuzey text-bogaz shadow-[var(--gol)]" : "text-murekkep-2 hover:text-murekkep"
            }`}
          >
            <Ikon />
          </button>
        );
      })}
    </div>
  );
}

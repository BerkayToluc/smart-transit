// Küçük, tutarlı çizgi ikonlar (20x20, 1.8 çizgi). Emoji yerine: boyut/renk kontrol edilebilir.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

function Taban({ children, ...p }: P) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...p}
    >
      {children}
    </svg>
  );
}

export const Yurume = (p: P) => (
  <Taban {...p}>
    <circle cx="13" cy="4.5" r="1.8" />
    <path d="M9 21l2.2-6.2L9 12.5l1.5-4.2 3.8 1.6 2.2 3.2M12.8 14.8l2.7 2.2.7 4M9.2 12.6L6.5 14" />
  </Taban>
);
export const Otobus = (p: P) => (
  <Taban {...p}>
    <rect x="4" y="3.5" width="16" height="14" rx="3" />
    <path d="M4 11h16M7.5 20.5v-3M16.5 20.5v-3" />
    <circle cx="8" cy="14.2" r=".6" fill="currentColor" />
    <circle cx="16" cy="14.2" r=".6" fill="currentColor" />
  </Taban>
);
export const Metrobus = (p: P) => (
  <Taban {...p}>
    <rect x="3" y="4.5" width="18" height="12.5" rx="3" />
    <path d="M3 9.5h18M6 20.5v-3.5M18 20.5v-3.5M9 4.5v5M15 4.5v5" />
  </Taban>
);
export const Metro = (p: P) => (
  <Taban {...p}>
    <rect x="5" y="3" width="14" height="14" rx="4" />
    <path d="M5 11h14M8 21l2-4M16 21l-2-4" />
    <circle cx="9" cy="14" r=".6" fill="currentColor" />
    <circle cx="15" cy="14" r=".6" fill="currentColor" />
  </Taban>
);
export const Tramvay = (p: P) => (
  <Taban {...p}>
    <rect x="5" y="5" width="14" height="12" rx="3" />
    <path d="M5 11h14M12 2.5V5M8 20.5l1.5-3.5M16 20.5L14.5 17" />
  </Taban>
);
export const Funikuler = (p: P) => (
  <Taban {...p}>
    <path d="M3 20L21 9" />
    <rect x="8" y="8.5" width="8" height="6" rx="1.5" transform="rotate(-30 12 11.5)" />
  </Taban>
);
export const Teleferik = (p: P) => (
  <Taban {...p}>
    <path d="M3 5l18 4M12 7v3" />
    <rect x="7.5" y="10" width="9" height="7" rx="2" />
  </Taban>
);
export const Tren = (p: P) => (
  <Taban {...p}>
    <rect x="5" y="3" width="14" height="14" rx="3" />
    <path d="M5 12h14M9 3v4M15 3v4M8 21l2-4M16 21l-2-4" />
  </Taban>
);
export const Vapur = (p: P) => (
  <Taban {...p}>
    <path d="M3 15.5l2.5 4h13l2.5-4-9-2.5-9 2.5z" />
    <path d="M7 12.8V9h10v3.8M10 9V5.5h4V9M2.5 22c2 0 2.5-1 4.5-1s2.5 1 4.5 1 2.5-1 4.5-1 2.5 1 4.5 1" />
  </Taban>
);
export const Degistir = (p: P) => (
  <Taban {...p}>
    <path d="M8 4v14M8 18l-3-3M8 18l3-3M16 20V6M16 6l-3 3M16 6l3 3" />
  </Taban>
);
export const Konum = (p: P) => (
  <Taban {...p}>
    <circle cx="12" cy="12" r="3.2" />
    <path d="M12 2.5v3.3M12 18.2v3.3M2.5 12h3.3M18.2 12h3.3" />
  </Taban>
);
export const Saat = (p: P) => (
  <Taban {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7v5l3 2" />
  </Taban>
);
export const Ok = (p: P) => (
  <Taban {...p}>
    <path d="M9 5l7 7-7 7" />
  </Taban>
);
export const Asagi = (p: P) => (
  <Taban {...p}>
    <path d="M5 9l7 7 7-7" />
  </Taban>
);
export const Kapat = (p: P) => (
  <Taban {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Taban>
);
export const Uyari = (p: P) => (
  <Taban {...p}>
    <path d="M12 4l9 16H3L12 4zM12 10v4.5M12 17.2v.1" />
  </Taban>
);

export const MOD_IKON: Record<string, (p: P) => React.JSX.Element> = {
  walk: Yurume,
  bus: Otobus,
  metrobus: Metrobus,
  metro: Metro,
  tram: Tramvay,
  funicular: Funikuler,
  cable_car: Teleferik,
  rail: Tren,
  ferry: Vapur,
};

export function ModIkonu({ mod, ...p }: { mod: string } & P) {
  const Ikon = MOD_IKON[mod] ?? Otobus;
  return <Ikon {...p} />;
}

export const Gunes = (p: P) => (
  <Taban {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M5.5 18.5l1.7-1.7M16.8 7.2l1.7-1.7" />
  </Taban>
);
export const Ay = (p: P) => (
  <Taban {...p}>
    <path d="M20 14.2A8 8 0 0 1 9.8 4a8 8 0 1 0 10.2 10.2Z" />
  </Taban>
);
export const Otomatik = (p: P) => (
  <Taban {...p}>
    <circle cx="12" cy="12" r="8.2" />
    <path d="M12 3.8v16.4" />
    <path d="M12 3.8a8.2 8.2 0 0 1 0 16.4Z" fill="currentColor" stroke="none" />
  </Taban>
);

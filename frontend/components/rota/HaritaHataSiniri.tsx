"use client";
import { Component, type ReactNode } from "react";

/** Harita bileşeni (Google betiği, anahtar, ağ) neden çökerse çöksün panel ayakta kalır. */
export default class HaritaHataSiniri extends Component<{ children: ReactNode }, { hata: boolean }> {
  state = { hata: false };

  static getDerivedStateFromError() {
    return { hata: true };
  }

  componentDidCatch(hata: unknown) {
    console.error("Harita çizilemedi:", hata);
  }

  render() {
    if (!this.state.hata) return this.props.children;
    return (
      <div role="alert" className="absolute inset-0 grid place-items-center bg-sis p-8 text-center">
        <div className="max-w-sm md:ml-[26rem]">
          <p className="text-[15px] font-semibold text-murekkep">Harita çizilemedi</p>
          <p className="mt-1 text-sm leading-relaxed text-murekkep-2">
            Rota adımları yine de soldaki listede görünür. Haritayı görmek için sayfayı yenileyin; sorun sürerse Google Haritalar
            anahtarını kontrol edin.
          </p>
        </div>
      </div>
    );
  }
}

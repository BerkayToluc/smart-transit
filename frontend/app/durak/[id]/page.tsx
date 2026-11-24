import DurakSayfasi from "@/components/rota/DurakSayfasi";

// Durak sayfası: /durak/iett%3A123. Kimlik adres çubuğunda kodlu gelir; çözülüp bileşene verilir.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DurakSayfasi id={decodeURIComponent(id)} />;
}

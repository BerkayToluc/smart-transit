import { NextResponse } from 'next/server';
import { Pool } from 'pg';

// 🚨 NEXT.JS'İN TEMBELLİK YAPMASINI (CACHE) ENGELLEYEN SİHİRLİ KOD
export const dynamic = 'force-dynamic';

// Neon.tech veritabanı bağlantısı: adres koda yazılmaz, DATABASE_URL ortam
// değişkeninden okunur (frontend/.env.local — bkz. frontend/.env.example).
// Havuz ilk istekte oluşturulur; böylece değişken yokken build kırılmaz.
let pool: Pool | null = null;

function getPool(): Pool {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("DATABASE_URL ortam değişkeni tanımlı değil.");
  }
  if (!pool) {
    pool = new Pool({ connectionString });
  }
  return pool;
}

export async function GET() {
  try {
    const client = await getPool().connect();

    // Veritabanındaki hatları canlı olarak çekiyoruz (522 burada gelecek!)
    const result = await client.query('SELECT * FROM hatlar ORDER BY hat_kodu ASC');
    client.release();

    // Frontend'e JSON olarak gönderiyoruz
    return NextResponse.json(result.rows);
  } catch (error) {
    console.error("Veritabanı bağlantı hatası:", error);
    return NextResponse.json({ error: "Hatlar getirilemedi." }, { status: 500 });
  }
}
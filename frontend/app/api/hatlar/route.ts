import { NextResponse } from 'next/server';
import { Pool } from 'pg';

// 🚨 NEXT.JS'İN TEMBELLİK YAPMASINI (CACHE) ENGELLEYEN SİHİRLİ KOD
export const dynamic = 'force-dynamic';

// Neon.tech veritabanı bağlantımız
const pool = new Pool({
  connectionString: "postgresql://neondb_owner:npg_v0PSI1MVHXlF@ep-lucky-wind-asuclpxw-pooler.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require",
});

export async function GET() {
  try {
    const client = await pool.connect();

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
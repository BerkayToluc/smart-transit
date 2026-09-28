/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        // Ne zaman "/api/python/..." ile başlayan bir istek gelirse
        source: '/api/python/:path*',
        // Arka planda bunu sessizce Python sunucusuna (8000) yönlendir
        destination: 'http://127.0.0.1:8000/api/:path*',
      },
    ]
  },
}

export default nextConfig;
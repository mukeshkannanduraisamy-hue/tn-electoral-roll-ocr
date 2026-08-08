/** @type {import('next').NextConfig} */
const backendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

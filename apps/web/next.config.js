/** @type {import('next').NextConfig} */
const backendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8000";

const nextConfig = {
  output: "export",
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  images: { unoptimized: true },
};

module.exports = nextConfig;

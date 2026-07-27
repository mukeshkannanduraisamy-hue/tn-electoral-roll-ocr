import type { NextConfig } from "next";

/**
 * Backend origin used by the dev/SSR rewrite proxy.
 *
 * On Render, `BACKEND_URL` is injected from the API service via
 * `fromService` in render.yaml, so the two services stay wired together
 * without hardcoding a hostname.
 */
const backendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // `@ocr/shared-types` ships raw .ts (its `main` points at src/index.ts).
  // Without this, a fresh `npm install` -- which is exactly what Render
  // runs -- symlinks it into node_modules and the build fails, because
  // Next does not transpile TypeScript found there by default. Locally the
  // symlink is often absent and the tsconfig path mapping hides the
  // problem, so this only breaks in CI. Declare it explicitly.
  transpilePackages: ["@ocr/shared-types"],

  // Keep the production image lean; source maps of a 6MB bundle are not
  // worth the build time or the disk on a small instance.
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

export default nextConfig;

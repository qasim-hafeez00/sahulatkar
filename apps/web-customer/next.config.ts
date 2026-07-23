import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["sk-shared-ts"],
  // sk-shared-ts lives in packages/shared-ts, outside this app's own
  // directory — Turbopack otherwise refuses to resolve files above its
  // inferred root (this app directory, since there's no root package.json).
  turbopack: {
    root: path.join(process.cwd(), "..", ".."),
  },
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "images.unsplash.com",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;

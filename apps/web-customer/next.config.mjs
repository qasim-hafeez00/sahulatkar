import path from "node:path";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  transpilePackages: ["sk-shared-ts"],
  turbopack: {
    root: path.join(process.cwd(), "..", ".."),
  },
};

export default nextConfig;
